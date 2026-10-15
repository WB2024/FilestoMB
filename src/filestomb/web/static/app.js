/* FilesToMB web UI: vanilla JS, no build step. */
'use strict';

// ---------------------------------------------------------------- helpers
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const ICON = {
  folder: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
  music: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/></svg>',
  artist: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
  label: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M20 12 12 20a2 2 0 0 1-3 0l-6-6a2 2 0 0 1 0-3l8-8h6a1 1 0 0 1 1 1z"/><circle cx="15.5" cy="8.5" r="1"/></svg>',
  rg: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r=".6"/></svg>',
  release: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2.5"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12 5 5 9-10"/></svg>',
  alert: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8v5m0 3.5v.01"/><path d="M10.3 3.9 2.4 17.5A2 2 0 0 0 4.1 20.5h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>',
  plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
  down: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11m0 0-4-4m4 4 4-4M5 20h14"/></svg>',
  ext: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6m0-6L10 14M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>',
  up: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V6m0 0-5 5m5-5 5 5"/></svg>',
  back: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5m0 0 6-6m-6 6 6 6"/></svg>',
  chev: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 6 6 6-6 6"/></svg>',
};

const ENTITIES = {
  artist: { name: 'Artist', icon: ICON.artist, view: (id) => `https://musicbrainz.org/artist/${id}` },
  label: { name: 'Label', icon: ICON.label, view: (id) => `https://musicbrainz.org/label/${id}` },
  'release-group': { name: 'Release Group', icon: ICON.rg, view: (id) => `https://musicbrainz.org/release-group/${id}` },
  release: { name: 'Release', icon: ICON.release, view: (id) => `https://musicbrainz.org/release/${id}` },
};
// Dependency order: parents before the entities that reference them.
const SUBMIT_ORDER = ['label', 'artist', 'release-group', 'release'];
const REVIEW_ORDER = ['artist', 'label', 'release-group', 'release'];

const state = {
  config: null,
  auth: { configured: false, logged_in: false, username: '' },
  view: 'browse',
  browse: null,      // last /api/browse response
  filter: '',
  album: null,       // scanned + edited album
  cover: null,
  matches: null,     // { entity: {status, query, candidates, selected, createNew} }
  checking: false,
  opened: {},        // entities whose seeded form was opened
  maxStep: 0,
};

