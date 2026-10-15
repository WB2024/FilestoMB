// ==UserScript==
// @name         FilesToMB helper
// @namespace    https://github.com/WB2024/FilesToMB
// @version      __VERSION__
// @description  Companion to your FilesToMB server: attaches local cover art on MusicBrainz's add-cover-art page and sends newly created entity IDs back to FilesToMB.
// @match        https://musicbrainz.org/*
// @match        https://beta.musicbrainz.org/*
// @match        __BASE_URL__/*
// @connect      __HOST__
// @grant        GM_xmlhttpRequest
// @grant        GM_addStyle
// @run-at       document-idle
// @updateURL    __BASE_URL__/filestomb.user.js
// @downloadURL  __BASE_URL__/filestomb.user.js
// ==/UserScript==

(function () {
  'use strict';
  const BASE = '__BASE_URL__';
  const VERSION = '__VERSION__';

  // On the FilesToMB app itself: just announce that we're installed.
  if (location.href.startsWith(BASE)) {
    document.documentElement.dataset.filestombUserscript = VERSION;
    return;
  }

  const call = (method, path, { json, blob } = {}) => new Promise((resolve, reject) => {
    GM_xmlhttpRequest({
      method,
      url: BASE + path,
      headers: json ? { 'Content-Type': 'application/json' } : {},
      data: json ? JSON.stringify(json) : undefined,
      responseType: blob ? 'blob' : 'json',
      onload: (r) => (r.status < 400 ? resolve(r.response) : reject(new Error(`FilesToMB returned ${r.status}`))),
      onerror: () => reject(new Error('Could not reach your FilesToMB server')),
    });
  });

  GM_addStyle(`
    .fmb-pill{position:fixed;right:18px;bottom:18px;z-index:99999;display:flex;align-items:center;gap:10px;
      padding:10px 16px;border-radius:999px;border:1px solid #8c6a2a;background:#181410;color:#ece0c6;
      font:600 13px system-ui,sans-serif;box-shadow:0 10px 30px -8px #000;cursor:pointer}
    .fmb-pill:hover{border-color:#ebc26e}
    .fmb-pill.ok{border-color:#86b36b;cursor:default}
    .fmb-pill.err{border-color:#d9684f}
    .fmb-banner{margin:12px 0;padding:12px 16px;border-radius:8px;border:1px solid #8c6a2a;background:#181410;color:#ece0c6;font:14px system-ui,sans-serif}
    .fmb-banner b{color:#ebc26e}
  `);

  const el = (tag, cls, text) => { const e = document.createElement(tag); e.className = cls; if (text) e.textContent = text; return e; };
  const waitFor = (fn, ms = 8000) => new Promise((resolve) => {
    const start = Date.now();
    (function tick() {
      const v = fn();
      if (v) return resolve(v);
      if (Date.now() - start > ms) return resolve(null);
      setTimeout(tick, 150);
    })();
  });

  const m = location.pathname.match(/^\/(artist|label|release-group|release)\/([0-9a-f-]{36})(\/[^/]*)?\/?$/i);
  if (!m) return;
  const [, entity, mbid, sub] = m;

  (async function main() {
    let job;
    try { job = await call('GET', '/api/job'); } catch { return; }
    if (!job || !job.active) return;

    if (entity === 'release' && sub === '/add-cover-art') attachCover(job);
    else if (!sub) capturePill(job);
  })();

  const norm = (t) => [...(t || '').toLowerCase()].filter((c) => /[\p{L}\p{N}]/u.test(c)).join('');
  const pageName = () => ((document.querySelector('h1 bdi') || document.querySelector('h1') || {}).textContent || '').trim();

  // Entity page -> hand the MBID back to FilesToMB. If this is the entity the
  // user was just creating (FilesToMB told us its name), do it automatically;
  // otherwise leave a one-click button.
  function capturePill(job) {
    const send = async (pill, auto) => {
      try {
        await call('POST', '/api/job/capture', { json: { entity, mbid, name: pageName() } });
        pill.textContent = auto ? '✓ Sent to FilesToMB automatically. You can close this tab.' : '✓ Sent to FilesToMB. Switch back to the app.';
        pill.classList.add('ok');
      } catch (e) {
        pill.textContent = `✗ ${e.message}`;
        pill.classList.add('err');
      }
    };
    const pill = el('div', 'fmb-pill', `➕ Use this ${entity.replace('-', ' ')} in FilesToMB`);
    pill.title = `Working on: ${job.title}`;
    pill.addEventListener('click', () => { if (!pill.classList.contains('ok')) send(pill, false); });
    document.body.append(pill);

    const expected = (job.names || {})[entity];
    if ((job.awaiting || []).includes(entity) && expected && norm(pageName()) === norm(expected)) {
      pill.textContent = 'Sending to FilesToMB…';
      send(pill, true);
    }
  }

  // add-cover-art page -> attach the album's cover to MusicBrainz's own file input.
  async function attachCover(job) {
    const host = await waitFor(() => document.querySelector('#add-cover-art'));
    if (!host) return;
    const banner = el('div', 'fmb-banner');
    host.before(banner);
    if (!job.has_cover) { banner.textContent = 'FilesToMB: no cover art was found for this album, so nothing to attach.'; return; }
    banner.textContent = 'FilesToMB: fetching cover art…';
    try {
      const blob = await call('GET', `/api/cover?path=${encodeURIComponent(job.path)}`, { blob: true });
      const name = job.cover_filename || 'cover.jpg';
      const file = new File([blob], name, { type: blob.type || 'image/jpeg' });
      const input = await waitFor(() => document.querySelector('input.add-files[type=file]'));
      if (!input) throw new Error('could not find the file input on this page');
      const dt = new DataTransfer();
      dt.items.add(file);
      input.files = dt.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));

      // MusicBrainz renders the "types" checkboxes once the file is queued; tick "Front".
      const front = await waitFor(() => [...document.querySelectorAll('.cover-art-type-checkboxes label')]
        .find((l) => l.textContent.trim() === 'Front')?.querySelector('input'), 4000);
      if (front && !front.checked) front.click();

      banner.innerHTML = `FilesToMB attached <b></b> and ticked “Front”. Check it looks right, then click <b>Enter edit</b>.`;
      banner.querySelector('b').textContent = name;
    } catch (e) {
      banner.textContent = `FilesToMB couldn't attach the cover automatically (${e.message}). Use the Download button in the app and drop the file here instead.`;
    }
  }
})();
