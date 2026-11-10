"""
Client ONVIF minimal (bibliothèque standard uniquement) pour piloter les caméras motorisées (PTZ).

- Authentification WS-Security UsernameToken (PasswordDigest), avec correction du décalage d'horloge
- Découverte des services (Media, PTZ) via GetCapabilities
- ContinuousMove / Stop / GotoHomePosition / GetPresets / GotoPreset / SetPreset
"""
import base64
import hashlib
import os
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from xml.sax.saxutils import escape

NS_DEVICE = "http://www.onvif.org/ver10/device/wsdl"
NS_MEDIA = "http://www.onvif.org/ver10/media/wsdl"
NS_PTZ = "http://www.onvif.org/ver20/ptz/wsdl"
NS_SCHEMA = "http://www.onvif.org/ver10/schema"
WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
WSU = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
PW_DIGEST = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest"
B64 = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary"


class OnvifError(Exception):
    pass


class OnvifAuthError(OnvifError):
    pass


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _find_all(root, name):
    return [el for el in root.iter() if _local(el.tag) == name]


def _find(root, name):
    for el in root.iter():
        if _local(el.tag) == name:
            return el
    return None


def _child_text(el, name, default=""):
    found = _find(el, name) if el is not None else None
    return (found.text or "").strip() if found is not None and found.text else default