// ---------------------------------------------------------------- api / ui plumbing
async function api(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try { const j = await res.json(); if (j.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch { /* keep default */ }
    throw new Error(msg);
  }
  return res.json();
}

function toast(message, kind = '') {
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.textContent = message;
  $('#toasts').append(el);
  setTimeout(() => el.remove(), kind === 'error' ? 8000 : 4500);
}

const app = () => $('#app');
const dlg = () => $('#dlg');
function openDialog(html) { dlg().innerHTML = html; if (!dlg().open) dlg().showModal(); }
function closeDialog() { if (dlg().open) dlg().close(); }
document.addEventListener('click', (e) => { if (e.target === dlg()) closeDialog(); });

function busy(btn, on, label) {
  if (!btn) return;
  if (on) { btn.dataset.label = btn.innerHTML; btn.disabled = true; btn.innerHTML = `<span class="spinner"></span> ${esc(label || '')}`; }
  else { btn.disabled = false; btn.innerHTML = btn.dataset.label ?? btn.innerHTML; }
}

// Open a window synchronously inside the click handler (popup blockers
// require a user gesture), then point it at MusicBrainz once the server
// has built the seeded URL or form.
function openBlank() {
  const w = window.open('about:blank', `fmb-${Date.now()}`);
  if (!w) toast('Your browser blocked the new tab. Allow pop-ups for this site and try again.', 'error');
  else w.document.write('<body style="background:#0b0907;color:#ece0c6;font:16px system-ui;display:grid;place-items:center;height:100vh;margin:0">Opening MusicBrainz&hellip;</body>');
  return w;
}
function postForm(win, action, fields) {
  const form = document.createElement('form');
  form.method = 'post'; form.action = action; form.target = win.name; form.style.display = 'none';
  for (const [k, v] of Object.entries(fields)) {
    const input = document.createElement('input');
    input.type = 'hidden'; input.name = k; input.value = v; form.append(input);
  }
  document.body.append(form); form.submit(); form.remove();
}

// ---------------------------------------------------------------- chrome
function renderChrome() {
  const steps = [['browse', 'Browse'], ['review', 'Review'], ['submit', 'Submit']];
  const idx = steps.findIndex(([k]) => k === state.view);
  $('#stepper').innerHTML = steps.map(([key, label], i) => {
    const cls = i === idx ? 'active' : (i <= state.maxStep && i < idx ? 'done' : (i <= state.maxStep ? 'done' : ''));
    const clickable = i !== idx && i <= state.maxStep && (key === 'browse' || state.album);
    return `<button class="step ${cls}" data-go="${clickable ? key : ''}" ${clickable ? '' : 'tabindex="-1"'}><span class="num">${i < idx || (i <= state.maxStep && i !== idx) ? '✓' : i + 1}</span>${label}</button>`;
  }).join('');
  $$('#stepper [data-go]').forEach((b) => b.dataset.go && b.addEventListener('click', () => go(b.dataset.go)));

  const a = state.auth;
  $('#auth-chip').innerHTML = `<button class="chip ${userscriptInstalled() ? (userscriptOutdated() ? 'warn' : 'on') : ''}" id="us-btn" title="Browser userscript"><span class="dot"></span>Userscript</button> <button class="chip ${a.logged_in ? 'on' : ''}" id="auth-btn"><span class="dot"></span>${a.logged_in ? esc(a.username || 'Logged in') : 'Log in to MusicBrainz'}</button>`;
  $('#auth-btn').addEventListener('click', openLogin);
  $('#us-btn').addEventListener('click', openUserscript);
}

const userscriptInstalled = () => !!document.documentElement.dataset.filestombUserscript;
const userscriptOutdated = () => userscriptInstalled() && !!state.config && document.documentElement.dataset.filestombUserscript !== state.config.userscript_version;

function go(view) {
  state.view = view;
  state.maxStep = Math.max(state.maxStep, ['browse', 'review', 'submit'].indexOf(view));
  renderChrome();
  ({ browse: renderBrowse, review: renderReview, submit: renderSubmit })[view]();
  window.scrollTo({ top: 0 });
}

// ---------------------------------------------------------------- browse
async function loadBrowse(path) {
  app().innerHTML = `<section class="view"><div class="folder-grid">${'<div class="skeleton"></div>'.repeat(9)}</div></section>`;
  try {
    state.browse = await api('GET', `/api/browse?path=${encodeURIComponent(path)}`);
    state.filter = '';
    renderBrowse();
  } catch (e) {
    toast(e.message, 'error');
    if (path) loadBrowse('');
    else app().innerHTML = `<div class="empty card pad"><h2>Can't open the library</h2><p>${esc(e.message)}</p></div>`;
  }
}

function renderBrowse() {
  if (!state.browse) return loadBrowse(state.config.last_path || '');
  const b = state.browse;
  const q = state.filter.toLowerCase();
  const dirs = b.dirs.filter((d) => d.name.toLowerCase().includes(q));
  const parent = b.crumbs.length > 1 ? b.crumbs[b.crumbs.length - 2].path : null;

  app().innerHTML = `
  <section class="view">
    <div class="page-head">
      <div><h2>Choose an album</h2><p>Open a folder of tagged audio files. Folders with music are marked and scan on click.</p></div>
    </div>
    <div class="card toolbar">
      <button class="btn small" id="up" ${parent === null ? 'disabled' : ''}>${ICON.up} Up</button>
      <div class="crumbs">${b.crumbs.map((c, i) => `${i ? '<span class="sep">/</span>' : ''}<button data-path="${esc(c.path)}" class="${i === b.crumbs.length - 1 ? 'cur' : ''}">${esc(c.name)}</button>`).join('')}</div>
      <input class="search" id="filter" type="text" placeholder="Filter folders…" value="${esc(state.filter)}" aria-label="Filter folders">
      <button class="btn ${b.audio_files ? 'primary' : ''}" id="scan-here">${ICON.music} ${b.audio_files ? `Scan this folder (${b.audio_files} file${b.audio_files === 1 ? '' : 's'})` : 'Scan this folder'}</button>
    </div>
    ${dirs.length ? `<div class="folder-grid" id="grid">${dirs.map((d) => folderCard(d)).join('')}</div>`
      : `<div class="empty card"><img src="/static/logo.png" alt=""><p>${b.dirs.length ? 'No folders match that filter.' : 'No sub-folders here.'}</p></div>`}
  </section>`;

  $('#up').addEventListener('click', () => loadBrowse(parent));
  $$('.crumbs button').forEach((c) => c.addEventListener('click', () => loadBrowse(c.dataset.path)));
  $('#scan-here').addEventListener('click', () => scan(b.path));
  const f = $('#filter');
  f.addEventListener('input', () => {
    state.filter = f.value;
    const grid = $('#grid');
    const query = f.value.toLowerCase();
    if (grid) $$('.folder-wrap', grid).forEach((w) => { w.hidden = !w.dataset.name.includes(query); });
  });
  $$('[data-open]').forEach((el) => el.addEventListener('click', () => loadBrowse(el.dataset.open)));
  $$('[data-scan]').forEach((el) => el.addEventListener('click', () => scan(el.dataset.scan)));
}

function folderCard(d) {
  const attr = `data-name="${esc(d.name.toLowerCase())}"`;
  if (d.has_audio) {
    return `<div class="folder-wrap album" ${attr}>
      <button class="folder album" data-scan="${esc(d.path)}" title="Scan ${esc(d.name)}"><span class="ico">${ICON.music}</span><span class="name">${esc(d.name)}</span></button>
      <button class="btn small ghost into" data-open="${esc(d.path)}" title="Browse inside" aria-label="Browse inside ${esc(d.name)}">Open ${ICON.chev}</button>
    </div>`;
  }
  return `<div class="folder-wrap" ${attr}><button class="folder" data-open="${esc(d.path)}"><span class="ico">${ICON.folder}</span><span class="name">${esc(d.name)}</span></button></div>`;
}

async function scan(path) {
  app().innerHTML = `<div class="scanning"><span class="spinner"></span><div>Reading tags…</div></div>`;
  try {
    const album = await api('POST', '/api/scan', { path });
    state.album = album;
    state.cover = album.cover;
    state.matches = null;
    state.opened = {};
    go('review');
    if (album.tagged_release_mbid) toast('These files are already tagged with a MusicBrainz release ID.', 'ok');
    checkMusicBrainz();
  } catch (e) {
    toast(e.message, 'error');
    renderBrowse();
  }
}

// ---------------------------------------------------------------- matching
async function checkMusicBrainz({ keepSelections = false } = {}) {
  const a = state.album;
  if (!a.title.trim() || !a.artist.trim()) { toast('Title and artist are needed to search MusicBrainz.', 'warn'); return; }
  state.checking = true; refreshMatchUI();
  try {
    const found = await api('POST', '/api/match', { title: a.title, artist: a.artist, label: a.label });
    const old = state.matches || {};
    const next = {};
    for (const [key, r] of Object.entries(found)) {
      const prev = old[key];
      const keep = keepSelections && prev && (prev.selected || prev.createNew);
      next[key] = keep
        ? { ...r, selected: prev.selected, createNew: prev.createNew, candidates: mergeCandidates(prev, r) }
        : { ...r, selected: r.selected_mbid, createNew: false };
    }
    state.matches = next;
    if (a.tagged_release_mbid && next.release && !next.release.selected) next.release.selected = a.tagged_release_mbid;
  } catch (e) {
    toast(`MusicBrainz search failed: ${e.message}`, 'error');
  } finally {
    state.checking = false;
    refreshMatchUI();
  }
}
function mergeCandidates(prev, fresh) {
  const ids = new Set(fresh.candidates.map((c) => c.mbid));
  const extra = prev.candidates.filter((c) => !ids.has(c.mbid) && c.mbid === prev.selected);
  return [...fresh.candidates, ...extra];
}
// What the submit step should treat this entity as.
function effective(key) {
  const m = state.matches?.[key];
  if (!m) return 'unchecked';
  if (m.selected) return 'existing';
  if (m.createNew || m.status === 'missing') return 'missing';
  return 'ambiguous';
}

// ---------------------------------------------------------------- review
function renderReview() {
  const a = state.album;
  app().innerHTML = `
  <section class="view">
    <div class="page-head">
      <div><h2>${esc(a.title || a.folder_name)}</h2><p>${esc(a.artist)} · ${a.tracks.length} track${a.tracks.length === 1 ? '' : 's'} · <span class="note">${esc(a.path || '/')}</span></p></div>
    </div>
    <div class="review-grid">
      <aside class="sticky">
        <div class="card pad">
          <div id="cover-card">${coverCardHTML()}</div>
          ${[['title', 'Title'], ['artist', 'Artist'], ['date', 'Date'], ['label', 'Label'], ['catalog_number', 'Catalog #'], ['barcode', 'Barcode']]
            .map(([k, l]) => `<label class="field"><span>${l}</span><input type="text" data-field="${k}" value="${esc(a[k])}" ${k === 'date' ? 'placeholder="YYYY or YYYY-MM-DD"' : ''}></label>`).join('')}
        </div>
      </aside>
      <div>
        ${a.tagged_release_mbid ? `<div class="banner">${ICON.check.replace('<svg', '<svg width="18" height="18"')}<span>These files already carry a MusicBrainz release ID: <a href="${ENTITIES.release.view(a.tagged_release_mbid)}" target="_blank" rel="noopener">${esc(a.tagged_release_mbid.slice(0, 8))}… ${ICON.ext.replace('<svg', '<svg width="12" height="12"')}</a></span></div>` : ''}
        <div class="page-head" style="margin-bottom:10px"><h3>MusicBrainz matches</h3><button class="btn" id="check">${ICON.search} Check MusicBrainz</button></div>
        <div id="matches"></div>
        <div class="page-head" style="margin:26px 0 10px"><h3>Tracks</h3><span class="note">Edit titles or numbering before they're seeded</span></div>
        <div class="card" style="overflow:auto"><table class="tracks"><thead><tr><th>Disc</th><th>#</th><th>Title</th><th style="text-align:right">Length</th></tr></thead><tbody>
          ${a.tracks.map((t, i) => `<tr><td class="d"><input type="text" data-track="${i}" data-k="disc_number" value="${esc(t.disc_number)}"></td><td class="n"><input type="text" data-track="${i}" data-k="track_number" value="${esc(t.track_number)}"></td><td><input type="text" data-track="${i}" data-k="title" value="${esc(t.title)}"></td><td class="len">${fmtLen(t.length_ms)}</td></tr>`).join('')}
        </tbody></table></div>
      </div>
    </div>
  </section>
  <div class="actionbar"><div class="inner">
    <button class="btn" id="back">${ICON.back} Choose another album</button>
    <button class="btn primary" id="next">Continue to submit ${ICON.chev}</button>
  </div></div>`;

  $$('[data-field]').forEach((i) => i.addEventListener('input', () => { a[i.dataset.field] = i.value; }));
  $$('[data-track]').forEach((i) => i.addEventListener('input', () => { a.tracks[+i.dataset.track][i.dataset.k] = i.value; }));
  wireCover();
  $('#check').addEventListener('click', () => checkMusicBrainz({ keepSelections: true }));
  $('#back').addEventListener('click', () => go('browse'));
  $('#next').addEventListener('click', () => {
    if (!state.matches) { toast('Check MusicBrainz first.', 'warn'); return; }
    go('submit');
  });
  refreshMatchUI();
}

const coverUrl = (download = false) => `/api/cover?path=${encodeURIComponent(state.album.path)}&v=${state.coverV || 0}${download ? '&download=1' : ''}`;
const coverHTML = () => (state.cover ? `<img src="${coverUrl()}" alt="Album cover">` : 'No cover art yet<br><small>Drop, paste or click to add one</small>');

// Cover card: preview + upload (client side) + pick-from-folder (server side).
function coverCardHTML() {
  const c = state.cover;
  return `<div class="cover drop" id="cover-drop" tabindex="0" role="button" aria-label="Upload cover art">${coverHTML()}<div class="drop-hint">Drop image to use as cover</div></div>
    <div class="cover-meta"><span>${c ? `${esc(c.filename)} · ${(c.bytes / 1024).toFixed(0)} KB${c.custom ? ' · yours' : ''}` : 'No cover art found'}</span>${c ? `<a href="${coverUrl(true)}" download>${ICON.down.replace('<svg', '<svg width="14" height="14"')} Download</a>` : ''}</div>
    ${coverActionsHTML()}`;
}
function coverActionsHTML() {
  return `<div class="cover-actions"><button class="btn small" data-cover="upload">${ICON.up} Upload…</button><button class="btn small" data-cover="pick">${ICON.folder} From folder…</button>${state.cover?.custom ? '<button class="btn small ghost" data-cover="reset">Reset</button>' : ''}<input type="file" id="cover-file" accept="image/jpeg,image/png,image/gif,image/webp" hidden></div>`;
}
function refreshCover() {
  if (state.view === 'review') { const card = $('#cover-card'); if (card) { card.innerHTML = coverCardHTML(); wireCover(); } }
  else if (state.view === 'submit') renderSubmit();
}
function wireCover() {
  const input = $('#cover-file');
  const drop = $('#cover-drop');
  $$('[data-cover]').forEach((b) => b.addEventListener('click', () => {
    if (b.dataset.cover === 'upload') input.click();
    else if (b.dataset.cover === 'pick') pickFromFolder();
    else resetCover();
  }));
  input.addEventListener('change', () => { if (input.files[0]) uploadCover(input.files[0]); });
  if (drop) {
    drop.addEventListener('click', () => input.click());
    drop.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } });
    ['dragenter', 'dragover'].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add('over'); }));
    ['dragleave', 'drop'].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove('over'); }));
    drop.addEventListener('drop', (e) => { const f = [...e.dataTransfer.files].find((x) => x.type.startsWith('image/')); if (f) uploadCover(f); else toast('That wasn\'t an image file.', 'warn'); });
  }
}
async function uploadCover(file) {
  if (file.size > 20 * 1024 * 1024) { toast('Image is larger than 20 MB.', 'error'); return; }
  try {
    const res = await fetch(`/api/cover?path=${encodeURIComponent(state.album.path)}&filename=${encodeURIComponent(file.name || 'cover')}`, { method: 'PUT', headers: { 'Content-Type': file.type || 'application/octet-stream' }, body: file });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    state.cover = await res.json(); state.coverV = Date.now();
    refreshCover(); toast('Cover art set.', 'ok');
  } catch (e) { toast(`Upload failed: ${e.message}`, 'error'); }
}
async function resetCover() {
  try {
    const { cover } = await api('DELETE', `/api/cover?path=${encodeURIComponent(state.album.path)}`);
    state.cover = cover; state.coverV = Date.now(); refreshCover(); toast('Back to the detected cover.');
  } catch (e) { toast(e.message, 'error'); }
}
async function pickFromFolder() {
  openDialog('<div class="dlg-head"><h3>Choose cover from folder</h3></div><div class="dlg-body"><div class="scanning" style="padding:30px 0"><span class="spinner"></span></div></div>');
  try {
    const { images } = await api('GET', `/api/images?path=${encodeURIComponent(state.album.path)}`);
    const p = encodeURIComponent(state.album.path);
    openDialog(`<div class="dlg-head"><h3>Choose cover from folder</h3><p>Images found inside ${esc(state.album.folder_name)}.</p></div>
      <div class="dlg-body">${images.length ? `<div class="imggrid">${images.map((i) => `<button data-img="${esc(i.name)}" title="${esc(i.name)}"><img loading="lazy" src="/api/image?path=${p}&name=${encodeURIComponent(i.name)}" alt=""><span>${esc(i.name.split('/').pop())}</span><small>${(i.bytes / 1024).toFixed(0)} KB</small></button>`).join('')}</div>` : '<p class="note">No image files were found in this folder. Use Upload to add one from your computer.</p>'}</div>
      <div class="dlg-foot"><button class="btn" id="dlg-cancel">Close</button></div>`);
    $('#dlg-cancel').addEventListener('click', closeDialog);
    $$('[data-img]').forEach((b) => b.addEventListener('click', async () => {
      try {
        state.cover = await api('POST', '/api/cover/use', { path: state.album.path, image: b.dataset.img });
        state.coverV = Date.now(); closeDialog(); refreshCover(); toast('Cover art set.', 'ok');
      } catch (e) { toast(e.message, 'error'); }
    }));
  } catch (e) { closeDialog(); toast(e.message, 'error'); }
}
// Paste an image from the clipboard anywhere on the review/submit screens.
document.addEventListener('paste', (e) => {
  if (!state.album || !['review', 'submit'].includes(state.view) || /^(INPUT|TEXTAREA)$/.test(document.activeElement?.tagName)) return;
  const f = [...(e.clipboardData?.files || [])].find((x) => x.type.startsWith('image/'));
  if (f) { e.preventDefault(); uploadCover(f); }
});
const fmtLen = (ms) => (ms ? `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, '0')}` : '');

