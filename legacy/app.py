"""
Seelice — mini VMS (gestion centralisée de caméras IP) pour lab réseau.

- Inventaire des caméras (SQLite)
- Statut en ligne / hors ligne (test TCP du port RTSP)
- Vue live en mosaïque + plein écran (ffmpeg RTSP -> JPEG, un seul flux partagé par caméra)
- Captures d'écran
- Découverte ONVIF (WS-Discovery) + scan d'un sous-réseau sur le port 554
- Accès protégé par mot de passe admin

Lancement :  python app.py   puis  http://<ip-du-pc>:8080
"""
import ipaddress
import json
import os
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import wraps
from urllib.parse import quote, unquote, urlparse

from flask import (Flask, Response, abort, flash, g, jsonify, redirect,
                   render_template, request, send_from_directory, session,
                   url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import onvif

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "seelice.db")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
CAPTURE_DIR = os.path.join(DATA_DIR, "captures")
FFMPEG = os.environ.get("SEELICE_FFMPEG", "ffmpeg")
HOST = os.environ.get("SEELICE_HOST", "0.0.0.0")
PORT = int(os.environ.get("SEELICE_PORT", "8080"))

os.makedirs(CAPTURE_DIR, exist_ok=True)

# Préréglages par marque : port RTSP et chemins des flux principal / secondaire
BRANDS = {
    "hikvision": {"label": "Hikvision / HiLook / Ezviz pro", "port": 554,
                  "main": "/Streaming/Channels/101", "sub": "/Streaming/Channels/102"},
    "dahua": {"label": "Dahua / Imou / Lorex", "port": 554,
              "main": "/cam/realmonitor?channel=1&subtype=0",
              "sub": "/cam/realmonitor?channel=1&subtype=1"},
    "hanwha": {"label": "Wisenet / Hanwha / Samsung", "port": 554,
               "main": "/profile2/media.smp", "sub": "/profile3/media.smp"},
    "reolink": {"label": "Reolink", "port": 554,
                "main": "/h264Preview_01_main", "sub": "/h264Preview_01_sub"},
    "tapo": {"label": "TP-Link Tapo / VIGI", "port": 554,
             "main": "/stream1", "sub": "/stream2"},
    "uniview": {"label": "Uniview (UNV)", "port": 554,
                "main": "/media/video1", "sub": "/media/video2"},
    "axis": {"label": "Axis", "port": 554,
             "main": "/axis-media/media.amp", "sub": "/axis-media/media.amp?resolution=640x360"},
    "custom": {"label": "Autre marque (RTSP / ONVIF)", "port": 554, "main": "", "sub": ""},
    "demo": {"label": "Caméra de démo (mire de test, sans matériel)", "port": 0, "main": "", "sub": ""},
}

# Flux live : largeur et images/s selon la qualité
QUALITY = {"sub": {"width": 640, "fps": 5}, "main": {"width": 1280, "fps": 12}}
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def load_config():
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    changed = False
    if "secret_key" not in cfg:
        cfg["secret_key"] = secrets.token_hex(32)
        changed = True
    cfg.setdefault("admin_hash", None)
    if changed:
        save_config(cfg)
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


CONFIG = load_config()
app = Flask(__name__)
app.secret_key = CONFIG["secret_key"]
app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_HTTPONLY=True)

