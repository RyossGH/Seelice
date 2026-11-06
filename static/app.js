// Seelice — fonctions partagées
const Seelice = (() => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  /**
   * Boucle d'affichage live : récupère l'image suivante du flux partagé côté serveur
   * (le serveur attend une image plus récente que `after`, donc le rythme suit le fps du flux).
   * On utilise fetch plutôt qu'un flux MJPEG pour ne pas saturer la limite de 6 connexions
   * simultanées par serveur des navigateurs quand la mosaïque contient beaucoup de caméras.
   */
  function liveLoop(img, overlay, camId, quality, isActive, fpsEl) {
    const getQ = typeof quality === 'function' ? quality : () => quality;
    let after = 0, lastQ = getQ(), url = null, frames = 0, t0 = performance.now();

    (async () => {
      while (true) {
        if (!isActive() || document.hidden) { await sleep(800); continue; }
        const q = getQ();
        if (q !== lastQ) { after = 0; lastQ = q; }
        try {
          const r = await fetch(`/api/frame/${camId}?q=${q}&after=${after}`, { cache: 'no-store' });
          if (r.status === 200) {
            after = parseInt(r.headers.get('X-Frame-Id') || '0', 10);
            const blob = await r.blob();
            const old = url; url = URL.createObjectURL(blob);
            img.src = url;
            if (old) setTimeout(() => URL.revokeObjectURL(old), 1000);
            overlay.hidden = true;
            frames++;
            if (fpsEl && performance.now() - t0 > 2000) {
              fpsEl.textContent = (frames * 1000 / (performance.now() - t0)).toFixed(1) + ' img/s · ' + (q === 'main' ? 'HD' : 'léger');
              frames = 0; t0 = performance.now();
            }
          } else if (r.status === 401) {
            location.href = '/login'; return;
          } else {
            let msg = 'Pas de signal';
            try { msg = (await r.json()).error || msg; } catch (e) {}
            overlay.textContent = msg.charAt(0).toUpperCase() + msg.slice(1); overlay.hidden = false;
            after = 0; await sleep(2000);
          }
        } catch (e) {
          overlay.textContent = 'Serveur injoignable'; overlay.hidden = false; await sleep(3000);
        }
      }
    })();

    return { reset() { after = 0; } };
  }

  function toast(msg, isError) {
    const t = document.createElement('div');
    t.className = 'toast' + (isError ? ' error' : '');
    t.innerHTML = msg;
    document.body.appendChild(t);
    setTimeout(() => t.classList.add('show'), 10);
    setTimeout(() => { t.classList.remove('show'); setTimeout(() => t.remove(), 300); }, 3500);
  }

  function bindCaptureButtons() {
    document.querySelectorAll('[data-capture]').forEach(btn => btn.addEventListener('click', async e => {
      e.preventDefault();
      const label = btn.textContent; btn.disabled = true; btn.textContent = '…';
      try {
        const r = await fetch(`/api/cameras/${btn.dataset.capture}/capture`, { method: 'POST' });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error);
        toast(`Capture enregistrée — <a href="${data.url}" target="_blank">voir</a>`);
      } catch (err) {
        toast('Capture impossible : ' + err.message, true);
      } finally { btn.disabled = false; btn.textContent = label; }
    }));
  }

  return { liveLoop, bindCaptureButtons, toast };
})();