function refreshMatchUI() {
  const host = $('#matches');
  const btn = $('#check');
  if (btn) { btn.disabled = state.checking; btn.innerHTML = state.checking ? `<span class="spinner"></span> Searching…` : `${ICON.search} Check MusicBrainz`; }
  if (!host) return;
  if (state.checking && !state.matches) {
    host.innerHTML = REVIEW_ORDER.map(() => '<div class="skeleton" style="margin-bottom:14px;height:74px"></div>').join('');
    return;
  }
  if (!state.matches) { host.innerHTML = `<div class="card pad note">Not checked yet.</div>`; return; }
  host.innerHTML = REVIEW_ORDER.filter((k) => state.matches[k]).map(entityCard).join('');

  $$('[data-pick]', host).forEach((r) => r.addEventListener('change', () => {
    const [key, mbid] = r.dataset.pick.split('|');
    const m = state.matches[key];
    if (mbid === '__new__') { m.selected = null; m.createNew = true; } else { m.selected = mbid; m.createNew = false; }
    refreshMatchUI();
  }));
  $$('[data-manual]', host).forEach((form) => form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const key = form.dataset.manual;
    try {
      const { mbid } = await api('POST', '/api/resolve-mbid', { name: $('input', form).value });
      const m = state.matches[key];
      if (!m.candidates.some((c) => c.mbid === mbid)) m.candidates.unshift({ mbid, name: 'Pasted ID', score: 100, disambiguation: mbid.slice(0, 8) + '…' });
      m.selected = mbid; m.createNew = false;
      refreshMatchUI();
    } catch (err) { toast(err.message, 'error'); }
  }));
}