# --------------------------------------------------------------------------
# Base de données
# --------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS cameras (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    brand       TEXT NOT NULL DEFAULT 'custom',
    ip          TEXT NOT NULL,
    rtsp_port   INTEGER NOT NULL DEFAULT 554,
    username    TEXT DEFAULT '',
    password    TEXT DEFAULT '',
    main_path   TEXT DEFAULT '',
    sub_path    TEXT DEFAULT '',
    location    TEXT DEFAULT '',
    vlan        TEXT DEFAULT '',
    notes       TEXT DEFAULT '',
    created_at  TEXT NOT NULL
);
"""


def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_db():
    if "db" not in g:
        g.db = db_connect()
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


with db_connect() as _c:
    _c.executescript(SCHEMA)
    # Migrations douces pour les bases créées par une version précédente
    _cols = {r[1] for r in _c.execute("PRAGMA table_info(cameras)")}
    if "onvif_port" not in _cols:
        _c.execute("ALTER TABLE cameras ADD COLUMN onvif_port INTEGER NOT NULL DEFAULT 80")


def all_cameras():
    return [dict(r) for r in get_db().execute("SELECT * FROM cameras ORDER BY location, name")]


def get_camera(cam_id):
    row = get_db().execute("SELECT * FROM cameras WHERE id = ?", (cam_id,)).fetchone()
    if row is None:
        abort(404)
    return dict(row)


# --------------------------------------------------------------------------
# Authentification
# --------------------------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if CONFIG.get("admin_hash") is None:
            return redirect(url_for("setup"))
        if not session.get("auth"):
            if request.path.startswith("/api/"):
                return jsonify(error="non authentifié"), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.route("/setup", methods=["GET", "POST"])
def setup():
    if CONFIG.get("admin_hash"):
        return redirect(url_for("login"))
    if request.method == "POST":
        pw = request.form.get("password", "")
        if len(pw) < 8:
            flash("Le mot de passe doit faire au moins 8 caractères.", "error")
        elif pw != request.form.get("confirm"):
            flash("Les deux mots de passe ne correspondent pas.", "error")
        else:
            CONFIG["admin_hash"] = generate_password_hash(pw)
            save_config(CONFIG)
            session["auth"] = True
            flash("Mot de passe admin créé. Bienvenue sur Seelice !", "ok")
            return redirect(url_for("index"))
    return render_template("setup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if CONFIG.get("admin_hash") is None:
        return redirect(url_for("setup"))
    if request.method == "POST":
        if check_password_hash(CONFIG["admin_hash"], request.form.get("password", "")):
            session["auth"] = True
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("index"))
        time.sleep(1)  # ralentit le brute-force
        flash("Mot de passe incorrect.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# --------------------------------------------------------------------------
# RTSP / ffmpeg
# --------------------------------------------------------------------------
def build_rtsp_url(cam, quality="main", hide_password=False):
    path = (cam.get("sub_path") if quality == "sub" else "") or cam.get("main_path") or "/"
    if not path.startswith("/"):
        path = "/" + path
    auth = ""
    if cam.get("username"):
        pw = "****" if hide_password else quote(cam.get("password") or "", safe="")
        auth = f"{quote(cam['username'], safe='')}:{pw}@"
    return f"rtsp://{auth}{cam['ip']}:{cam['rtsp_port']}{path}"


def ffmpeg_input_args(cam, quality):
    if cam["brand"] == "demo":
        size = "640x360" if quality == "sub" else "1280x720"
        return ["-re", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=12"]
    return ["-rtsp_transport", "tcp", "-timeout", "5000000", "-i", build_rtsp_url(cam, quality)]


class LiveStream:
    """Un process ffmpeg par (caméra, qualité), partagé entre tous les spectateurs."""

    def __init__(self, key, input_args, width, fps):
        self.key = key
        self.input_args = input_args
        self.width = width
        self.fps = fps
        self.frame = None
        self.frame_id = 0
        self.cond = threading.Condition()
        self.last_access = time.time()
        self.running = True
        self.error = None
        self.proc = None
        threading.Thread(target=self._run, daemon=True).start()

    def touch(self):
        self.last_access = time.time()

    def _run(self):
        while self.running:
            cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin",
                   *self.input_args, "-an",
                   "-vf", f"scale={self.width}:-2,fps={self.fps}",
                   "-q:v", "6", "-f", "image2pipe", "-c:v", "mjpeg", "pipe:1"]
            try:
                self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                             stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
            except FileNotFoundError:
                self.error = "ffmpeg introuvable"
                self.running = False
                break
            buf = b""
            while self.running:
                chunk = self.proc.stdout.read1(65536)
                if not chunk:
                    break
                buf += chunk
                while True:
                    start = buf.find(b"\xff\xd8")
                    if start < 0:
                        buf = buf[-1:]
                        break
                    end = buf.find(b"\xff\xd9", start + 2)
                    if end < 0:
                        buf = buf[start:]
                        break
                    frame, buf = buf[start:end + 2], buf[end + 2:]
                    with self.cond:
                        self.frame = frame
                        self.frame_id += 1
                        self.error = None
                        self.cond.notify_all()
                if len(buf) > 8_000_000:
                    buf = b""
            self._kill()
            if self.running:
                self.error = "flux interrompu, reconnexion…"
                time.sleep(3)

    def get_frame(self, after=0, timeout=4.0):
        """Renvoie (jpeg, id) d'une image plus récente que `after`, ou (None, id) si timeout."""
        self.touch()
        with self.cond:
            self.cond.wait_for(lambda: self.frame_id > after or not self.running, timeout=timeout)
            if self.frame is not None and self.frame_id > after:
                return self.frame, self.frame_id
            return None, self.frame_id

    def _kill(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass

    def stop(self):
        self.running = False
        self._kill()
        with self.cond:
            self.cond.notify_all()


STREAMS = {}
STREAMS_LOCK = threading.Lock()


def get_stream(cam, quality):
    key = (cam["id"], quality)
    with STREAMS_LOCK:
        st = STREAMS.get(key)
        if st is None or not st.running:
            q = QUALITY[quality]
            st = LiveStream(key, ffmpeg_input_args(cam, quality), q["width"], q["fps"])
            STREAMS[key] = st
        st.touch()
        return st


def stop_streams_for(cam_id):
    with STREAMS_LOCK:
        for key in [k for k in STREAMS if k[0] == cam_id]:
            STREAMS.pop(key).stop()


def _watchdog():
    """Coupe les flux que plus personne ne regarde (économise CPU et bande passante)."""
    while True:
        time.sleep(5)
        now = time.time()
        with STREAMS_LOCK:
            for key in [k for k, s in STREAMS.items() if now - s.last_access > 20 or not s.running]:
                STREAMS.pop(key).stop()


threading.Thread(target=_watchdog, daemon=True).start()


# --------------------------------------------------------------------------
# Réseau : statut, découverte ONVIF, scan de sous-réseau
# --------------------------------------------------------------------------
def tcp_open(ip, port, timeout=1.5):
    try:
        with socket.create_connection((ip, int(port)), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def camera_online(cam):
    if cam["brand"] == "demo":
        return True
    return tcp_open(cam["ip"], cam["rtsp_port"])


def guess_brand(text):
    t = text.lower()
    for needle, brand in (("hikvision", "hikvision"), ("hilook", "hikvision"), ("dahua", "dahua"),
                          ("imou", "dahua"), ("wisenet", "hanwha"), ("hanwha", "hanwha"),
                          ("samsung", "hanwha"),("reolink", "reolink"), ("tp-link", "tapo"),
                          ("tapo", "tapo"), ("vigi", "tapo"), ("uniview", "uniview"), ("axis", "axis")):
        if needle in t:
            return brand
    return "custom"


WS_PROBE = """<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"
 xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"
 xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
 xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
<e:Header>
 <w:MessageID>uuid:{uid}</w:MessageID>
 <w:To e:mustUnderstand="true">urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
 <w:Action e:mustUnderstand="true">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
</e:Header>
<e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body>
</e:Envelope>"""


def onvif_discover(timeout=3.0):
    """WS-Discovery : envoie un Probe multicast et collecte les caméras ONVIF qui répondent."""
    found = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.settimeout(0.5)
        sock.bind(("", 0))
        probe = WS_PROBE.format(uid=uuid.uuid4()).encode()
        for _ in range(2):
            sock.sendto(probe, ("239.255.255.250", 3702))
        end = time.time() + timeout
        while time.time() < end:
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            text = data.decode("utf-8", errors="ignore")
            scopes_m = re.search(r"<[^>]*Scopes[^>]*>(.*?)</", text, re.S)
            xaddrs_m = re.search(r"<[^>]*XAddrs[^>]*>(.*?)</", text, re.S)
            scopes = unquote(scopes_m.group(1)) if scopes_m else ""
            name = re.search(r"onvif://www\.onvif\.org/name/(\S+)", scopes)
            hw = re.search(r"onvif://www\.onvif\.org/hardware/(\S+)", scopes)
            xaddrs = xaddrs_m.group(1).split() if xaddrs_m else []
            xaddr_ip = urlparse(xaddrs[0]).hostname if xaddrs else None
            found[addr[0]] = {
                "ip": addr[0],
                "announced_ip": xaddr_ip,
                "name": name.group(1).replace("_", " ") if name else "",
                "hardware": hw.group(1) if hw else "",
                "brand": guess_brand(scopes),
                "source": "ONVIF",
            }
    except OSError as exc:
        return [], str(exc)
    finally:
        sock.close()
    return list(found.values()), None


def local_subnet():
    """Devine le /24 du PC (adresse de l'interface qui sert de route par défaut)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # aucun paquet n'est envoyé
        ip = s.getsockname()[0]
    except OSError:
        ip = "192.168.1.10"
    finally:
        s.close()
    return str(ipaddress.ip_network(f"{ip}/24", strict=False))


def sweep_subnet(cidr, ports=(554, 80)):
    net = ipaddress.ip_network(cidr, strict=False)
    if net.num_addresses > 1024:
        raise ValueError("Sous-réseau trop grand (maximum /22, soit 1024 adresses).")
    hosts = [str(h) for h in net.hosts()] or [str(net.network_address)]

    def probe(ip):
        if not tcp_open(ip, ports[0], timeout=0.6):
            return None
        return {"ip": ip, "announced_ip": None, "name": "", "hardware": "",
                "brand": "custom", "source": f"Port {ports[0]} ouvert",
                "http": tcp_open(ip, ports[1], timeout=0.6)}

    with ThreadPoolExecutor(max_workers=128) as ex:
        return [r for r in ex.map(probe, hosts) if r]


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------
@app.route("/")
@login_required
def index():
    return render_template("index.html", cameras=all_cameras(), brands=BRANDS)


@app.route("/mur")
@login_required
def wall():
    cams = [{"id": c["id"], "name": c["name"], "location": c["location"]} for c in all_cameras()]
    return render_template("wall.html", cameras=cams)


@app.route("/camera/<int:cam_id>")
@login_required
def camera_view(cam_id):
    cam = get_camera(cam_id)
    return render_template("camera.html", cam=cam, brands=BRANDS,
                           rtsp_main=build_rtsp_url(cam, "main", hide_password=True),
                           rtsp_sub=build_rtsp_url(cam, "sub", hide_password=True))


def _form_to_camera(form, existing=None):
    brand = form.get("brand", "custom")
    if brand not in BRANDS:
        brand = "custom"
    data = {
        "name": form.get("name", "").strip(),
        "brand": brand,
        "ip": form.get("ip", "").strip(),
        "username": form.get("username", "").strip(),
        "password": form.get("password", ""),
        "main_path": form.get("main_path", "").strip(),
        "sub_path": form.get("sub_path", "").strip(),
        "location": form.get("location", "").strip(),
        "vlan": form.get("vlan", "").strip(),
        "notes": form.get("notes", "").strip(),
    }
    try:
        data["onvif_port"] = int(form.get("onvif_port") or 80)
        if not 1 <= data["onvif_port"] <= 65535:
            raise ValueError
    except ValueError:
        data["onvif_port"] = 80
    errors = []
    if not data["name"]:
        errors.append("Le nom est obligatoire.")
    if brand == "demo":
        data["ip"] = data["ip"] or "demo"
        data["rtsp_port"] = 0
    else:
        try:
            ipaddress.ip_address(data["ip"])
        except ValueError:
            errors.append("Adresse IP invalide.")
        try:
            data["rtsp_port"] = int(form.get("rtsp_port") or 554)
            if not 1 <= data["rtsp_port"] <= 65535:
                raise ValueError
        except ValueError:
            errors.append("Port RTSP invalide.")
            data["rtsp_port"] = 554
    # Mot de passe vide en modification = on garde l'ancien
    if existing is not None and data["password"] == "":
        data["password"] = existing["password"]
    return data, errors


@app.route("/cameras/new", methods=["GET", "POST"])
@login_required
def camera_new():
    if request.method == "POST":
        data, errors = _form_to_camera(request.form)
        if not errors:
            data["created_at"] = datetime.now().isoformat(timespec="seconds")
            cols = ", ".join(data)
            get_db().execute(f"INSERT INTO cameras ({cols}) VALUES ({', '.join('?' * len(data))})",
                             tuple(data.values()))
            get_db().commit()
            flash(f"Caméra « {data['name']} » ajoutée.", "ok")
            return redirect(url_for("index"))
        for e in errors:
            flash(e, "error")
        cam = data
    else:
        brand = request.args.get("brand", "hikvision")
        preset = BRANDS.get(brand, BRANDS["custom"])
        cam = {"name": request.args.get("name", ""), "brand": brand if brand in BRANDS else "custom",
               "ip": request.args.get("ip", ""), "rtsp_port": preset["port"] or 554,
               "username": "admin", "password": "", "main_path": preset["main"],
               "sub_path": preset["sub"], "location": "", "vlan": "", "notes": "", "onvif_port": 80}
    return render_template("camera_form.html", cam=cam, brands=BRANDS, editing=False)


@app.route("/cameras/<int:cam_id>/edit", methods=["GET", "POST"])
@login_required
def camera_edit(cam_id):
    existing = get_camera(cam_id)
    if request.method == "POST":
        data, errors = _form_to_camera(request.form, existing)
        if not errors:
            sets = ", ".join(f"{k} = ?" for k in data)
            get_db().execute(f"UPDATE cameras SET {sets} WHERE id = ?", (*data.values(), cam_id))
            get_db().commit()
            stop_streams_for(cam_id)  # pour relancer le flux avec les nouveaux paramètres
            onvif.forget(cam_id)
            flash(f"Caméra « {data['name']} » modifiée.", "ok")
            return redirect(url_for("index"))
        for e in errors:
            flash(e, "error")
        cam = {**existing, **data}
    else:
        cam = existing
    return render_template("camera_form.html", cam=cam, brands=BRANDS, editing=True)


@app.route("/cameras/<int:cam_id>/delete", methods=["POST"])
@login_required
def camera_delete(cam_id):
    cam = get_camera(cam_id)
    stop_streams_for(cam_id)
    onvif.forget(cam_id)
    get_db().execute("DELETE FROM cameras WHERE id = ?", (cam_id,))
    get_db().commit()
    flash(f"Caméra « {cam['name']} » supprimée.", "ok")
    return redirect(url_for("index"))


@app.route("/scan")
@login_required
def scan_page():
    return render_template("scan.html", subnet=local_subnet(), brands=BRANDS)


@app.route("/captures")
@login_required
def captures_page():
    files = sorted((f for f in os.listdir(CAPTURE_DIR) if f.lower().endswith(".jpg")), reverse=True)
    return render_template("captures.html", files=files[:200])


@app.route("/captures/<path:filename>")
@login_required
def capture_file(filename):
    return send_from_directory(CAPTURE_DIR, filename)


# --------------------------------------------------------------------------
# API (appelée par le JavaScript)
# --------------------------------------------------------------------------
@app.route("/api/status")
@login_required
def api_status():
    cams = all_cameras()
    with ThreadPoolExecutor(max_workers=32) as ex:
        states = list(ex.map(camera_online, cams))
    return jsonify({str(c["id"]): s for c, s in zip(cams, states)})


@app.route("/api/frame/<int:cam_id>")
@login_required
def api_frame(cam_id):
    quality = request.args.get("q", "sub")
    if quality not in QUALITY:
        quality = "sub"
    after = request.args.get("after", 0, type=int)
    cam = get_camera(cam_id)
    st = get_stream(cam, quality)
    frame, fid = st.get_frame(after=after)
    if frame is None:
        return jsonify(error=st.error or "pas de signal"), 503
    return Response(frame, mimetype="image/jpeg",
                    headers={"Cache-Control": "no-store", "X-Frame-Id": str(fid)})


@app.route("/api/cameras/<int:cam_id>/capture", methods=["POST"])
@login_required
def api_capture(cam_id):
    cam = get_camera(cam_id)
    st = get_stream(cam, "main")
    frame, _ = st.get_frame(after=0, timeout=10)
    if frame is None:
        return jsonify(error=st.error or "impossible de récupérer une image"), 503
    ascii_name = unicodedata.normalize("NFKD", cam["name"]).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", ascii_name).strip("-")[:40] or f"cam{cam_id}"
    filename = f"{datetime.now():%Y%m%d-%H%M%S}_{slug}.jpg"
    with open(os.path.join(CAPTURE_DIR, filename), "wb") as f:
        f.write(frame)
    return jsonify(file=filename, url=url_for("capture_file", filename=filename))


# --- Caméras motorisées (PTZ) via ONVIF -----------------------------------
def _ptz_camera(cam_id):
    cam = get_camera(cam_id)
    if cam["brand"] == "demo":
        raise onvif.OnvifError("la caméra de démo n'est pas motorisée")
    return onvif.get_onvif(cam)


def _clamp(v, lo=-1.0, hi=1.0):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return 0.0


@app.route("/api/cameras/<int:cam_id>/ptz")
@login_required
def api_ptz_info(cam_id):
    try:
        oc = _ptz_camera(cam_id)
        presets = oc.presets() if oc.has_ptz else []
        return jsonify(supported=oc.has_ptz, presets=presets)
    except onvif.OnvifError as exc:
        onvif.forget(cam_id)
        return jsonify(supported=False, presets=[], error=str(exc))


@app.route("/api/cameras/<int:cam_id>/ptz", methods=["POST"])
@login_required
def api_ptz_command(cam_id):
    body = request.get_json(silent=True) or {}
    action = body.get("action")
    try:
        oc = _ptz_camera(cam_id)
        if action == "move":
            oc.move(_clamp(body.get("pan")), _clamp(body.get("tilt")), _clamp(body.get("zoom")))
        elif action == "stop":
            oc.stop()
        elif action == "home":
            oc.home()
        elif action == "goto":
            oc.goto_preset(body.get("token", ""))
        elif action == "save":
            name = str(body.get("name", "")).strip()[:40] or datetime.now().strftime("Position %H:%M")
            oc.set_preset(name)
            return jsonify(ok=True, presets=oc.presets())
        else:
            return jsonify(error="action inconnue"), 400
        return jsonify(ok=True)
    except onvif.OnvifError as exc:
        onvif.forget(cam_id)
        return jsonify(error=str(exc)), 502


@app.route("/api/discover")
@login_required
def api_discover():
    results, err = onvif_discover()
    known = {c["ip"] for c in all_cameras()}
    for r in results:
        r["known"] = r["ip"] in known
    return jsonify(results=results, error=err)


@app.route("/api/sweep")
@login_required
def api_sweep():
    try:
        results = sweep_subnet(request.args.get("subnet", local_subnet()))
    except ValueError as exc:
        return jsonify(results=[], error=str(exc)), 400
    known = {c["ip"] for c in all_cameras()}
    for r in results:
        r["known"] = r["ip"] in known
    return jsonify(results=results, error=None)


@app.context_processor
def inject_globals():
    return {"now": datetime.now()}


if __name__ == "__main__":
    try:
        subprocess.run([FFMPEG, "-version"], capture_output=True, check=True,
                       creationflags=CREATE_NO_WINDOW)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("[!] ffmpeg introuvable : la vue live ne marchera pas. "
              "Windows : winget install Gyan.FFmpeg  |  Linux : sudo apt install ffmpeg")
    print(f"Seelice démarré -> http://localhost:{PORT}  (ou http://<ip-de-ce-pc>:{PORT} depuis le réseau)")
    app.run(host=HOST, port=PORT, threaded=True, debug=False)