class OnvifCamera:
    def __init__(self, ip, port, username, password, timeout=4.0):
        self.ip = ip
        self.port = int(port or 80)
        self.username = username or ""
        self.password = password or ""
        self.timeout = timeout
        self.device_url = f"http://{ip}:{self.port}/onvif/device_service"
        self.media_url = None
        self.ptz_url = None
        self.profile_token = None
        self.clock_offset = timedelta(0)
        self.ready = False
        # Méthode d'authentification : "wsse" (jeton dans le SOAP), "digest" (HTTP Digest) ou "both"
        self.auth_mode = "wsse"
        pwd_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        pwd_mgr.add_password(None, f"http://{ip}:{self.port}/", self.username, self.password)
        self._digest_opener = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(pwd_mgr))
        self._plain_opener = urllib.request.build_opener()

    # ------------------------------------------------------------------ SOAP
    def _security_header(self):
        if not self.username:
            return ""
        nonce = os.urandom(16)
        created = (datetime.now(timezone.utc) + self.clock_offset).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + self.password.encode()).digest()).decode()
        return (
            f'<wsse:Security s:mustUnderstand="1" xmlns:wsse="{WSSE}" xmlns:wsu="{WSU}">'
            f"<wsse:UsernameToken><wsse:Username>{escape(self.username)}</wsse:Username>"
            f'<wsse:Password Type="{PW_DIGEST}">{digest}</wsse:Password>'
            f'<wsse:Nonce EncodingType="{B64}">{base64.b64encode(nonce).decode()}</wsse:Nonce>'
            f"<wsu:Created>{created}</wsu:Created></wsse:UsernameToken></wsse:Security>"
        )

    def _call(self, url, body, auth=True):
        if not auth or not self.username:
            return self._send(url, body, wsse=False, digest=False)
        try:
            return self._send(url, body, wsse=self.auth_mode in ("wsse", "both"),
                              digest=self.auth_mode in ("digest", "both"))
        except OnvifAuthError:
            if self.ready:
                raise
            # Pendant la connexion : on essaie les autres méthodes et on retient celle qui marche
            for mode in ("digest", "both", "wsse"):
                if mode == self.auth_mode:
                    continue
                try:
                    root = self._send(url, body, wsse=mode in ("wsse", "both"), digest=mode in ("digest", "both"))
                    self.auth_mode = mode
                    return root
                except OnvifAuthError:
                    continue
            raise

    def _send(self, url, body, wsse, digest):
        envelope = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
            f'xmlns:tds="{NS_DEVICE}" xmlns:trt="{NS_MEDIA}" xmlns:tptz="{NS_PTZ}" xmlns:tt="{NS_SCHEMA}">'
            f"<s:Header>{self._security_header() if wsse else ''}</s:Header>"
            f"<s:Body>{body}</s:Body></s:Envelope>"
        ).encode("utf-8")
        req = urllib.request.Request(url, data=envelope, method="POST",
                                     headers={"Content-Type": "application/soap+xml; charset=utf-8"})
        opener = self._digest_opener if digest else self._plain_opener
        try:
            with opener.open(req, timeout=self.timeout) as resp:
                data = resp.read()
        except urllib.error.HTTPError as exc:
            data = exc.read()
            if exc.code == 401 and b"Fault" not in (data or b""):
                raise OnvifAuthError("identifiants refusés par la caméra (utilisateur / mot de passe)")
            if not data:
                raise OnvifError(f"HTTP {exc.code} sur {urlparse(url).path}")
        except (urllib.error.URLError, OSError) as exc:
            raise OnvifError(f"caméra injoignable en ONVIF ({self.ip}:{self.port}) : {getattr(exc, 'reason', exc)}")
        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            raise OnvifError("réponse ONVIF illisible")
        fault = _find(root, "Fault")
        if fault is not None:
            reason = _child_text(fault, "Text") or _child_text(fault, "Value") or "erreur inconnue"
            if "auth" in reason.lower() or "NotAuthorized" in ET.tostring(fault, encoding="unicode"):
                raise OnvifAuthError("identifiants refusés par la caméra (utilisateur / mot de passe)")
            raise OnvifError(f"la caméra a refusé la commande : {reason}")
        return root

    def _fix_host(self, xaddr):
        """Certaines caméras annoncent une IP interne : on garde le chemin mais on vise l'IP connue."""
        if not xaddr:
            return None
        p = urlparse(xaddr.split()[0])
        return f"http://{self.ip}:{self.port}{p.path or '/onvif/device_service'}"

    # ------------------------------------------------------------ connexion
    def connect(self):
        # 1. Horloge de la caméra (sans authentification) pour éviter les refus de jeton
        try:
            root = self._call(self.device_url, "<tds:GetSystemDateAndTime/>", auth=False)
            utc = _find(root, "UTCDateTime")
            if utc is not None:
                cam = datetime(int(_child_text(utc, "Year")), int(_child_text(utc, "Month")),
                               int(_child_text(utc, "Day")), int(_child_text(utc, "Hour")),
                               int(_child_text(utc, "Minute")), int(_child_text(utc, "Second")),
                               tzinfo=timezone.utc)
                self.clock_offset = cam - datetime.now(timezone.utc)
        except (OnvifError, ValueError, TypeError):
            pass

        # 2. Adresses des services
        root = self._call(self.device_url,
                          "<tds:GetCapabilities><tds:Category>All</tds:Category></tds:GetCapabilities>")
        caps = _find(root, "Capabilities")
        media = _find(caps, "Media") if caps is not None else None
        ptz = _find(caps, "PTZ") if caps is not None else None
        self.media_url = self._fix_host(_child_text(media, "XAddr")) or self.device_url
        self.ptz_url = self._fix_host(_child_text(ptz, "XAddr")) if ptz is not None else None

        # 3. Profil vidéo qui porte une configuration PTZ
        root = self._call(self.media_url, "<trt:GetProfiles/>")
        profiles = [p for p in _find_all(root, "Profiles") if p.get("token")]
        if not profiles:
            raise OnvifError("aucun profil vidéo ONVIF trouvé")
        with_ptz = [p for p in profiles if _find(p, "PTZConfiguration") is not None]
        self.profile_token = (with_ptz or profiles)[0].get("token")
        if self.ptz_url is None and with_ptz:
            self.ptz_url = self.device_url
        self.ready = True
        return self

    @property
    def has_ptz(self):
        return self.ready and self.ptz_url is not None

    def _require_ptz(self):
        if not self.has_ptz:
            raise OnvifError("cette caméra n'est pas motorisée (pas de service PTZ)")

    # ------------------------------------------------------------------ PTZ
    def move(self, pan=0.0, tilt=0.0, zoom=0.0):
        self._require_ptz()
        vel = ""
        if pan or tilt:
            vel += f'<tt:PanTilt x="{pan:.2f}" y="{tilt:.2f}"/>'
        if zoom:
            vel += f'<tt:Zoom x="{zoom:.2f}"/>'
        self._call(self.ptz_url, f"<tptz:ContinuousMove><tptz:ProfileToken>{escape(self.profile_token)}"
                                 f"</tptz:ProfileToken><tptz:Velocity>{vel}</tptz:Velocity></tptz:ContinuousMove>")

    def stop(self):
        self._require_ptz()
        self._call(self.ptz_url, f"<tptz:Stop><tptz:ProfileToken>{escape(self.profile_token)}</tptz:ProfileToken>"
                                 "<tptz:PanTilt>true</tptz:PanTilt><tptz:Zoom>true</tptz:Zoom></tptz:Stop>")

    def home(self):
        self._require_ptz()
        self._call(self.ptz_url, f"<tptz:GotoHomePosition><tptz:ProfileToken>{escape(self.profile_token)}"
                                 "</tptz:ProfileToken></tptz:GotoHomePosition>")

    def presets(self):
        self._require_ptz()
        root = self._call(self.ptz_url, f"<tptz:GetPresets><tptz:ProfileToken>{escape(self.profile_token)}"
                                        "</tptz:ProfileToken></tptz:GetPresets>")
        out = []
        for p in _find_all(root, "Preset"):
            if p.get("token"):
                out.append({"token": p.get("token"), "name": _child_text(p, "Name") or f"Position {p.get('token')}"})
        return out

    def goto_preset(self, token):
        self._require_ptz()
        self._call(self.ptz_url, f"<tptz:GotoPreset><tptz:ProfileToken>{escape(self.profile_token)}</tptz:ProfileToken>"
                                 f"<tptz:PresetToken>{escape(str(token))}</tptz:PresetToken></tptz:GotoPreset>")

    def set_preset(self, name):
        self._require_ptz()
        self._call(self.ptz_url, f"<tptz:SetPreset><tptz:ProfileToken>{escape(self.profile_token)}</tptz:ProfileToken>"
                                 f"<tptz:PresetName>{escape(name)}</tptz:PresetName></tptz:SetPreset>")


# Cache des connexions ONVIF par caméra (la découverte coûte 3 requêtes, on ne la refait pas à chaque clic)
_CACHE = {}
_LOCK = threading.Lock()


def get_onvif(cam):
    key = cam["id"]
    sig = (cam["ip"], cam.get("onvif_port"), cam.get("username"), cam.get("password"))
    with _LOCK:
        entry = _CACHE.get(key)
        if entry and entry[0] == sig and time.time() - entry[2] < 600:
            return entry[1]
    oc = OnvifCamera(cam["ip"], cam.get("onvif_port") or 80, cam.get("username"), cam.get("password")).connect()
    with _LOCK:
        _CACHE[key] = (sig, oc, time.time())
    return oc


def forget(cam_id):
    with _LOCK:
        _CACHE.pop(cam_id, None)