function entityCard(key) {
  const m = state.matches[key];
  const info = ENTITIES[key];
  const status = effective(key);
  const label = { existing: 'Using existing', missing: 'Will create', ambiguous: 'Needs a pick', unchecked: 'Unchecked' }[status];
  const row = (id, body, score) => `<label class="cand ${(id === '__new__' ? m.createNew : m.selected === id) ? 'sel' : ''}">
      <input type="radio" name="pick-${key}" data-pick="${key}|${esc(id)}" ${(id === '__new__' ? m.createNew : m.selected === id) ? 'checked' : ''}>
      <div class="nm">${body}</div>
      ${score == null ? '<span></span>' : `<div class="bar-wrap"><div class="bar"><i style="width:${Math.min(100, score)}%"></i></div>${Math.round(score)}%</div>`}
    </label>`;
  return `<div class="card entity">
    <div class="entity-head"><span class="ico">${info.icon}</span><div class="t"><b>${info.name}</b><small>${esc(m.query)}</small></div><span class="pill ${status}">${label}</span></div>
    <div class="cands">
      ${m.candidates.map((c) => row(c.mbid, `<b>${esc(c.name)}</b>${c.disambiguation ? `<small>${esc(c.disambiguation)}</small>` : ''}${c.extra ? `<small>${esc(c.extra)}</small>` : ''}<a href="${info.view(c.mbid)}" target="_blank" rel="noopener">view ↗</a>`, c.score)).join('')}
      ${row('__new__', `<b>None of these</b><small>create a new ${info.name.toLowerCase()}</small>`, null)}
      <form class="manual" data-manual="${key}"><input type="text" placeholder="…or paste a MusicBrainz ID / URL" aria-label="MusicBrainz ID for ${info.name}"><button class="btn small" type="submit">Use</button></form>
    </div>
  </div>`;
}

// ---------------------------------------------------------------- submit
async function pushJob() {
  const a = state.album;
  try {
    await api('PUT', '/api/job', { path: a.path, title: a.title, artist: a.artist, release_mbid: state.matches?.release?.selected || null, has_cover: !!state.cover, cover_filename: state.cover?.filename || null, awaiting: SUBMIT_ORDER.filter((k) => state.matches?.[k] && effective(k) === 'missing'), names: { artist: a.artist, label: a.label, 'release-group': a.title, release: a.title } });
  } catch { /* the userscript is optional */ }
}

function adopt(key, cand) {
  const m = state.matches[key];
  if (!m.candidates.some((x) => x.mbid === cand.mbid)) m.candidates.unshift(cand);
  m.selected = cand.mbid; m.createNew = false;
}

// Find a release group / release the user just created, by browsing from the
// parent entity. This reads MusicBrainz's database directly; unlike search it
// has no indexing delay. Returns true if anything new was found.
async function lookupCreated() {
  const m = state.matches;
  if (!m) return false;
  let changed = false;
  // Pass 2 only runs when pass 1 just found the release group, which lets
  // us look for its release straight away.
  for (let pass = 0; pass < 2; pass += 1) {
    const artist = m.artist?.selected;
    const group = m['release-group']?.selected;
    // Only adopt what the user has actually gone to create; an existing
    // same-named entity they chose to ignore must not be picked up.
    const wantRg = !!m['release-group'] && !group && !!state.opened['release-group'];
    const wantRel = !!m.release && !m.release.selected && !!state.opened.release;
    if (!(wantRg || wantRel) || !(artist || group)) break;

    const r = await api('POST', '/api/lookup', { title: state.album.title, artist_mbid: artist || null, release_group_mbid: group || null });
    let foundGroup = false;
    if (wantRg && r['release-group'].length === 1) {
      adopt('release-group', r['release-group'][0]);
      toast('Found your new release group on MusicBrainz.', 'ok');
      foundGroup = true; changed = true;
    }
    if (wantRel && r.release.length === 1) {
      adopt('release', r.release[0]);
      toast('Found your new release on MusicBrainz.', 'ok');
      changed = true;
    }
    if (!foundGroup || m.release?.selected) break;
  }
  return changed;
}

const anyMissing = () => !!state.matches && SUBMIT_ORDER.some((k) => state.matches[k] && effective(k) === 'missing');
let polling = false;
let ticks = 0;
let lastFullCheck = 0;

async function refreshSubmit({ full = false } = {}) {
  if (polling) return;
  polling = true;
  try {
    let changed = false;
    try { changed = await lookupCreated(); } catch { /* transient MusicBrainz error: try again next tick */ }
    if (full && anyMissing() && Date.now() - lastFullCheck > 10000) {
      lastFullCheck = Date.now();
      const before = JSON.stringify(SUBMIT_ORDER.map((k) => effective(k)));
      await checkMusicBrainz({ keepSelections: true });
      changed = changed || before !== JSON.stringify(SUBMIT_ORDER.map((k) => effective(k)));
    }
    if (changed && state.view === 'submit') renderSubmit();
  } finally { polling = false; }
}

// Every 2.5s on the Submit screen: pick up IDs the userscript captured on
// musicbrainz.org; every ~8s while something is still missing, look it up.
async function pollSubmit() {
  if (state.view !== 'submit' || document.hidden || !state.matches) return;
  ticks += 1;
  try {
    const { captures } = await api('GET', '/api/job/captures');
    if (captures.length) {
      for (const c of captures) {
        if (!state.matches[c.entity]) continue;
        adopt(c.entity, { mbid: c.mbid, name: c.name || 'Captured from MusicBrainz', score: 100, disambiguation: c.mbid.slice(0, 8) + '…' });
        toast(`${ENTITIES[c.entity].name} captured from MusicBrainz.`, 'ok');
      }
      renderSubmit();
      return;
    }
  } catch { /* ignore */ }
  if (ticks % 3 === 0 && anyMissing()) refreshSubmit();
}
setInterval(pollSubmit, 2500);

// Coming back from the MusicBrainz tab: check straight away, including a full search.
const onReturn = () => { if (state.view === 'submit' && !document.hidden && state.matches && anyMissing()) refreshSubmit({ full: true }); };
document.addEventListener('visibilitychange', onReturn);
window.addEventListener('focus', onReturn);

function openUserscript() {
  const on = userscriptInstalled();
  const installed = document.documentElement.dataset.filestombUserscript;
  const outdated = on && installed !== state.config.userscript_version;
  openDialog(`<div class="dlg-head"><h3>Browser userscript</h3><p>${outdated ? `<b style="color:var(--warn)">Update available</b>: you have v${esc(installed)}, the server has v${esc(state.config.userscript_version)}.` : on ? `Installed ✓ (v${esc(installed)})` : 'Optional. Needs Tampermonkey, Violentmonkey or similar.'}</p></div>
    <div class="dlg-body">
      <div class="stepnote"><span class="num">1</span><div><b>Cover art attaches itself.</b> On MusicBrainz's add-cover-art page the script fetches this album's cover from FilesToMB, drops it into the uploader and ticks “Front”.</div></div>
      <div class="stepnote"><span class="num">2</span><div><b>No manual re-check.</b> After you create an artist, label, release group or release, click <i>Use in FilesToMB</i> on its page and the ID flows back here.</div></div>
      <p class="note">Form fields themselves are pre-filled by MusicBrainz's own seeding, which is more reliable than editing the page. The script only handles what seeding can't. It never submits an edit for you.</p>
    </div>
    <div class="dlg-foot"><button class="btn" id="dlg-cancel">Close</button><a class="btn primary" href="/filestomb.user.js" target="_blank" rel="noopener">${ICON.down} ${outdated ? 'Update userscript' : on ? 'Reinstall' : 'Install userscript'}</a></div>`);
  $('#dlg-cancel').addEventListener('click', closeDialog);
}

function renderSubmit() {
  const a = state.album;
  pushJob();
  const steps = SUBMIT_ORDER.filter((k) => state.matches[k]);
  const relMbid = state.matches.release?.selected;
  const unresolved = steps.some((k) => effective(k) === 'ambiguous');

  app().innerHTML = `
  <section class="view">
    <div class="page-head">
      <div><h2>Submit to MusicBrainz</h2><p>MusicBrainz has no write API for new entities, so each button opens a pre-filled edit form in a new tab. Review it and submit while logged in there. Work top to bottom.</p></div>
      <button class="btn" id="recheck">${ICON.search} Re-check MusicBrainz</button>
    </div>
    <div class="timeline">
      ${(() => { const firstMissing = steps.find((k) => effective(k) === 'missing'); return steps.map((k, i) => timelineStep(k, i + 1, k === firstMissing)).join(''); })()}
    </div>
    ${unresolved ? '<p class="hint" style="margin-top:14px">Some matches still need a pick. Go back to Review to choose one or mark it as new.</p>' : ''}
    <div class="two-col">
      <div class="card pad">
        <h3>Cover art</h3>
        <p class="note">The Cover Art Archive has no upload API. Download the image, then drag it into the upload page.</p>
        <div class="cover-sm">
          <div class="cover drop" id="cover-drop" tabindex="0" role="button" aria-label="Upload cover art">${coverHTML()}<div class="drop-hint">Drop image</div></div>
          <div style="display:grid;gap:10px">
            ${state.cover ? `<a class="btn small" href="${coverUrl(true)}" download>${ICON.down} Download ${esc(state.cover.filename)}</a>` : '<span class="note">No cover art yet.</span>'}
            ${coverActionsHTML()}
            <button class="btn small" id="cover-open" ${relMbid ? '' : 'disabled'}>${ICON.ext} Open upload page</button>
            ${relMbid ? '' : '<span class="note">Needs a release ID first.</span>'}
          </div>
        </div>
      </div>
      <div class="card pad">
        <h3>Your collections</h3>
        <p class="note">File the release into one of your MusicBrainz collections.${state.auth.logged_in ? '' : ' Requires login.'}</p>
        <button class="btn" id="coll" ${relMbid ? '' : 'disabled'}>${ICON.plus} Add release to a collection</button>
        ${relMbid ? '' : '<p class="note" style="margin-bottom:0">Needs a release ID first.</p>'}
      </div>
    </div>
  </section>
  <div class="actionbar"><div class="inner"><button class="btn" id="back">${ICON.back} Back to review</button><span></span></div></div>`;

  $('#back').addEventListener('click', () => go('review'));
  $('#recheck').addEventListener('click', async (e) => {
    busy(e.currentTarget, true, 'Checking…');
    lastFullCheck = 0;
    try { await lookupCreated(); } catch { /* fall through to the search */ }
    await checkMusicBrainz({ keepSelections: true });
    renderSubmit();
    toast('Re-checked MusicBrainz.', 'ok');
  });
  $$('[data-create]').forEach((b) => b.addEventListener('click', () => createEntity(b.dataset.create)));
  $$('[data-review]').forEach((b) => b.addEventListener('click', () => go('review')));
  wireCover();
  const cov = $('#cover-open');
  if (cov) cov.addEventListener('click', () => window.open(`https://musicbrainz.org/release/${relMbid}/add-cover-art`, '_blank', 'noopener'));
  const coll = $('#coll');
  if (coll) coll.addEventListener('click', openCollections);
}

function timelineStep(key, n, isNext) {
  const info = ENTITIES[key];
  const m = state.matches[key];
  const status = effective(key);
  let body = '';
  if (status === 'existing') {
    body = `<div class="grow"><b>${info.name}</b> <span class="pill existing">Using existing</span><small>${esc(m.candidates.find((c) => c.mbid === m.selected)?.name || m.query)} · <a href="${info.view(m.selected)}" target="_blank" rel="noopener">${esc(m.selected.slice(0, 8))}… ↗</a></small></div>`;
  } else if (status === 'missing') {
    const opened = state.opened[key];
    body = `<div class="grow"><b>${info.name}</b> <span class="pill missing">Missing</span><small>${esc(m.query)}</small>${opened ? `<small class="waiting"><span class="spinner"></span> Waiting for you to submit it on MusicBrainz. This updates by itself${userscriptInstalled() ? ' the moment its page loads.' : '.'}</small>` : ''}</div>
      <button class="btn ${isNext && !opened ? 'primary' : ''}" data-create="${key}">${ICON.ext} ${opened ? 'Open again' : `Create ${info.name.toLowerCase()} on MusicBrainz`}</button>`;
  } else {
    body = `<div class="grow"><b>${info.name}</b> <span class="pill ambiguous">Needs a pick</span><small>${esc(m.query)}</small></div><button class="btn" data-review>Choose a match</button>`;
  }
  const mark = status === 'existing' ? ICON.check : status === 'ambiguous' ? ICON.alert : n;
  return `<div class="tstep ${status}"><div class="tnum">${mark}</div><div class="card tbody">${body}</div></div>`;
}

async function createEntity(key) {
  const a = state.album;
  if (key === 'artist') return seedUrl('artist', '/api/seed/artist', { name: a.artist });
  if (key === 'label') return seedUrl('label', '/api/seed/label', { name: a.label });
  if (key === 'release-group') return releaseGroupDialog();
  if (key === 'release') return releaseDialog();
}

async function seedUrl(key, endpoint, body) {
  const w = openBlank();
  if (!w) return;
  try {
    const { url } = await api('POST', endpoint, body);
    w.location.href = url;
    state.opened[key] = true;
    renderSubmit();
  } catch (e) { w.close(); toast(e.message, 'error'); }
}

function datalist(id, items) { return `<datalist id="${id}">${items.map(([v, n]) => `<option value="${v}">${esc(n)}</option>`).join('')}</datalist>`; }
const LANGS = [['eng', 'English'], ['jpn', 'Japanese'], ['deu', 'German'], ['fra', 'French'], ['spa', 'Spanish'], ['ita', 'Italian'], ['por', 'Portuguese'], ['nld', 'Dutch'], ['swe', 'Swedish'], ['nor', 'Norwegian'], ['dan', 'Danish'], ['fin', 'Finnish'], ['rus', 'Russian'], ['pol', 'Polish'], ['zho', 'Chinese'], ['kor', 'Korean'], ['ara', 'Arabic'], ['hin', 'Hindi'], ['zxx', '[No linguistic content]'], ['mul', '[Multiple languages]']];
const SCRIPTS = [['Latn', 'Latin'], ['Jpan', 'Japanese'], ['Cyrl', 'Cyrillic'], ['Hani', 'Han'], ['Hans', 'Han (Simplified)'], ['Hant', 'Han (Traditional)'], ['Kore', 'Korean'], ['Arab', 'Arabic'], ['Grek', 'Greek'], ['Hebr', 'Hebrew'], ['Deva', 'Devanagari']];
const COUNTRIES = [['GB', 'United Kingdom'], ['US', 'United States'], ['XW', '[Worldwide]'], ['XE', '[Europe]'], ['DE', 'Germany'], ['FR', 'France'], ['JP', 'Japan'], ['CA', 'Canada'], ['AU', 'Australia'], ['NL', 'Netherlands'], ['SE', 'Sweden'], ['NO', 'Norway'], ['IT', 'Italy'], ['ES', 'Spain'], ['IE', 'Ireland'], ['BR', 'Brazil'], ['NZ', 'New Zealand']];

function releaseGroupDialog() {
  const a = state.album;
  const o = state.config.options;
  openDialog(`<form id="rg-form" method="dialog">
    <div class="dlg-head"><h3>New release group</h3><p>${esc(a.title)} · ${esc(a.artist)}</p></div>
    <div class="dlg-body">
      <label class="field"><span>Primary type</span><select name="primary_type"><option value="">(none)</option>${o.rg_primary_types.map((t) => `<option>${esc(t)}</option>`).join('')}</select></label>
      <div class="field"><span style="display:block;margin-bottom:5px;color:var(--muted);font-size:.76rem;letter-spacing:.08em;text-transform:uppercase">Secondary types</span><div class="checks">${o.rg_secondary_types.map((t) => `<label><input type="checkbox" name="sec" value="${esc(t)}">${esc(t)}</label>`).join('')}</div></div>
      <label class="field"><span>Disambiguation</span><input type="text" name="disambiguation" placeholder="e.g. remastered edition"></label>
      <label class="field"><span>Edit note</span><textarea name="edit_note"></textarea></label>
    </div>
    <div class="dlg-foot"><button class="btn" type="button" id="dlg-cancel">Cancel</button><button class="btn primary" type="submit">${ICON.ext} Open form on MusicBrainz</button></div>
  </form>`);
  $('#dlg-cancel').addEventListener('click', closeDialog);
  $('#rg-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const body = { title: a.title, artist: a.artist, primary_type: f.get('primary_type'), secondary_types: f.getAll('sec'), disambiguation: f.get('disambiguation'), edit_note: f.get('edit_note') };
    closeDialog();
    seedUrl('release-group', '/api/seed/release-group', body);
  });
}

function releaseDialog() {
  const a = state.album;
  const o = state.config.options;
  openDialog(`<form id="rel-form" method="dialog">
    <div class="dlg-head"><h3>New release</h3><p>${esc(a.title)} · ${esc(a.artist)} · ${a.tracks.length} tracks</p></div>
    <div class="dlg-body">
      <div class="row2">
        <label class="field"><span>Status</span><select name="status"><option value="">(none)</option>${o.release_statuses.map((t) => `<option>${esc(t)}</option>`).join('')}</select></label>
        <label class="field"><span>Packaging</span><select name="packaging"><option value="">(none)</option>${o.release_packagings.map((t) => `<option>${esc(t)}</option>`).join('')}</select></label>
      </div>
      <div class="row2">
        <label class="field"><span>Language</span><input type="text" name="language" list="dl-lang" placeholder="eng"></label>
        <label class="field"><span>Script</span><input type="text" name="script" list="dl-script" placeholder="Latn"></label>
      </div>
      <div class="row2">
        <label class="field"><span>Country</span><input type="text" name="country" list="dl-country" placeholder="GB"></label>
        <label class="field"><span>Disambiguation</span><input type="text" name="disambiguation" placeholder="e.g. Japanese edition"></label>
      </div>
      <label class="field"><span>Annotation</span><textarea name="annotation"></textarea></label>
      <label class="field"><span>External links (one per line)</span><textarea name="links" placeholder="https://…"></textarea></label>
      <label class="field"><span>Edit note</span><textarea name="edit_note"></textarea></label>
      ${datalist('dl-lang', LANGS)}${datalist('dl-script', SCRIPTS)}${datalist('dl-country', COUNTRIES)}
    </div>
    <div class="dlg-foot"><button class="btn" type="button" id="dlg-cancel">Cancel</button><button class="btn primary" type="submit">${ICON.ext} Open form on MusicBrainz</button></div>
  </form>`);
  $('#dlg-cancel').addEventListener('click', closeDialog);
  $('#rel-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const details = {};
    for (const k of ['status', 'packaging', 'language', 'script', 'country', 'disambiguation', 'annotation', 'edit_note']) details[k] = f.get(k);
    details.external_links = String(f.get('links')).split('\n').map((s) => s.trim()).filter(Boolean);
    closeDialog();
    const w = openBlank();
    if (!w) return;
    try {
      const sel = (k) => state.matches[k]?.selected || null;
      const { action, fields } = await api('POST', '/api/seed/release', {
        album: { title: a.title, artist: a.artist, date: a.date, label: a.label, catalog_number: a.catalog_number, barcode: a.barcode, tracks: a.tracks },
        release_group_mbid: sel('release-group'), artist_mbid: sel('artist'), label_mbid: sel('label'), details,
      });
      postForm(w, action, fields);
      state.opened.release = true;
      renderSubmit();
    } catch (err) { w.close(); toast(err.message, 'error'); }
  });
}

// ---------------------------------------------------------------- login + collections
async function refreshAuth() {
  try { state.auth = await api('GET', '/api/auth/status'); } catch { /* keep previous */ }
  renderChrome();
}

function openLogin() {
  const a = state.auth;
  if (a.logged_in) {
    openDialog(`<div class="dlg-head"><h3>Logged in</h3><p>Signed in to MusicBrainz as <b>${esc(a.username || 'your account')}</b>.</p></div>
      <div class="dlg-foot"><button class="btn" id="dlg-cancel">Close</button><button class="btn" id="logout">Log out</button></div>`);
    $('#dlg-cancel').addEventListener('click', closeDialog);
    $('#logout').addEventListener('click', async () => { await api('POST', '/api/auth/logout'); closeDialog(); await refreshAuth(); toast('Logged out.'); });
    return;
  }
  if (!a.configured) {
    openDialog(`<div class="dlg-head"><h3>Login not configured</h3><p>Set <code>MB_OAUTH_CLIENT_ID</code> and <code>MB_OAUTH_CLIENT_SECRET</code> in the container's environment to enable MusicBrainz login. It's only needed for collections.</p></div>
      <div class="dlg-foot"><button class="btn" id="dlg-cancel">Close</button></div>`);
    $('#dlg-cancel').addEventListener('click', closeDialog);
    return;
  }
  openDialog(`<form id="code-form" method="dialog">
    <div class="dlg-head"><h3>Log in to MusicBrainz</h3><p>Only needed for collections. Searching and creating entities work without it.</p></div>
    <div class="dlg-body">
      <div class="stepnote"><span class="num">1</span><div>Open MusicBrainz and approve access. It will show you a code.<br><br><button class="btn small" type="button" id="open-auth">${ICON.ext} Open MusicBrainz</button></div></div>
      <div class="stepnote"><span class="num">2</span><div style="flex:1"><label class="field" style="margin:0"><span>Paste the code</span><input type="text" name="code" autocomplete="off" required></label></div></div>
    </div>
    <div class="dlg-foot"><button class="btn" type="button" id="dlg-cancel">Cancel</button><button class="btn primary" type="submit">Connect</button></div>
  </form>`);
  $('#dlg-cancel').addEventListener('click', closeDialog);
  $('#open-auth').addEventListener('click', async () => {
    const w = openBlank(); if (!w) return;
    try { const { url } = await api('POST', '/api/auth/start'); w.location.href = url; } catch (e) { w.close(); toast(e.message, 'error'); }
  });
  $('#code-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = $('button[type=submit]', e.target);
    busy(btn, true, 'Connecting…');
    try {
      await api('POST', '/api/auth/code', { code: new FormData(e.target).get('code') });
      closeDialog(); await refreshAuth(); toast('Logged in to MusicBrainz.', 'ok');
    } catch (err) { busy(btn, false); toast(err.message, 'error'); }
  });
}

async function openCollections() {
  if (!state.auth.logged_in) { openLogin(); return; }
  openDialog(`<div class="dlg-head"><h3>Add to a collection</h3></div><div class="dlg-body"><div class="scanning" style="padding:30px 0"><span class="spinner"></span></div></div>`);
  try {
    const { collections } = await api('GET', '/api/collections');
    openDialog(`<div class="dlg-head"><h3>Add to a collection</h3><p>${esc(state.album.title)}</p></div>
      <div class="dlg-body">${collections.length ? `<div class="list">${collections.map((c) => `<button data-coll="${esc(c.id)}">${esc(c.name)}</button>`).join('')}</div>` : '<p class="note">No release collections found on your account.</p>'}</div>
      <div class="dlg-foot"><button class="btn" id="dlg-cancel">Close</button></div>`);
    $('#dlg-cancel').addEventListener('click', closeDialog);
    $$('[data-coll]').forEach((b) => b.addEventListener('click', async () => {
      busy(b, true, 'Adding…');
      try {
        await api('POST', '/api/collections/add', { collection_id: b.dataset.coll, release_mbid: state.matches.release.selected });
        closeDialog(); toast('Added to your collection.', 'ok');
      } catch (e) { busy(b, false); toast(e.message, 'error'); }
    }));
  } catch (e) { closeDialog(); toast(e.message, 'error'); }
}

// ---------------------------------------------------------------- boot
(async function boot() {
  renderChrome();
  try {
    state.config = await api('GET', '/api/config');
  } catch (e) {
    app().innerHTML = `<div class="empty card pad"><h2>Can't reach the server</h2><p>${esc(e.message)}</p></div>`;
    return;
  }
  if (!state.config.has_contact) toast('Set MB_CONTACT so MusicBrainz can identify this client.', 'warn');
  if (!state.config.library_exists) { app().innerHTML = `<div class="empty card pad"><h2>Music library not found</h2><p>The configured MUSIC_ROOT doesn't exist inside the container. Check the volume mount.</p></div>`; return; }
  refreshAuth();
  go('browse');
})();
