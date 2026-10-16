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
  star: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/></svg>',
  box: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M21 8v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8"/><path d="M1 3h22v5H1z"/><path d="M10 12h4"/></svg>',
  chev: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 6 6 6-6 6"/></svg>',
};

const ENTITIES = {
  artist: { name: 'Artist', icon: ICON.artist, view: (id) => `https://musicbrainz.org/artist/${id}` },
  label: { name: 'Label', icon: ICON.label, view: (id) => `https://musicbrainz.org/label/${id}` },
  'release-group': { name: 'Release Group', icon: ICON.rg, view: (id) => `https://musicbrainz.org/release-group/${id}` },
  release: { name: 'Release', icon: ICON.release, view: (id) => `https://musicbrainz.org/release/${id}` },
};
// Dependency order: parents before the entities that reference them.
// A credit like "Morrissey & Johnny Marr" can be split into separate artists on a chosen
// separator. Each gets its own match entity: 'artist', 'artist-2', 'artist-3', ...
const SEPARATOR_KEY = 'filestomb.separator';
const savedSeparator = () => { try { return localStorage.getItem(SEPARATOR_KEY) || ' & '; } catch { return ' & '; } };
function artistNames(a = state.album) {
  const whole = (a?.artist || '').trim();
  const sp = a?.split;
  if (!sp?.on || !sp.sep) return [whole];
  const parts = whole.split(sp.sep).map((n) => n.trim()).filter(Boolean);
  return parts.length ? parts : [whole];
}
const isSplit = () => artistNames().length > 1;
const artistKeys = () => artistNames().map((_, i) => (i === 0 ? 'artist' : `artist-${i + 1}`));
const isArtistKey = (k) => k === 'artist' || /^artist-\d+$/.test(k);
const artistIndex = (k) => (k === 'artist' ? 0 : Number(k.split('-')[1]) - 1);
const joinPhrase = () => (isSplit() ? state.album.split.sep : '');
function entityInfo(key) {
  if (!isArtistKey(key)) return ENTITIES[key];
  return { ...ENTITIES.artist, name: isSplit() ? `Artist ${artistIndex(key) + 1}` : 'Artist' };
}
const submitOrder = () => ['label', ...artistKeys(), 'release-group', 'release'];
const reviewOrder = () => [...artistKeys(), 'label', 'release-group', 'release'];

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
  extracted: {},     // archive path -> {path, name, files} once extracted this session
  highlight: null,   // folder path to spotlight after an extraction
  picard: { status: null, statusAt: 0, sent: null, saved: false, fingerprinted: false },
  favs: [],          // favourite folders: [{path, name, parent}]
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
  $('#auth-chip').innerHTML = `<button class="chip ${state.view === 'library' ? 'on' : ''}" id="lib-btn" title="Process a whole folder of albums"><span class="dot"></span>Library</button> ${state.enf?.configured && state.enf.reachable ? `<button class="chip ${state.view === 'genres' ? 'on' : ''}" id="gen-btn" title="Artists that still need a genre in Music Genre Enforcer"><span class="dot"></span>Genres${state.enf.counts?.undefined ? ` <b>${state.enf.counts.undefined}</b>` : ''}</button> ` : ''}<button class="chip ${userscriptInstalled() ? (userscriptOutdated() ? 'warn' : 'on') : ''}" id="us-btn" title="Browser userscript"><span class="dot"></span>Userscript</button> <button class="chip" id="set-btn" title="fanart.tv key and other optional services"><span class="dot"></span>Settings</button> <button class="chip ${a.logged_in ? 'on' : ''}" id="auth-btn"><span class="dot"></span>${a.logged_in ? esc(a.username || 'Logged in') : 'Log in to MusicBrainz'}</button>`;
  $('#auth-btn').addEventListener('click', openLogin);
  $('#us-btn').addEventListener('click', openUserscript);
  $('#set-btn').addEventListener('click', openSettings);
  $('#gen-btn')?.addEventListener('click', () => go('genres'));
  $('#lib-btn').addEventListener('click', () => openLibrary(state.lib.root));
}

const userscriptInstalled = () => !!document.documentElement.dataset.filestombUserscript;
const userscriptOutdated = () => userscriptInstalled() && !!state.config && document.documentElement.dataset.filestombUserscript !== state.config.userscript_version;

function go(view) {
  state.view = view;
  state.maxStep = Math.max(state.maxStep, ['browse', 'review', 'submit'].indexOf(view));
  renderChrome();
  if (view !== 'library') libStop();
  ({ browse: renderBrowse, review: renderReview, submit: renderSubmit, library: renderLibrary, genres: renderGenres })[view]();
  window.scrollTo({ top: 0 });
}

// ---------------------------------------------------------------- browse
// The folder being browsed lives in the address bar (#/Some/Folder), so a
// refresh stays put and Back/Forward walk through folders. A bare "/" is the
// library root.
const pathFromHash = () => { try { return decodeURIComponent(location.hash.replace(/^#\/?/, '')); } catch { return ''; } };
const hashFor = (p) => (p ? '#/' + p.split('/').map(encodeURIComponent).join('/') : '');

async function loadBrowse(path, { push = true, keepHighlight = false } = {}) {
  if (!keepHighlight) state.highlight = null;
  state.batchCtx = null;
  app().innerHTML = `<section class="view"><div class="folder-grid">${'<div class="skeleton"></div>'.repeat(9)}</div></section>`;
  try {
    state.browse = await api('GET', `/api/browse?path=${encodeURIComponent(path)}`);
    state.filter = '';
    if (push && pathFromHash() !== path) history.pushState(null, '', location.pathname + hashFor(path));
    renderBrowse();
  } catch (e) {
    toast(e.message, 'error');
    if (path) loadBrowse('', { push: false }).then(() => history.replaceState(null, '', location.pathname));
    else app().innerHTML = `<div class="empty card pad"><h2>Can't open the library</h2><p>${esc(e.message)}</p></div>`;
  }
}

function renderBrowse() {
  if (!state.browse) return loadBrowse(pathFromHash(), { push: false });
  const b = state.browse;
  const q = state.filter.toLowerCase();
  const dirs = b.dirs.filter((d) => d.name.toLowerCase().includes(q));
  const parent = b.crumbs.length > 1 ? b.crumbs[b.crumbs.length - 2].path : null;
  // The folder holding the album you last worked on: handy for doing its siblings next.
  const resumeFolder = (state.config.last_path || '').split('/').slice(0, -1).join('/');

  app().innerHTML = `
  <section class="view">
    <div class="page-head">
      <div><h2>Choose an album</h2><p>Open a folder of tagged audio files. Folders with music are marked and scan on click.</p></div>
      ${resumeFolder && b.path === '' ? `<button class="btn" id="resume" title="${esc(resumeFolder)}">${ICON.back} Resume in ${esc(resumeFolder.split('/').pop())}</button>` : ''}
    </div>
    <div class="card toolbar">
      <button class="btn small" id="up" ${parent === null ? 'disabled' : ''}>${ICON.up} Up</button>
      ${b.path ? favBtn(b.path, b.crumbs[b.crumbs.length - 1].name) : ''}
      <div class="crumbs">${b.crumbs.map((c, i) => `${i ? '<span class="sep">/</span>' : ''}<button data-path="${esc(c.path)}" class="${i === b.crumbs.length - 1 ? 'cur' : ''}">${esc(c.name)}</button>`).join('')}</div>
      <input class="search" id="filter" type="text" placeholder="Filter folders…" value="${esc(state.filter)}" aria-label="Filter folders">
      ${b.path ? `<button class="btn" id="batch-here" title="Find every album under this folder, match them against MusicBrainz and triage them">${ICON.box} Batch this folder</button>` : ''}
      <button class="btn ${b.audio_files ? 'primary' : ''}" id="scan-here">${ICON.music} ${b.audio_files ? `Scan this folder (${b.audio_files} file${b.audio_files === 1 ? '' : 's'})` : 'Scan this folder'}</button>
    </div>
    ${b.path === '' ? favChipsHTML() : ''}
    ${archivesHTML(b)}
    ${dirs.length ? `<div class="folder-grid" id="grid">${dirs.map((d) => folderCard(d)).join('')}</div>`
      : `<div class="empty card"><img src="/static/logo.png" alt=""><p>${b.dirs.length ? 'No folders match that filter.' : 'No sub-folders here.'}</p></div>`}
  </section>`;

  $('#up').addEventListener('click', () => loadBrowse(parent));
  const resume = $('#resume');
  if (resume) resume.addEventListener('click', () => loadBrowse(resumeFolder));
  $$('.crumbs button').forEach((c) => c.addEventListener('click', () => loadBrowse(c.dataset.path)));
  $('#scan-here').addEventListener('click', () => scan(b.path));
  $('#batch-here')?.addEventListener('click', () => openLibrary(b.path));
  const f = $('#filter');
  f.addEventListener('input', () => {
    state.filter = f.value;
    const grid = $('#grid');
    const query = f.value.toLowerCase();
    if (grid) $$('.folder-wrap', grid).forEach((w) => { w.hidden = !w.dataset.name.includes(query); });
  });
  $$('[data-open]').forEach((el) => el.addEventListener('click', () => loadBrowse(el.dataset.open)));
  $$('[data-extract]').forEach((el) => el.addEventListener('click', () => extractArchive(el.dataset.extract, el)));
  $$('[data-fav]').forEach((el) => el.addEventListener('click', (e) => { e.stopPropagation(); toggleFav(el.dataset.fav); }));
  $$('[data-scan]').forEach((el) => el.addEventListener('click', () => scan(el.dataset.scan)));
}

const isFav = (path) => state.favs.some((f) => f.path === path);
const favBtn = (path, name) => `<button class="favbtn ${isFav(path) ? 'on' : ''}" data-fav="${esc(path)}" aria-pressed="${isFav(path)}" title="${isFav(path) ? 'Remove from favourites' : 'Add to favourites'}" aria-label="Favourite ${esc(name)}">${ICON.star}</button>`;

function folderCard(d) {
  const attr = `data-name="${esc(d.name.toLowerCase())}"`;
  if (d.has_audio) {
    return `<div class="folder-wrap album ${d.path === state.highlight ? 'fresh' : ''}" ${attr}>
      <button class="folder album" data-scan="${esc(d.path)}" title="Scan ${esc(d.name)}"><span class="ico">${ICON.music}</span><span class="name">${esc(d.name)}</span></button>
      <div class="actions">${favBtn(d.path, d.name)}<button class="btn small ghost" data-open="${esc(d.path)}" title="Browse inside" aria-label="Browse inside ${esc(d.name)}">Open ${ICON.chev}</button></div>
    </div>`;
  }
  return `<div class="folder-wrap plain ${d.path === state.highlight ? 'fresh' : ''}" ${attr}><button class="folder" data-open="${esc(d.path)}"><span class="ico">${ICON.folder}</span><span class="name">${esc(d.name)}</span></button><div class="actions">${favBtn(d.path, d.name)}</div></div>`;
}

const fmtSize = (n) => (n >= 1024 ** 3 ? `${(n / 1024 ** 3).toFixed(1)} GB` : n >= 1024 ** 2 ? `${(n / 1024 ** 2).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
const extractorMissing = (name) => (/\.rar$/i.test(name) ? !state.config.can_extract_rar : /\.(zip|7z)$/i.test(name) ? !state.config.can_extract_all : false);

function archivesHTML(b) {
  if (!b.archives?.length) return '';
  return `<div class="card archives"><div class="arch-head">${ICON.box}<b>Archives</b><span class="note">Extracted into this folder. The archive itself is kept.</span></div>
    ${b.archives.map((a) => {
      const done = state.extracted[a.path];
      const blocked = !b.writable ? 'This library is mounted read-only, so nothing can be extracted.' : extractorMissing(a.name) ? 'This server is missing the tool needed for this archive type.' : '';
      return `<div class="arch-row"><span class="ico">${ICON.box}</span><span class="aname">${esc(a.name)}<small>${fmtSize(a.bytes)}</small></span>
        ${done ? `<span class="pill existing">Extracted · ${done.files} files</span><button class="btn small primary" data-open="${esc(done.path)}">Open folder ${ICON.chev}</button>`
          : `<button class="btn small" data-extract="${esc(a.path)}" ${blocked ? `disabled title="${esc(blocked)}"` : ''}>${ICON.down} Extract here</button>`}</div>`;
    }).join('')}</div>`;
}

async function extractArchive(path, btn) {
  busy(btn, true, 'Extracting…');
  try {
    const res = await api('POST', '/api/extract', { path });
    state.extracted[path] = res;
    state.highlight = res.path;
    toast(`Extracted ${res.files} file${res.files === 1 ? '' : 's'} to “${res.name}”.`, 'ok');
    await loadBrowse(state.browse.path, { push: false, keepHighlight: true });
    $('.folder-wrap.fresh')?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  } catch (e) {
    busy(btn, false);
    toast(e.message, 'error');
  }
}

async function toggleFav(path) {
  try {
    const res = isFav(path) ? await api('DELETE', `/api/favourites?path=${encodeURIComponent(path)}`) : await api('POST', '/api/favourites', { path });
    state.favs = res.favourites;
    if (state.view === 'browse') renderBrowse();
  } catch (e) { toast(e.message, 'error'); }
}

// Favourite chips: shown at the library root. Parent folder is added only
// when two favourites share a name, so labels stay short but unambiguous.
function favChipsHTML() {
  if (!state.favs.length) return '';
  const counts = {};
  state.favs.forEach((f) => { counts[f.name] = (counts[f.name] || 0) + 1; });
  return `<div class="favs" aria-label="Favourite folders"><span class="favs-label">${ICON.star} Favourites</span>${state.favs.map((f) => `<span class="favchip"><button class="chipgo" data-open="${esc(f.path)}" title="${esc(f.path)}">${counts[f.name] > 1 && f.parent ? `<small>${esc(f.parent)} /</small> ` : ''}${esc(f.name)}</button><button class="chipx" data-fav="${esc(f.path)}" title="Remove from favourites" aria-label="Remove ${esc(f.name)} from favourites">×</button></span>`).join('')}</div>`;
}

async function scan(path) {
  app().innerHTML = `<div class="scanning"><span class="spinner"></span><div>Reading tags…</div></div>`;
  try {
    const album = await api('POST', '/api/scan', { path });
    album.split = { on: false, sep: savedSeparator() };
    state.album = album;
    state.config.last_path = album.path;
    state.cover = album.cover;
    state.matches = null;
    state.opened = {};
    state.picard.sent = null; state.picard.saved = false; state.picard.fingerprinted = false;
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
    const names = artistNames();
    const found = await api('POST', '/api/match', { title: a.title, artist: a.artist, label: a.label, artists: names.length > 1 ? names : [] });
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
            .map(([k, l]) => `<label class="field"><span>${l}</span><input type="text" data-field="${k}" value="${esc(a[k])}" ${k === 'date' ? 'placeholder="YYYY or YYYY-MM-DD"' : ''}></label>${k === 'artist' ? '<div id="split-box"></div>' : ''}`).join('')}
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
    <div style="display:flex;gap:8px">${batchBar()}<button class="btn" id="back">${ICON.back} ${state.batchCtx ? 'Browse' : 'Choose another album'}</button></div>
    <button class="btn primary" id="next">Continue to submit ${ICON.chev}</button>
  </div></div>`;

  $$('[data-field]').forEach((i) => i.addEventListener('input', () => { a[i.dataset.field] = i.value; }));
  $$('[data-track]').forEach((i) => i.addEventListener('input', () => { a.tracks[+i.dataset.track][i.dataset.k] = i.value; }));
  wireCover();
  renderSplitBox();
  $('#check').addEventListener('click', () => checkMusicBrainz({ keepSelections: true }));
  wireBatchBar();
  $('#back').addEventListener('click', () => { state.batchCtx = null; go('browse'); });
  $('#next').addEventListener('click', () => {
    if (!state.matches) { toast('Check MusicBrainz first.', 'warn'); return; }
    go('submit');
  });
  refreshMatchUI();
}

// "Split into separate artists": a toggle plus a free-text separator (e.g. " & ").
function renderSplitBox() {
  const box = $('#split-box'); if (!box) return;
  const a = state.album; const sp = a.split;
  const names = artistNames();
  box.innerHTML = `<label style="display:flex;gap:8px;align-items:center;margin:-6px 0 10px;font-size:.85rem"><input type="checkbox" id="split-on" ${sp.on ? 'checked' : ''}> Credit is several artists</label>
    ${sp.on ? `<label class="field"><span>Separator <small style="text-transform:none;letter-spacing:0">(spaces count)</small></span><input type="text" id="split-sep" value="${esc(sp.sep)}" spellcheck="false" placeholder=" &amp; "></label>
    <div class="note" style="margin:-6px 0 10px">${names.length > 1 ? `${names.length} artists: ${names.map((n) => `<b>${esc(n)}</b>`).join(' + ')}` : 'That separator isn\'t in the artist, so it stays one artist.'}</div>` : ''}`;
  const apply = () => { state.matches = null; renderReview(); checkMusicBrainz(); };
  $('#split-on').addEventListener('change', (e) => { sp.on = e.target.checked; apply(); });
  const sep = $('#split-sep');
  if (sep) {
    sep.addEventListener('input', () => { sp.sep = sep.value; try { if (sp.sep.trim()) localStorage.setItem(SEPARATOR_KEY, sp.sep); } catch { /* optional */ } });
    sep.addEventListener('change', apply);
  }
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
  return `<div class="cover-actions"><button class="btn small" data-cover="upload">${ICON.up} Upload…</button><button class="btn small" data-cover="pick">${ICON.folder} From folder…</button><button class="btn small" data-cover="online" title="Cover Art Archive and fanart.tv">${ICON.search} Find online…</button>${state.cover?.custom ? '<button class="btn small ghost" data-cover="reset">Reset</button>' : ''}<input type="file" id="cover-file" accept="image/jpeg,image/png,image/gif,image/webp" hidden></div>`;
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
    else if (b.dataset.cover === 'online') pickOnline();
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
async function pickOnline() {
  const rel = state.matches?.release?.selected;
  const rg = state.matches?.['release-group']?.selected;
  const head = '<div class="dlg-head"><h3>Find cover art online</h3><p>From the Cover Art Archive and fanart.tv, for the release you matched.</p></div>';
  if (!rel && !rg) {
    openDialog(`${head}<div class="dlg-body"><p class="note">Match this album to a MusicBrainz release (or release group) first, then come back. Both services are looked up by MusicBrainz ID.</p></div><div class="dlg-foot"><button class="btn" id="dlg-cancel">Close</button></div>`);
    $('#dlg-cancel').addEventListener('click', closeDialog); return;
  }
  openDialog(`${head}<div class="dlg-body"><div class="scanning" style="padding:30px 0"><span class="spinner"></span></div></div>`);
  try {
    const { images, notes } = await api('GET', `/api/artwork?release=${rel || ''}&release_group=${rg || ''}`);
    const src = { caa: 'Cover Art Archive', fanart: 'fanart.tv' };
    openDialog(`${head}<div class="dlg-body">${images.length ? `<div class="imggrid">${images.map((i, n) => `<button data-n="${n}" title="${esc(src[i.source])} · ${esc(i.scope)}"><img loading="lazy" referrerpolicy="no-referrer" src="${esc(i.thumb)}" alt=""><span>${esc(i.label)}</span><small>${esc(src[i.source])}${i.front ? ' · front' : ''}</small></button>`).join('')}</div>` : '<p class="note">No artwork found for this release.</p>'}${(notes || []).map((n) => `<p class="note">${esc(n)}</p>`).join('')}</div>
      <div class="dlg-foot"><button class="btn" id="dlg-cancel">Close</button></div>`);
    $('#dlg-cancel').addEventListener('click', closeDialog);
    $$('[data-n]').forEach((b) => b.addEventListener('click', async () => {
      busy(b, true, 'Downloading…');
      try {
        state.cover = await api('POST', '/api/cover/online', { path: state.album.path, url: images[+b.dataset.n].url });
        state.coverV = Date.now(); closeDialog(); refreshCover(); toast('Cover art set.', 'ok');
      } catch (e) { busy(b, false); toast(e.message, 'error'); }
    }));
  } catch (e) { closeDialog(); toast(e.message, 'error'); }
}

async function openSettings() {
  let st;
  try { st = await api('GET', '/api/settings'); } catch (e) { toast(e.message, 'error'); return; }
  const f = st.fanart_api_key; const lk = st.lidarr_api_key;
  const val = (k) => esc(st[k]?.value || '');
  const tag = (x) => (x.set ? '<b style="color:var(--ok)">· saved</b>' : '') + (x.from_env ? ' <small>(from environment)</small>' : '');
  openDialog(`<div class="dlg-head"><h3>Settings</h3><p>Optional services. Keys are stored on the server in its config folder and never shown again.</p></div>
    <div class="dlg-body">
      <h4 style="margin:0 0 8px">fanart.tv</h4>
      <label class="field"><span>API key ${tag(f)}</span>
        <input type="password" id="set-fanart" autocomplete="off" placeholder="${f.set ? 'Leave blank to keep the saved key' : 'Paste your key'}">
      </label>
      <p class="note">Used by “Find online…” on the cover card, alongside the Cover Art Archive.</p>
      <div class="inline-actions" style="margin-bottom:18px">${f.set ? '<button class="btn small" id="set-test">Test key</button><button class="btn small ghost" id="set-clear">Remove key</button>' : ''}</div>
      <h4 style="margin:0 0 8px">Lidarr</h4>
      <label class="field"><span>URL</span><input id="set-lurl" value="${val('lidarr_url')}" placeholder="http://lidarr.local:8686"></label>
      <label class="field"><span>API key ${tag(lk)}</span><input type="password" id="set-lkey" autocomplete="off" placeholder="${lk.set ? 'Leave blank to keep the saved key' : 'Lidarr → Settings → General → API Key'}"></label>
      <label class="field"><span>Root folder, as Lidarr sees it</span><input id="set-lroot" value="${val('lidarr_root_folder')}" placeholder="/data/Media/Audio/Music/Sources/Clean"></label>
      <label class="field"><span>Library mount inside Lidarr</span><input id="set-llib" value="${val('lidarr_library_path') || '/data'}" placeholder="/data"></label>
      <label style="display:flex;gap:8px;align-items:center;margin-bottom:8px"><input type="checkbox" id="set-lauto" ${st.lidarr_auto?.value === '1' ? 'checked' : ''}> Batch mode sends each finished album to Lidarr automatically</label>
      <p class="note">Albums are added by their exact MusicBrainz release and Lidarr rescans the folder where Picard saved them. Files are never moved or renamed by Lidarr.</p>
      <div class="inline-actions" style="margin-bottom:18px">${lk.set ? '<button class="btn small" id="set-ltest">Test Lidarr</button>' : ''}</div>
      <h4 style="margin:0 0 8px">ReplayGain (rsgain)</h4>
      <label class="field"><span>Path to rsgain, inside this container</span><input id="set-rsgain" value="${val('rsgain_path')}" placeholder="/rsgain/rsgain"></label>
      <p class="note">Mount the folder containing the rsgain binary (the one Picard's plugin uses) into this container. The options themselves are set on the Submit screen and remembered.</p>
      <div class="inline-actions" style="margin-bottom:18px"></div>
      <h4 style="margin:0 0 8px">Music Genre Enforcer</h4>
      <label class="field"><span>URL</span><input id="set-eurl" value="${val('enforcer_url')}" placeholder="http://enforcer.local:8320"></label>
      <label style="display:flex;gap:8px;align-items:center;margin-bottom:8px"><input type="checkbox" id="set-eauto" ${st.enforcer_auto?.value === '1' ? 'checked' : ''}> Batch mode tells it about each finished album</label>
      <p class="note">New artists are reviewed inside FilesToMB (the Genres chip). The enforcer itself keeps the genres and writes the tags.</p>
      <div class="inline-actions">${st.enforcer_url?.set ? '<button class="btn small" id="set-etest">Test connection</button>' : ''}</div>
    </div>
    <div class="dlg-foot"><button class="btn" id="dlg-cancel">Close</button><button class="btn primary" id="set-save">Save</button></div>`);
  $('#dlg-cancel').addEventListener('click', closeDialog);
  $('#set-save').addEventListener('click', async () => {
    const body = { lidarr_url: $('#set-lurl').value.trim(), lidarr_root_folder: $('#set-lroot').value.trim(), lidarr_library_path: $('#set-llib').value.trim(), lidarr_auto: $('#set-lauto').checked ? '1' : '', enforcer_url: $('#set-eurl').value.trim(), enforcer_auto: $('#set-eauto').checked ? '1' : '', rsgain_path: $('#set-rsgain').value.trim() };
    if ($('#set-fanart').value.trim()) body.fanart_api_key = $('#set-fanart').value.trim();
    if ($('#set-lkey').value.trim()) body.lidarr_api_key = $('#set-lkey').value.trim();
    try { await api('PUT', '/api/settings', body); toast('Saved.', 'ok'); state.rsgain.configured = null; loadEnforcerStatus(); openSettings(); } catch (e) { toast(e.message, 'error'); }
  });
  $('#set-clear')?.addEventListener('click', async () => { try { await api('PUT', '/api/settings', { fanart_api_key: '' }); toast('Key removed.'); openSettings(); } catch (e) { toast(e.message, 'error'); } });
  $('#set-test')?.addEventListener('click', async (e) => {
    const btn = e.currentTarget; // currentTarget is cleared once the handler awaits
    busy(btn, true, 'Testing…');
    try { const r = await api('POST', '/api/settings/test-fanart'); toast(`fanart.tv key works (${r.images} images found for the test album).`, 'ok'); } catch (err) { toast(err.message, 'error'); }
    busy(btn, false);
  });
  $('#set-etest')?.addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    busy(btn, true, 'Testing…');
    try { const r = await api('POST', '/api/settings/test-enforcer'); toast(`Connected: ${r.artists} artists, ${r.undefined} still need a genre.`, 'ok'); } catch (err) { toast(err.message, 'error'); }
    busy(btn, false);
  });
  $('#set-ltest')?.addEventListener('click', async (e) => {
    const btn = e.currentTarget;
    busy(btn, true, 'Testing…');
    try {
      const r = await api('POST', '/api/settings/test-lidarr');
      toast(r.root_folder_found ? `Lidarr ${r.version} connected; root folder found.` : `Connected to Lidarr ${r.version}, but that root folder isn't in it. Lidarr has: ${r.root_folders.join(', ') || 'none'}.`, r.root_folder_found ? 'ok' : 'warn');
    } catch (err) { toast(err.message, 'error'); }
    busy(btn, false);
  });
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
    host.innerHTML = reviewOrder().map(() => '<div class="skeleton" style="margin-bottom:14px;height:74px"></div>').join('');
    return;
  }
  if (!state.matches) { host.innerHTML = `<div class="card pad note">Not checked yet.</div>`; return; }
  host.innerHTML = reviewOrder().filter((k) => state.matches[k]).map(entityCard).join('');

  $$('[data-pick]', host).forEach((r) => r.addEventListener('change', () => {
    const [key, mbid] = r.dataset.pick.split('|');
    const m = state.matches[key];
    if (mbid === '__new__') { m.selected = null; m.createNew = true; } else { m.selected = mbid; m.createNew = false; }
    refreshMatchUI();
  }));
  $$('[data-search]', host).forEach((b) => b.addEventListener('click', () => openSearch(b.dataset.search)));
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

// "Search…": look an entity up on MusicBrainz by hand (when the automatic match missed it),
// then pick a result, or fall back to creating it.
function openSearch(key) {
  const a = state.album; const info = entityInfo(key);
  const type = isArtistKey(key) ? 'artist' : key;
  const hasArtistField = type === 'release-group' || type === 'release';
  const first = type === 'artist' ? artistNames()[artistIndex(key)] : type === 'label' ? a.label : a.title;
  openDialog(`<form id="srch-form"><div class="dlg-head"><h3>Search MusicBrainz: ${esc(info.name.toLowerCase())}</h3><p>Type what you know. Results come straight from MusicBrainz.</p></div>
    <div class="dlg-body">
      <label class="field"><span>${type === 'artist' || type === 'label' ? 'Name' : 'Title'}</span><input type="text" id="srch-name" value="${esc(first || '')}" autocomplete="off"></label>
      ${hasArtistField ? `<label class="field"><span>Artist <small style="text-transform:none;letter-spacing:0">(optional)</small></span><input type="text" id="srch-artist" value="${esc(a.artist || '')}" autocomplete="off"></label>` : ''}
      <div id="srch-results"></div>
    </div>
    <div class="dlg-foot"><button class="btn" type="button" id="dlg-cancel">Close</button><button class="btn primary" type="submit">${ICON.search} Search</button></div></form>`);
  $('#dlg-cancel').addEventListener('click', closeDialog);
  $('#srch-name').focus(); $('#srch-name').select();
  const out = $('#srch-results');
  $('#srch-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = $('button[type=submit]', e.target); busy(btn, true, 'Searching…');
    out.innerHTML = '';
    try {
      const { results } = await api('POST', '/api/search', { entity: type, name: $('#srch-name').value, artist: hasArtistField ? $('#srch-artist').value : '' });
      if (!results.length) {
        out.innerHTML = `<div class="card pad" style="margin-top:8px"><b>No results.</b><p class="note" style="margin:6px 0 10px">Nothing like that is on MusicBrainz. Try fewer words, or create it.</p><button class="btn" type="button" id="srch-new">Create a new ${esc(info.name.toLowerCase())}</button></div>`;
        $('#srch-new').addEventListener('click', () => { const m = state.matches[key]; m.selected = null; m.createNew = true; closeDialog(); refreshMatchUI(); if (state.view === 'submit') renderSubmit(); });
      } else {
        out.innerHTML = `<div class="srows">${results.map((r, i) => `<div class="srow"><div class="sinfo"><b>${esc(r.name)}</b>${r.artist ? `<span class="sby">${esc(r.artist)}</span>` : ''}<div class="smeta">${[r.detail, r.disambiguation].filter(Boolean).map(esc).join(' · ')}${r.detail || r.disambiguation ? ' · ' : ''}<a href="${info.view(r.mbid)}" target="_blank" rel="noopener">view ↗</a></div></div><button class="btn small primary" type="button" data-use="${i}">Use this</button></div>`).join('')}</div>`;
        $$('[data-use]', out).forEach((b) => b.addEventListener('click', () => {
          const r = results[+b.dataset.use];
          adopt(key, { mbid: r.mbid, name: r.name, score: r.score, disambiguation: [r.artist, r.detail].filter(Boolean).join(' · ') || null });
          closeDialog(); refreshMatchUI(); if (state.view === 'submit') renderSubmit();
          toast(`${info.name} set to “${r.name}”.`, 'ok');
        }));
      }
    } catch (err) { toast(err.message, 'error'); }
    busy(btn, false);
  });
}

function entityCard(key) {
  const m = state.matches[key];
  const info = entityInfo(key);
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
      <form class="manual" data-manual="${key}"><input type="text" placeholder="…or paste a MusicBrainz ID / URL" aria-label="MusicBrainz ID for ${info.name}"><button class="btn small" type="submit">Use</button><button class="btn small" type="button" data-search="${key}" title="Search MusicBrainz yourself">${ICON.search} Search…</button></form>
    </div>
  </div>`;
}

// ---------------------------------------------------------------- submit
async function pushJob() {
  const a = state.album;
  try {
    await api('PUT', '/api/job', { path: a.path, title: a.title, artist: a.artist, release_mbid: state.matches?.release?.selected || null, has_cover: !!state.cover, cover_filename: state.cover?.filename || null, awaiting: [...new Set(submitOrder().filter((k) => state.matches?.[k] && effective(k) === 'missing').map((k) => (isArtistKey(k) ? 'artist' : k)))], names: { artist: artistNames()[0], label: a.label, 'release-group': a.title, release: a.title }, artist_names: artistNames() });
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

const anyMissing = () => !!state.matches && submitOrder().some((k) => state.matches[k] && effective(k) === 'missing');
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
      const before = JSON.stringify(submitOrder().map((k) => effective(k)));
      await checkMusicBrainz({ keepSelections: true });
      changed = changed || before !== JSON.stringify(submitOrder().map((k) => effective(k)));
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
        const slot = c.entity === 'artist' ? captureArtistSlot(c) : c.entity;
        if (!slot || !state.matches[slot]) continue;
        adopt(slot, { mbid: c.mbid, name: c.name || 'Captured from MusicBrainz', score: 100, disambiguation: c.mbid.slice(0, 8) + '…' });
        toast(`${entityInfo(c.entity).name} captured from MusicBrainz.`, 'ok');
      }
      renderSubmit();
      return;
    }
  } catch { /* ignore */ }
  if (ticks % 3 === 0 && anyMissing()) refreshSubmit();
}
// A captured artist belongs to the slot whose name it matches (else the first one still missing).
function captureArtistSlot(c) {
  const norm = (t) => String(t || '').toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');
  const keys = artistKeys().filter((k) => state.matches[k]);
  const byName = keys.find((k) => norm(artistNames()[artistIndex(k)]) === norm(c.name));
  return byName || keys.find((k) => !state.matches[k].selected && state.opened[k]) || keys.find((k) => !state.matches[k].selected) || null;
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
  const steps = submitOrder().filter((k) => state.matches[k]);
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
    <div class="card pad picard" id="picard-card"></div>
    <div class="card pad" id="rsgain-card" style="margin-top:16px"></div>
    <div class="card pad" id="lidarr-card" style="margin-top:16px"></div>
    <div class="card pad" id="genre-card" style="margin-top:16px"></div>
  </section>
  <div class="actionbar"><div class="inner"><div style="display:flex;gap:8px"><button class="btn" id="back">${ICON.back} Back to review</button>${batchBar()}</div>${state.batchCtx ? `<button class="btn primary" id="bt-next" title="Open the next album in the Create on MB list">Next to create ${ICON.chev}</button>` : '<span></span>'}</div></div>`;

  wireBatchBar();
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
  renderPicardCard();
  loadPicardStatus();
  renderRsgainCard();
  renderLidarrCard();
  renderGenreCard();
  const cov = $('#cover-open');
  if (cov) cov.addEventListener('click', () => window.open(`https://musicbrainz.org/release/${relMbid}/add-cover-art`, '_blank', 'noopener'));
  const coll = $('#coll');
  if (coll) coll.addEventListener('click', openCollections);
}

// ---------------------------------------------------------------- Music Genre Enforcer
// FilesToMB only calls the enforcer's API: it stays the source of truth for artist genres and writes the tags.
state.enf = null;
async function loadEnforcerStatus() {
  try { state.enf = await api('GET', '/api/enforcer/status'); } catch { state.enf = null; }
  renderChrome();
}

// The review form for one artist, used on the Submit screen and in the Genres queue.
async function mountGenreReview(el, name, { onSaved, onSkip } = {}) {
  el.innerHTML = `<div class="artist-name" style="font:600 1.2rem var(--display, inherit)">${esc(name)}</div>
    <div class="note" id="gr-peek">Reading tags on disk…</div>
    <div class="inline-actions" style="margin:8px 0"><button class="btn small" id="gr-lfm" ${state.enf?.lastfm ? '' : 'disabled title="Add a Last.fm key in Music Genre Enforcer settings"'}>Check Last.fm</button></div>
    <div id="gr-lfmres" class="note"></div>
    <div class="note" style="margin-top:10px">Your genres</div>
    <div class="gchips" id="gr-chips"></div>
    <form id="gr-form" style="margin-top:10px"><input id="gr-input" placeholder="Type a genre, or pick one above" autocomplete="off">
      <div class="inline-actions" style="margin-top:10px">${onSkip ? '<button type="button" class="btn ghost" id="gr-skip">Skip</button>' : ''}<button class="btn primary" type="submit">Save${onSaved ? ' &amp; apply' : ''}</button></div>
      <p class="note">Single genre only, no ; | /${state.enf?.dry_run ? ' · <b style="color:var(--warn)">The enforcer is in dry-run mode: tags won\'t actually be written.</b>' : ''}</p></form>`;
  const input = $('#gr-input', el); const chips = $('#gr-chips', el);
  let genres = []; const suggested = new Set();
  const draw = () => {
    const q = input.value.trim().toLowerCase();
    const list = genres.filter((g) => !q || g.genre.toLowerCase().includes(q));
    chips.innerHTML = list.map((g) => `<button type="button" class="gchip ${suggested.has(g.genre) ? 'on' : ''}" data-g="${esc(g.genre)}">${esc(g.genre)} <small>${g.count}</small></button>`).join('') || '<span class="note">No matching genres yet. Type a new one.</span>';
  };
  input.addEventListener('input', draw);
  chips.addEventListener('click', (e) => { const b = e.target.closest('[data-g]'); if (b) { input.value = b.dataset.g; draw(); input.focus(); } });
  $('#gr-skip', el)?.addEventListener('click', onSkip);
  $('#gr-lfm', el).addEventListener('click', async (e) => {
    const btn = e.currentTarget; busy(btn, true, 'Checking…');
    try {
      const r = await api('GET', `/api/enforcer/lastfm?name=${encodeURIComponent(name)}`);
      const known = new Map(genres.map((g) => [g.genre.toLowerCase(), g.genre]));
      $('#gr-lfmres', el).innerHTML = r.tags.length ? `Last.fm says: ${r.tags.map((t) => { const k = known.get(t.name.toLowerCase()); return `<button type="button" class="gchip ${k ? 'on' : ''}" data-lfm="${esc(k || t.name)}">${k ? '✓ ' : ''}${esc(k || t.name)} <small>${t.count}</small></button>`; }).join(' ')}` : 'Last.fm has no tags for this artist.';
    } catch (err) { toast(err.message, 'error'); }
    busy(btn, false);
  });
  $('#gr-lfmres', el).addEventListener('click', (e) => { const b = e.target.closest('[data-lfm]'); if (b) { input.value = b.dataset.lfm; draw(); input.focus(); } });
  $('#gr-form', el).addEventListener('submit', async (e) => {
    e.preventDefault();
    const genre = input.value.trim(); if (!genre) { onSkip?.(); return; }
    const btn = $('button[type=submit]', el); busy(btn, true, 'Saving…');
    try {
      const { job } = await api('PUT', '/api/enforcer/genre', { name, genre, apply: true });
      toast(`${name} → ${genre}`, 'ok');
      await waitEnforcerJob(job, el);
      loadEnforcerStatus();
      onSaved?.(genre);
    } catch (err) { busy(btn, false); toast(err.message, 'error'); }
  });
  try {
    const info = await api('GET', `/api/enforcer/artist?name=${encodeURIComponent(name)}`);
    genres = info.genres; draw();
    const peek = await api('GET', `/api/enforcer/peek?name=${encodeURIComponent(name)}`);
    const known = new Map(genres.map((g) => [g.genre.toLowerCase(), g.genre]));
    peek.genres.forEach((g) => { const k = known.get(g.genre.toLowerCase()); if (k) suggested.add(k); });
    $('#gr-peek', el).innerHTML = peek.total ? `Tags currently on disk: ${peek.genres.map((g) => `<b>${esc(g.genre)}</b> ×${g.count}`).join(', ')} <small>(${peek.sampled < peek.total ? `sampled ${peek.sampled}/${peek.total}` : peek.total} files)</small>` : 'No audio files found in this artist folder.';
    draw();
  } catch (err) { const p = $('#gr-peek', el); if (p) p.textContent = err.message; }
  input.focus();
}

async function waitEnforcerJob(job, el) {
  if (!job) return;
  const note = document.createElement('div'); note.className = 'note'; el.appendChild(note);
  for (let i = 0; i < 120; i += 1) {
    const { job: j } = await api('GET', '/api/enforcer/job');
    if (!j || j.id !== job.id) break;
    note.textContent = j.state === 'running' ? `Applying tags… ${j.done_artists}/${j.total_artists}` : '';
    if (j.state !== 'running') {
      toast(j.state === 'done' ? `Tagged ${j.totals.changed} of ${j.totals.files} files${j.dry_run ? ' (dry run, nothing written)' : ''}.` : `Apply ${j.state}${j.message ? ': ' + j.message : ''}`, j.state === 'done' ? 'ok' : 'error');
      break;
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
}

// Submit screen: after Picard + Lidarr, tell the enforcer and review the artist here if it's new.
state.genreCard = { forPath: null, artist: null, status: null };
async function renderGenreCard(notifyNow = false) {
  const el = $('#genre-card'); if (!el) return;
  const G = state.genreCard;
  if (!state.enf) await loadEnforcerStatus();
  if (!state.enf?.configured) { el.innerHTML = '<h3>Genre</h3><p class="note">Music Genre Enforcer isn\'t set up. Add its URL in Settings to set the artist\'s genre here.</p>'; return; }
  if (!state.enf.reachable) { el.innerHTML = `<h3>Genre</h3><p class="note">Couldn't reach Music Genre Enforcer. ${esc(state.enf.error || '')}</p>`; return; }
  const folder = state.lidarr?.chosen;
  if (!folder) { el.innerHTML = '<h3>Genre</h3><p class="note">Use “Find where Picard saved it” above first; the artist is worked out from where the files landed.</p>'; return; }
  if (G.forPath !== folder) {
    el.innerHTML = '<h3>Genre</h3><p class="note"><span class="spinner"></span> Checking…</p>';
    try {
      G.artist = (await api('GET', `/api/enforcer/for-folder?path=${encodeURIComponent(folder)}`)).name;
      if (notifyNow) { try { await api('POST', '/api/enforcer/notify'); } catch { /* shown below via status */ } }
      G.status = await api('GET', `/api/enforcer/artist?name=${encodeURIComponent(G.artist)}`);
      G.forPath = folder;
    } catch (err) { el.innerHTML = `<h3>Genre</h3><p class="note">${esc(err.message)}</p>`; return; }
  }
  if (G.status.genre) {
    el.innerHTML = `<h3>Genre</h3><p><b>${esc(G.artist)}</b> is set to <b>${esc(G.status.genre)}</b>. Music Genre Enforcer will tag the new files itself within a few minutes.</p>
      <div class="inline-actions"><button class="btn small" id="gn-ping">Tell it now</button><button class="btn small ghost" id="gn-change">Change genre</button></div>`;
    $('#gn-ping').addEventListener('click', async (e) => { const b = e.currentTarget; busy(b, true, 'Telling…'); try { await api('POST', '/api/enforcer/notify'); toast('Told Music Genre Enforcer to rescan.', 'ok'); } catch (err) { toast(err.message, 'error'); } busy(b, false); });
    $('#gn-change').addEventListener('click', () => { G.status.genre = ''; renderGenreCard(); });
    return;
  }
  el.innerHTML = '<h3>Genre</h3><p class="note">New artist: it needs a genre before Music Genre Enforcer can tag it.</p><div id="gn-review"></div>';
  mountGenreReview($('#gn-review'), G.artist, { onSaved: (genre) => { G.status.genre = genre; renderGenreCard(); } });
}

// The Genres view: every artist still waiting for a genre, one at a time.
state.genresView = { skipped: new Set() };
async function renderGenres() {
  app().innerHTML = '<section class="view"><div class="page-head"><div><h2>New artists</h2><p>Artists in your library that Music Genre Enforcer hasn\'t got a genre for yet.</p></div></div><div id="gv" class="card pad"><span class="spinner"></span></div></section>';
  try {
    const { artists } = await api('GET', '/api/enforcer/queue');
    const queue = artists.filter((a) => !state.genresView.skipped.has(a.name));
    const box = $('#gv');
    if (!queue.length) {
      box.innerHTML = `<h3>${artists.length ? 'All remaining artists skipped' : 'Every artist has a genre'}</h3><p class="note">${artists.length ? `${artists.length} still need one.` : 'New artists show up here after Picard saves them.'}</p>${state.genresView.skipped.size ? '<button class="btn" id="gv-unskip">Review skipped</button>' : ''}`;
      $('#gv-unskip')?.addEventListener('click', () => { state.genresView.skipped.clear(); renderGenres(); });
      loadEnforcerStatus(); return;
    }
    const cur = queue[0];
    box.innerHTML = `<p class="note">${queue.length} to go · folder group ${esc(cur.group)}</p><div id="gv-review"></div>`;
    mountGenreReview($('#gv-review'), cur.name, { onSaved: () => renderGenres(), onSkip: () => { state.genresView.skipped.add(cur.name); renderGenres(); } });
  } catch (err) { $('#gv').innerHTML = `<p class="note">${esc(err.message)}</p>`; }
}

// ReplayGain: same rsgain scan as Picard's ReplayGain 2.0 plugin, run on the files Picard saved.
state.rsgain = { configured: null, options: null, folders: null, chosen: '', result: null, working: false };
async function renderRsgainCard() {
  const el = $('#rsgain-card'); if (!el) return;
  const R = state.rsgain; const rel = state.matches?.release?.selected;
  if (R.forPath !== state.album.path) Object.assign(R, { forPath: state.album.path, folders: null, chosen: '', result: null });
  if (R.configured === null) {
    try { const s = await api('GET', '/api/replaygain/status'); R.configured = s.configured; R.options = s.options; } catch { R.configured = false; }
  }
  if (!R.configured) { el.innerHTML = '<h3>ReplayGain</h3><p class="note">Not set up. Mount the folder holding <code>rsgain</code> into the container and enter its path in Settings to calculate ReplayGain here.</p>'; return; }
  const o = R.options; const folders = R.folders;
  const sel = (v, cur, label) => `<option value="${v}" ${v === cur ? 'selected' : ''}>${label}</option>`;
  const chk = (id, on, label) => `<label style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="${id}" ${on ? 'checked' : ''}> ${label}</label>`;
  const res = R.result;
  el.innerHTML = `<h3>ReplayGain</h3>
    <p class="note">Run this after Picard has saved the album and before Lidarr rescans it. It uses the same rsgain settings as Picard's ReplayGain 2.0 plugin (remembered for next time) and only touches files tagged with this release.</p>
    <div class="inline-actions">
      <button class="btn small" id="rg-find" ${rel ? '' : 'disabled'}>${ICON.search} Find where Picard saved it</button>
      ${folders && folders.length ? `<select id="rg-folder">${folders.map((f) => `<option ${f === R.chosen ? 'selected' : ''}>${esc(f)}</option>`).join('')}</select>` : ''}
    </div>
    ${folders && !folders.length ? '<p class="note">No freshly saved files with this release ID were found yet. Save in Picard first, or give it a moment: it saves everything it has loaded before this album.</p>' : ''}
    ${folders && folders.length ? `<div class="rg-opts" style="display:grid;gap:8px;margin:12px 0">
      ${chk('rg-album', o.album, 'Calculate album gain/peak')}
      ${chk('rg-tp', o.true_peak, 'Use true peak')}
      ${chk('rg-ref', o.reference_tag, 'Write reference loudness tag')}
      <label class="field"><span>Target loudness (LUFS)</span><input type="number" id="rg-target" min="-30" max="-5" step="1" value="${o.target}"></label>
      <label class="field"><span>Clipping protection</span><select id="rg-clip">${sel('n', o.clip_mode, 'Disabled')}${sel('p', o.clip_mode, 'Enabled for positive gain values only')}${sel('a', o.clip_mode, 'Always enabled')}</select></label>
      <label class="field"><span>Max peak (dB)</span><input type="number" id="rg-maxpeak" step="0.1" value="${o.max_peak}"></label>
      <label class="field"><span>Opus files</span><select id="rg-opus">${sel('d', o.opus_mode, 'Write standard ReplayGain tags')}${sel('r', o.opus_mode, 'Write R128 gain tags')}${sel('s', o.opus_mode, 'R128 tags, referenced to -23 LUFS')}</select></label>
    </div>
    <div class="inline-actions"><button class="btn small" id="rg-scan">Scan only</button><button class="btn small primary" id="rg-write">Calculate &amp; write tags</button></div>` : ''}
    ${rel ? '' : '<p class="note">Needs a release ID first.</p>'}
    ${res ? `<div class="note" style="margin-top:10px">
      <b style="color:var(${res.error ? '--warn' : '--ok'})">${esc(res.error || (res.wrote ? `Wrote ReplayGain tags to ${res.verified} of ${res.tracks.length} files.` : 'Scan only, nothing written.'))}</b>
      ${res.tracks ? `<table class="rg-table" style="margin-top:6px;border-collapse:collapse"><tr><th align="left">Track</th><th>Loudness</th><th>Gain</th><th>Peak dB</th></tr>
        ${[...res.tracks, ...(res.album ? [res.album] : [])].map((r) => `<tr><td>${esc(r.filename.split('/').pop())}</td><td align="right">${esc(r.loudness)}</td><td align="right">${esc(r.gain)}</td><td align="right">${esc(r.peak_db)}</td></tr>`).join('')}</table>` : ''}
      ${(res.notes || []).map((n) => `<br>${esc(n)}`).join('')}</div>` : ''}`;
  const read = () => {
    R.chosen = $('#rg-folder').value;
    R.options = { album: $('#rg-album').checked, true_peak: $('#rg-tp').checked, reference_tag: $('#rg-ref').checked, target: Number($('#rg-target').value), clip_mode: $('#rg-clip').value, max_peak: Number($('#rg-maxpeak').value), opus_mode: $('#rg-opus').value };
  };
  $('#rg-find')?.addEventListener('click', async (e) => {
    const btn = e.currentTarget; busy(btn, true, 'Looking…');
    try { R.folders = (await api('POST', '/api/lidarr/locate', { release_mbid: rel })).folders; R.chosen = R.folders[0] || ''; R.result = null; } catch (err) { toast(err.message, 'error'); }
    renderRsgainCard();
  });
  const run = (write) => async (e) => {
    const btn = e.currentTarget; read(); busy(btn, true, write ? 'Writing…' : 'Scanning…');
    try { R.result = await api('POST', '/api/replaygain/run', { path: R.chosen, release_mbid: rel, write, options: R.options }); } catch (err) { R.result = { error: err.message }; }
    renderRsgainCard();
  };
  $('#rg-scan')?.addEventListener('click', run(false));
  $('#rg-write')?.addEventListener('click', run(true));
}

// Lidarr: after Picard has saved the album, register the exact release and let Lidarr map the files in place.
state.lidarr = { configured: null, folders: null, chosen: '', result: null, working: false };
async function renderLidarrCard() {
  const el = $('#lidarr-card'); if (!el) return;
  const L = state.lidarr; const rel = state.matches?.release?.selected;
  if (L.forPath !== state.album.path) Object.assign(L, { forPath: state.album.path, folders: null, chosen: '', result: null });
  if (L.configured === null) { try { L.configured = (await api('GET', '/api/lidarr/status')).configured; } catch { L.configured = false; } }
  if (!L.configured) { el.innerHTML = '<h3>Lidarr</h3><p class="note">Not set up. Add the URL, API key and root folder in Settings to hand finished albums to Lidarr.</p>'; return; }
  const folders = L.folders;
  el.innerHTML = `<h3>Lidarr</h3>
    <p class="note">After Picard has saved the album: add it to Lidarr by this exact release, then Lidarr rescans where Picard put the files. Nothing is moved or renamed.</p>
    <div class="inline-actions">
      <button class="btn small" id="ld-find" ${rel ? '' : 'disabled'}>${ICON.search} Find where Picard saved it</button>
      ${folders && folders.length ? `<select id="ld-folder">${folders.map((f) => `<option ${f === L.chosen ? 'selected' : ''}>${esc(f)}</option>`).join('')}</select>
        <button class="btn small" id="ld-dry">Check only</button><button class="btn small primary" id="ld-send">Add to Lidarr</button>` : ''}
    </div>
    ${folders && !folders.length ? '<p class="note">No freshly saved files with this release ID were found yet. Save in Picard first, or give it a moment: it saves everything it has loaded before this album.</p>' : ''}
    ${rel ? '' : '<p class="note">Needs a release ID first.</p>'}
    ${L.result ? `<div class="note" style="margin-top:10px"><b style="color:var(${L.result.ok ? '--ok' : '--warn'})">${esc(L.result.summary)}</b>${L.result.dry_run ? ' (check only, nothing changed)' : ''}<br>${L.result.steps.map(esc).join(' → ')}${L.result.url ? ` <a href="${esc(L.result.url)}" target="_blank" rel="noopener">Open in Lidarr</a>` : ''}</div>` : ''}`;
  $('#ld-find')?.addEventListener('click', async (e) => {
    const btn = e.currentTarget; busy(btn, true, 'Looking…');
    try { L.folders = (await api('POST', '/api/lidarr/locate', { release_mbid: rel })).folders; L.chosen = L.folders[0] || ''; L.result = null; } catch (err) { toast(err.message, 'error'); }
    renderLidarrCard(); renderGenreCard();
  });
  const go = (dry) => async (e) => {
    const btn = e.currentTarget; L.chosen = $('#ld-folder').value; busy(btn, true, dry ? 'Checking…' : 'Sending…');
    try { L.result = await api('POST', '/api/lidarr/send', { path: L.chosen, release_mbid: rel, dry_run: dry }); } catch (err) { L.result = { ok: false, summary: err.message, steps: [] }; }
    renderLidarrCard(); if (L.result?.ok && !dry) renderGenreCard(true);
  };
  $('#ld-dry')?.addEventListener('click', go(true));
  $('#ld-send')?.addEventListener('click', go(false));
}

function timelineStep(key, n, isNext) {
  const info = entityInfo(key);
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
  if (isArtistKey(key)) return seedUrl(key, '/api/seed/artist', { name: artistNames()[artistIndex(key)] });
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
    const body = { title: a.title, artist: a.artist, artists: isSplit() ? artistNames() : [], join_phrase: joinPhrase(), primary_type: f.get('primary_type'), secondary_types: f.getAll('sec'), disambiguation: f.get('disambiguation'), edit_note: f.get('edit_note') };
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
        release_group_mbid: sel('release-group'), artist_mbid: sel('artist'), artists: artistKeys().map((k) => ({ name: artistNames()[artistIndex(k)], mbid: sel(k) })), join_phrase: joinPhrase(), label_mbid: sel('label'), details,
      });
      postForm(w, action, fields);
      state.opened.release = true;
      renderSubmit();
    } catch (err) { w.close(); toast(err.message, 'error'); }
  });
}


// ---------------------------------------------------------------- Library (batch mode)
// Point it at a folder like "Unmanaged": find every album, match each against
// MusicBrainz, then triage into Ready / Review / Missing. Matching is read-only;
// only the Ready tab can ever move files, and only through a gated, verified run.
const LIB_TABS = [
  ['ready', 'Ready', 'Matches a release exactly. Eligible for tagging in Picard.'],
  ['review', 'Review', 'Close but not exact, or several identical editions. You decide.'],
  ['missing', 'Create on MB', 'Not on MusicBrainz. Work through these to create them.'],
  ['processing', 'Processing', 'Being tagged and saved by Picard right now.'],
  ['in_picard', 'In Picard', 'Tagged and loaded in Picard.'],
  ['done', 'Done', 'Finished.'],
  ['problem', 'Problems', 'Something went wrong. Check these first.'],
  ['skipped', 'Skipped', 'You skipped these.'],
  ['pending', 'Waiting', 'Found but not matched yet.'],
];
const PILL_FOR = { ready: 'existing', review: 'ambiguous', missing: 'missing', in_picard: 'existing', done: 'existing', problem: 'missing', skipped: 'unchecked', pending: 'unchecked', processing: 'ambiguous' };
const LABEL_FOR = { ready: 'Ready', review: 'Review', missing: 'Create on MB', in_picard: 'In Picard', done: 'Done', problem: 'Problem', skipped: 'Skipped', pending: 'Waiting', processing: 'Processing' };

state.lib = { dismissed: '', root: null, tab: 'ready', albums: [], counts: null, status: null, q: '', roots: [], timer: null, sig: '', shown: 100 };

async function openLibrary(root) {
  state.lib.root = root || null;
  state.lib.tab = 'ready';
  state.lib.albums = [];
  state.lib.counts = null;
  state.lib.shown = 100;
  go('library');
}

function libStop() { clearInterval(state.lib.timer); state.lib.timer = null; }

async function renderLibrary() {
  const lib = state.lib;
  libStop();
  if (!lib.root) return renderLibraryHome();
  app().innerHTML = `<section class="view" id="lib">
    <div class="page-head"><div><h2>${esc(lib.root.split('/').slice(-1)[0])}</h2><p class="note">${esc(lib.root)}</p></div>
      <div class="lib-actions" id="lib-actions"></div></div>
    <div id="lib-job"></div>
    <div class="lib-tiles" id="lib-tiles"></div>
    <div class="card toolbar" style="margin-top:14px"><input class="search" id="lib-q" type="text" placeholder="Filter by artist, title or path…" style="max-width:none;flex:1" value="${esc(lib.q)}" aria-label="Filter albums"></div>
    <div id="lib-list" class="lib-list"></div>
  </section>`;
  $('#lib-q').addEventListener('input', debounce((e) => { lib.q = e.target.value; lib.shown = 100; loadLibraryList(); }, 250));
  try { await api('POST', '/api/batch/reconcile', { path: lib.root }); } catch { /* a job may be running */ }
  await refreshLibraryStatus(true);
  const total = lib.counts?.total || 0;
  if (!total && !lib.status?.busy) await libRun('/api/batch/discover', {}, 'Scanning for albums…');
  lib.timer = setInterval(() => { if (state.view === 'library' && !document.hidden) refreshLibraryStatus(false); }, 2000);
}

const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

async function renderLibraryHome() {
  let roots = [];
  try { roots = (await api('GET', '/api/batch/roots')).roots; } catch { /* none yet */ }
  app().innerHTML = `<section class="view">
    <div class="page-head"><div><h2>Library batch</h2><p>Point FilesToMB at a folder such as <b>Unmanaged</b> and it will find every album, check each against MusicBrainz, and sort them into <b>Ready</b>, <b>Review</b> and <b>Create on MB</b>.</p></div></div>
    <div class="card pad">
      <h3>How it stays safe</h3>
      <ul class="safe-list">
        <li><b>Finding and matching never change a file.</b> They only read tags and ask MusicBrainz.</li>
        <li><b>“Ready” is strict:</b> every file must match a track on one specific release, with agreeing titles, lengths and artist. Anything less goes to Review or Create.</li>
        <li><b>Only Ready albums can be processed</b>, one at a time, with a trial of one first. Each is re-checked, verified after Picard saves it, and the whole batch stops at the first problem.</li>
        <li><b>Nothing is ever deleted.</b> Every action is written to an audit log.</li>
      </ul>
      <button class="btn primary" id="lib-pick">${ICON.folder} Choose a folder to batch…</button>
    </div>
    ${roots.length ? `<h3 style="margin:22px 0 10px">Recent batches</h3><div class="folder-grid">${roots.map((r) => `<div class="folder-wrap"><button class="folder album" data-root="${esc(r.path)}" style="padding-right:18px"><span class="ico">${ICON.box}</span><span class="name">${esc(r.path)}<small style="display:block;color:var(--muted)">${r.albums} album${r.albums === 1 ? '' : 's'}</small></span></button></div>`).join('')}</div>` : ''}
  </section>`;
  $('#lib-pick').addEventListener('click', () => { toast('Browse to the folder, then press “Batch this folder”.'); go('browse'); });
  $$('[data-root]').forEach((b) => b.addEventListener('click', () => openLibrary(b.dataset.root)));
}

async function refreshLibraryStatus(forceList) {
  const lib = state.lib;
  if (!lib.root) return;
  try { lib.status = await api('GET', `/api/batch/status?root=${encodeURIComponent(lib.root)}`); } catch { return; }
  lib.counts = lib.status.counts;
  const sig = JSON.stringify([lib.counts, lib.status.phase]);
  renderLibraryChrome();
  const wasMatching = lib.sig.includes('"matching"') || lib.sig.includes('"processing"');
  if (forceList || sig !== lib.sig) {
    lib.sig = sig;
    // After a run finishes, land on the first tab that has something in it.
    if (wasMatching && !lib.status.busy && !(lib.counts?.[lib.tab])) {
      const first = ['ready', 'review', 'missing', 'problem', 'in_picard', 'done'].find((k) => lib.counts?.[k]);
      if (first) lib.tab = first;
    }
    await loadLibraryList();
  }
}

function renderLibraryChrome() {
  const lib = state.lib, st = lib.status, c = lib.counts || {};
  if (!$('#lib-tiles')) return;
  $('#lib-tiles').innerHTML = LIB_TABS.filter(([k]) => !['pending', 'processing'].includes(k) || c[k]).map(([k, label, hint]) => `<button class="tile ${lib.tab === k ? 'on' : ''} t-${k}" data-tab="${k}" title="${esc(hint)}"><b>${c[k] || 0}</b><span>${label}</span></button>`).join('');
  $$('#lib-tiles [data-tab]').forEach((b) => b.addEventListener('click', () => { lib.tab = b.dataset.tab; lib.shown = 100; renderLibraryChrome(); loadLibraryList(); }));

  const busyNow = st?.busy;
  $('#lib-actions').innerHTML = `
    ${c.pending ? `<button class="btn ${c.total && !busyNow ? 'primary' : ''}" id="lib-match" ${busyNow ? 'disabled' : ''}>${ICON.search} Match ${c.pending} album${c.pending === 1 ? '' : 's'}</button>` : ''}
    <button class="btn" id="lib-process" ${busyNow || !(c.ready) ? 'disabled' : ''} title="${c.ready ? 'Tag and save the Ready albums through Picard' : 'Nothing is Ready yet'}">${ICON.release} Process Ready (${c.ready || 0})…</button>
    <button class="btn ghost" id="lib-rescan" ${busyNow ? 'disabled' : ''} title="Look for new album folders">Rescan folders</button>
    <button class="btn ghost" id="lib-more" title="More actions">⋯</button>`;
  $('#lib-match')?.addEventListener('click', () => libRun('/api/batch/match', {}, 'Matching…'));
  $('#lib-process')?.addEventListener('click', openProcessDialog);
  $('#lib-rescan')?.addEventListener('click', () => libRun('/api/batch/discover', {}, 'Scanning…'));
  $('#lib-more')?.addEventListener('click', openLibraryMore);

  // Live job panel.
  const job = $('#lib-job');
  if (!st || (!busyNow && (!st.last_result || st.last_result === lib.dismissed))) { job.innerHTML = ''; return; }
  const p = st.progress || {};
  const pct = p.total ? Math.round((p.done / p.total) * 100) : 0;
  const stopped = st.last_result?.startsWith('Stopped') || st.last_result?.includes('unexpected');
  job.innerHTML = `<div class="card pad job ${stopped && !busyNow ? 'err' : ''}">
    <div class="job-head"><b>${busyNow ? ({ discovering: 'Scanning folders', matching: 'Matching with MusicBrainz', processing: 'Processing through Picard' }[st.phase] || 'Working') : (stopped ? 'Stopped' : 'Last run')}</b>
      ${busyNow ? `<span class="note">${p.done || 0} / ${p.total || 0}</span><button class="btn small" id="lib-stop">${st.stop_requested ? 'Stopping…' : 'Stop'}</button>` : `<button class="btn small ghost" id="lib-dismiss">Dismiss</button>`}</div>
    ${busyNow && p.total ? `<div class="bar" style="height:8px;margin:8px 0"><i style="width:${pct}%"></i></div>` : ''}
    ${busyNow && p.current ? `<div class="note job-cur">${esc(p.current.slice(state.lib.root.length + 1))}</div>` : ''}
    ${!busyNow && st.last_result ? `<div class="${stopped ? 'job-err' : ''}">${esc(st.last_result)}</div>` : ''}
    ${(st.events || []).length && (busyNow || stopped) ? `<div class="job-log">${st.events.slice(-6).map((e) => `<div class="ev ${e.level}">${esc(e.message)}</div>`).join('')}</div>` : ''}
  </div>`;
  $('#lib-stop')?.addEventListener('click', async () => { await api('POST', '/api/batch/stop'); refreshLibraryStatus(false); });
  $('#lib-dismiss')?.addEventListener('click', () => { lib.dismissed = st.last_result; job.innerHTML = ''; });
}

async function libRun(url, extra, label) {
  try {
    await api('POST', url, { path: state.lib.root, ...extra });
    state.lib.dismissed = '';
    toast(label);
    await refreshLibraryStatus(true);
  } catch (e) { toast(e.message, 'error'); }
}

async function loadLibraryList() {
  const lib = state.lib;
  const host = $('#lib-list');
  if (!host || !lib.root) return;
  try {
    const q = new URLSearchParams({ root: lib.root, status: lib.tab, limit: String(lib.shown), q: lib.q });
    const data = await api('GET', `/api/batch/albums?${q}`);
    lib.albums = data.albums;
    lib.counts = data.counts;
  } catch (e) { host.innerHTML = `<div class="empty card pad">${esc(e.message)}</div>`; return; }
  renderLibraryChrome();
  const hint = LIB_TABS.find(([k]) => k === lib.tab)?.[2];
  if (!lib.albums.length) { host.innerHTML = `<div class="empty card pad"><p>${lib.q ? 'No albums match that filter.' : `Nothing in “${LIB_TABS.find(([k]) => k === lib.tab)?.[1]}”.`}</p><p class="note">${esc(hint || '')}</p></div>`; return; }
  host.innerHTML = `<p class="hint" style="margin:14px 0 8px">${esc(hint || '')}</p>` + lib.albums.map(libRow).join('') +
    ((lib.counts[lib.tab] || 0) > lib.albums.length ? `<div style="text-align:center;margin:14px"><button class="btn" id="lib-more-rows">Show more (${(lib.counts[lib.tab] || 0) - lib.albums.length} left)</button></div>` : '');
  $('#lib-more-rows')?.addEventListener('click', () => { lib.shown += 200; loadLibraryList(); });
  $$('#lib-list [data-act]').forEach((b) => b.addEventListener('click', () => libAct(b)));
}

const relPath = (a) => a.path.slice(state.lib.root.length + 1);

function libRow(a) {
  const heading = a.title ? `${esc(a.artist)} — ${esc(a.title)}${a.year ? ` <span class="note">(${esc(a.year)})</span>` : ''}` : esc(relPath(a).split('/').slice(-2).join(' / '));
  const meta = `${a.tracks ? `${a.tracks} track${a.tracks === 1 ? '' : 's'}` : ''}${a.duration_ms ? ` · ${fmtLen(a.duration_ms)}` : ''}`;
  const cands = a.verdict?.candidates || [];
  let body = '';
  if (a.status === 'review') {
    body = `<div class="cands-mini">${cands.slice(0, 4).map((c) => `<div class="cmini ${c.confident ? 'ok' : ''}">
      <div class="cinfo"><a href="https://musicbrainz.org/release/${c.mbid}" target="_blank" rel="noopener"><b>${esc(c.title)}</b></a> <span class="note">${esc(c.artist)} · ${esc(c.date || '?')} ${esc(c.country || '')} · ${c.track_count} tracks</span>
        <div class="note">${c.confident ? 'Every file matches a track on this release.' : c.track_exact ? `The tracks match exactly, but ${esc(c.problems.join('; '))}.` : esc(c.problems.join('; '))}</div></div>
      <button class="btn small ${c.confident ? 'primary' : ''}" data-act="use" data-path="${esc(a.path)}" data-mbid="${c.mbid}" ${c.confident || c.track_exact ? '' : 'disabled title="Not a complete match. Open the album to handle it by hand."'}>Use this</button></div>`).join('')}</div>`;
  } else if (a.status === 'ready' && cands[0]) {
    const c = cands.find((x) => x.mbid === a.release_mbid) || cands[0];
    body = `<div class="note">→ <a href="https://musicbrainz.org/release/${c.mbid}" target="_blank" rel="noopener">${esc(c.title)}</a> · ${esc(c.date || '?')} ${esc(c.country || '')} · ${c.track_count} tracks · ${esc(a.message || '')}</div>`;
  } else if (a.message) {
    body = `<div class="note">${esc(a.message)}</div>`;
  }
  // Before creating something, see what's already closest on MusicBrainz: this is how duplicates get avoided.
  if (a.status === 'missing' && cands.length) {
    body += `<div class="closest note">Closest on MusicBrainz: ${cands.slice(0, 2).map((c) => `<a href="https://musicbrainz.org/release/${c.mbid}" target="_blank" rel="noopener">${esc(c.artist)} — ${esc(c.title)}</a> (${c.track_count} tracks, ${Math.round(c.coverage_local * 100)}% of your files)`).join(' · ')}</div>`;
  }
  const acts = [];
  acts.push(`<button class="btn small ${a.status === 'missing' ? 'primary' : ''}" data-act="open" data-path="${esc(a.path)}">${a.status === 'missing' ? 'Create…' : 'Open'}</button>`);
  if (['missing', 'problem', 'skipped', 'review'].includes(a.status)) acts.push(`<button class="btn small ghost" data-act="reset" data-path="${esc(a.path)}" title="Check MusicBrainz again">Re-check</button>`);
  if (['review', 'ready', 'missing'].includes(a.status)) acts.push(`<button class="btn small ghost" data-act="skip" data-path="${esc(a.path)}">Skip</button>`);
  if (a.status === 'review') acts.push(`<button class="btn small ghost" data-act="missing" data-path="${esc(a.path)}" title="None of these are right">Not on MB</button>`);
  return `<div class="card lrow"><div class="lmain"><div class="lhead"><span class="pill ${PILL_FOR[a.status]}">${LABEL_FOR[a.status]}</span><b class="ltitle">${heading}</b><span class="note">${meta}</span></div>
    <div class="lpath">${esc(relPath(a))}</div>${body}</div><div class="lacts">${acts.join('')}</div></div>`;
}

async function libAct(btn) {
  const path = btn.dataset.path, act = btn.dataset.act;
  if (act === 'open') return openFromBatch(path);
  busy(btn, true, '');
  try {
    await api('POST', '/api/batch/resolve', { path, action: act, release_mbid: btn.dataset.mbid });
    if (act === 'reset') await libRun('/api/batch/match', {}, 'Re-checking…');
    else { toast(act === 'use' ? 'Marked Ready with the release you picked.' : 'Updated.', 'ok'); await refreshLibraryStatus(true); }
  } catch (e) { busy(btn, false); toast(e.message, 'error'); }
}

// Open one album in the normal Review → Submit flow, remembering we came from the batch.
async function openFromBatch(path) {
  state.batchCtx = { root: state.lib.root, tab: state.lib.tab };
  libStop();
  await scan(path);
}

async function nextInQueue() {
  const ctx = state.batchCtx;
  if (!ctx) return;
  try {
    const { albums } = await api('GET', `/api/batch/albums?root=${encodeURIComponent(ctx.root)}&status=missing&limit=500`);
    const current = state.album?.path;
    const idx = albums.findIndex((a) => a.path === current);
    const next = albums.slice(idx + 1).concat(albums.slice(0, Math.max(idx, 0))).find((a) => a.path !== current);
    if (!next) { toast('That was the last one in the “Create on MB” list.', 'ok'); return openLibrary(ctx.root); }
    state.batchCtx = ctx;
    await scan(next.path);
  } catch (e) { toast(e.message, 'error'); }
}

function batchBar() {
  if (!state.batchCtx) return '';
  return `<button class="btn" id="bt-back" title="Back to the batch list">${ICON.back} Batch list</button>`;
}
function wireBatchBar() {
  $('#bt-back')?.addEventListener('click', () => openLibrary(state.batchCtx.root));
  $('#bt-next')?.addEventListener('click', nextInQueue);
}

// ---- processing (the only step that moves files)
async function openProcessDialog() {
  const lib = state.lib, c = lib.counts || {};
  await loadPicardStatus(true);
  const st = state.picard.status;
  const connected = st?.connected;
  openDialog(`<form id="proc-form" method="dialog">
    <div class="dlg-head"><h3>Process ready albums</h3><p>${c.ready || 0} album${c.ready === 1 ? '' : 's'} match a MusicBrainz release exactly.</p></div>
    <div class="dlg-body">
      <div class="stepnote"><span class="num">1</span><div>For each album, one at a time: re-check it against MusicBrainz, <b>write the release IDs into the files</b>, load it in Picard, tell Picard to <b>save (rename and move) it</b>, then confirm the files left this folder${lib.status?.dest_configured ? ' and arrived at Picard\'s destination with the right release ID' : ''}.</div></div>
      <div class="stepnote"><span class="num">2</span><div>The batch <b>stops at the first problem</b>. Nothing is deleted. Every step is written to the audit log.</div></div>
      ${lib.status?.dest_configured ? '' : '<div class="banner"><span>Picard\'s destination folder isn\'t configured (<code>PICARD_DEST_ROOT</code>), so arrival can\'t be verified, only that the files left.</span></div>'}
      <label class="field"><span>How many albums</span><select name="limit">
        <option value="1">1 (a trial run, recommended first)</option>
        <option value="5">5</option><option value="10">10</option><option value="25">25</option>
        <option value="${Math.min(c.ready || 1, 500)}">All ${c.ready || 0} ready</option></select></label>
      <label class="check"><input type="checkbox" name="clear" required> <span>Picard has nothing unsaved that I care about. FilesToMB will <b>clear Picard's file lists</b> first, so “save matched” can only ever touch the album being processed.</span></label>
      ${connected ? '' : `<div class="banner"><span>${st?.configured ? 'Picard isn\'t reachable right now.' : 'Picard isn\'t linked to FilesToMB (see the README).'}</span></div>`}
    </div>
    <div class="dlg-foot"><button class="btn" type="button" id="dlg-cancel">Cancel</button><button class="btn primary" type="submit" ${connected ? '' : 'disabled'}>Start processing</button></div></form>`);
  $('#dlg-cancel').addEventListener('click', closeDialog);
  $('#proc-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    closeDialog();
    await libRun('/api/batch/process', { limit: Number(f.get('limit')), clear_picard: !!f.get('clear') }, 'Processing started.');
  });
}

function openLibraryMore() {
  openDialog(`<div class="dlg-head"><h3>More</h3></div><div class="dlg-body"><div class="list">
    <button id="mo-audit">Audit log: every action taken on your files</button>
    <button id="mo-clean">Remove empty folders under this batch (only folders with nothing in them)</button>
    <button id="mo-all">Re-match everything still Waiting, Missing or in Review</button></div></div>
    <div class="dlg-foot"><button class="btn" id="dlg-cancel">Close</button></div>`);
  $('#dlg-cancel').addEventListener('click', closeDialog);
  $('#mo-audit').addEventListener('click', openAudit);
  $('#mo-clean').addEventListener('click', async () => {
    try { const r = await api('POST', '/api/batch/cleanup', { path: state.lib.root }); closeDialog(); toast(`Removed ${r.removed} empty folder${r.removed === 1 ? '' : 's'}.`, 'ok'); } catch (e) { toast(e.message, 'error'); }
  });
  $('#mo-all').addEventListener('click', async () => {
    closeDialog();
    try {
      const lists = await Promise.all(['missing', 'review'].map((s) => api('GET', `/api/batch/albums?root=${encodeURIComponent(state.lib.root)}&status=${s}&limit=500`)));
      const paths = lists.flatMap((l) => l.albums.map((a) => a.path));
      await libRun('/api/batch/match', { rematch: paths }, `Re-matching ${paths.length} albums…`);
    } catch (e) { toast(e.message, 'error'); }
  });
}

async function openAudit() {
  try {
    const { lines } = await api('GET', '/api/batch/audit');
    openDialog(`<div class="dlg-head"><h3>Audit log</h3><p>Newest at the bottom. Stored in the /config volume as batch-audit.log.</p></div>
      <div class="dlg-body"><pre class="audit">${lines.length ? esc(lines.join('\n')) : 'Nothing has been done yet.'}</pre></div>
      <div class="dlg-foot"><button class="btn" id="dlg-cancel">Close</button></div>`);
    $('#dlg-cancel').addEventListener('click', closeDialog);
  } catch (e) { toast(e.message, 'error'); }
}

// ---------------------------------------------------------------- Picard
async function loadPicardStatus(force = false) {
  const p = state.picard;
  if (!force && p.status && Date.now() - p.statusAt < 15000) return;
  try { p.status = await api('GET', '/api/picard/status'); p.statusAt = Date.now(); } catch { p.status = { configured: false, connected: false, url: '' }; }
  if (state.view === 'submit') renderPicardCard();
}

function renderPicardCard() {
  const host = $('#picard-card');
  if (!host) return;
  const p = state.picard;
  const st = p.status;
  const rel = state.matches?.release?.selected;
  const pill = !st ? '' : !st.configured ? '<span class="pill unchecked">Not set up</span>' : st.connected ? '<span class="pill existing">Connected</span>' : '<span class="pill missing">Not reachable</span>';
  const open = st?.url ? `<a class="btn small" href="${esc(st.url)}" target="_blank" rel="noopener">${ICON.ext} Open Picard</a>` : '';
  let body = '';
  if (!st) body = '<div class="skeleton" style="height:44px"></div>';
  else if (!st.configured) body = '<p class="note">Picard isn\'t linked to FilesToMB. Share Picard\'s runtime folder with this container and set <code>PICARD_PIPE_DIR</code> (see the README) to tag, load and save from here.</p>';
  else {
    const step = (n, done, title, detail, action) => `<div class="pstep ${done ? 'done' : ''}"><span class="pnum">${done ? ICON.check : n}</span><div class="pbody"><b>${title}</b><small>${detail}</small></div>${action || ''}</div>`;
    const sent = p.sent;
    body = `<div class="psteps">
      ${step(1, !!sent, 'Tag files and load in Picard', sent ? `${sent.tagged} file${sent.tagged === 1 ? '' : 's'} tagged · ${sent.matched} matched to the release${sent.loaded ? ' · loaded in Picard' : ''}` : 'Writes this release\'s MusicBrainz IDs into the files so Picard puts them straight onto it.', `<button class="btn ${sent ? '' : 'primary'}" id="picard-send" ${rel && st.connected ? '' : 'disabled'} title="${rel ? (st.connected ? '' : 'Picard isn\'t reachable') : 'Needs a release ID first'}">${sent ? 'Redo' : 'Preview &amp; send'}</button>`)}
      ${step(2, !!sent && p.saved, 'Check it in Picard', 'The files should appear matched under your release. Fix anything odd there.', open)}
      ${step(3, p.fingerprinted, 'Generate AcoustID fingerprints (optional)', p.fingerprinted ? 'Requested. Picard calculates them in the background; they are written to the files when you save.' : 'Picard fingerprints the matched files so the AcoustID is saved into their tags. Runs for every matched file in Picard and can take a while.', `<button class="btn" id="picard-fingerprint" ${sent && st.connected ? '' : 'disabled'}>${p.fingerprinted ? 'Run again' : 'Generate'}</button>`)}
      ${step(4, p.saved, 'Save in Picard', p.saved ? 'Save requested. Picard is rewriting tags and moving files with your own settings, so the folder may have moved.' : 'Saves every matched file currently in Picard (not just this album). Tags, renaming and moving follow your own Picard settings.', `<button class="btn ${sent && !p.saved ? 'primary' : ''}" id="picard-save" ${sent && st.connected ? '' : 'disabled'}>${p.saved ? 'Save again' : 'Save in Picard'}</button>${p.saved ? '<button class="btn" id="picard-clear" title="Remove saved files from Picard\'s album pane">Clear saved</button>' : ''}`)}
    </div>`;
  }
  host.innerHTML = `<div class="picard-head"><h3>Picard</h3>${pill}<span class="note grow">Tag, load and save in your Picard without leaving FilesToMB.</span><button class="btn small ghost" id="picard-refresh" title="Re-check the connection">Refresh</button></div>${body}`;
  $('#picard-refresh')?.addEventListener('click', () => loadPicardStatus(true));
  $('#picard-send')?.addEventListener('click', openPicardPlan);
  $('#picard-fingerprint')?.addEventListener('click', picardFingerprint);
  $('#picard-save')?.addEventListener('click', picardSave);
  $('#picard-clear')?.addEventListener('click', picardClear);
}

async function openPicardPlan() {
  const rel = state.matches.release?.selected;
  openDialog('<div class="dlg-head"><h3>Matching tracks…</h3></div><div class="dlg-body"><div class="scanning" style="padding:30px 0"><span class="spinner"></span></div></div>');
  try {
    const plan = await api('POST', '/api/picard/plan', { path: state.album.path, release_mbid: rel });
    const bad = plan.pairs.filter((x) => !x.match).length;
    const connected = state.picard.status?.connected;
    openDialog(`<div class="dlg-head"><h3>Tag files for Picard</h3><p>${esc(plan.release.artist)} · ${esc(plan.release.title)}${plan.release.date ? ` (${esc(plan.release.date)})` : ''} · ${plan.release.track_count} tracks on MusicBrainz</p></div>
      <div class="dlg-body">
        ${plan.complete ? `<div class="banner ok">${ICON.check.replace('<svg', '<svg width="18" height="18"')}<span>Every file matches a track on the release.</span></div>`
          : `<div class="banner">${ICON.alert.replace('<svg', '<svg width="18" height="18"')}<span>${bad ? `${bad} file${bad === 1 ? '' : 's'} didn't match a track. ` : ''}${plan.unmatched_release_tracks.length ? `${plan.unmatched_release_tracks.length} track${plan.unmatched_release_tracks.length === 1 ? '' : 's'} on the release ${plan.unmatched_release_tracks.length === 1 ? 'has' : 'have'} no file. ` : ''}Picard will still try to match them itself.</span></div>`}
        <p class="note">Only MusicBrainz ID tags are added. Picard rewrites everything else when you save.</p>
        <div class="pairs">${plan.pairs.map((x) => `<div class="pair ${x.match ? '' : 'nomatch'}"><span class="l">${x.track_number ? esc(x.track_number.split('/')[0]) + '. ' : ''}${esc(x.title)}</span><span class="arrow">${x.match ? '→' : '✕'}</span><span class="r">${x.match ? `${plan.pairs.some((y) => y.match && y.match.disc > 1) || x.match.disc > 1 ? `${x.match.disc}-` : ''}${x.match.position}. ${esc(x.match.title)} <small>${x.score}%</small>` : 'no matching track'}</span></div>`).join('')}
          ${plan.unmatched_release_tracks.map((t) => `<div class="pair nomatch"><span class="l">(no file)</span><span class="arrow">✕</span><span class="r">${t.disc > 1 ? `${t.disc}-` : ''}${t.position}. ${esc(t.title)}</span></div>`).join('')}
        </div>
      </div>
      <div class="dlg-body" style="padding-top:0"><label style="display:flex;gap:8px;align-items:flex-start"><input type="checkbox" id="pp-clear" checked style="margin-top:3px"><span>Clear Picard's file list first (recommended)<br><small class="note">“Save in Picard” saves <b>every</b> matched file Picard has loaded, so anything left from earlier albums would be re-saved and moved too. Unsaved edits made inside Picard are discarded.</small></span></label></div>
      <div class="dlg-foot"><button class="btn" id="dlg-cancel">Cancel</button><button class="btn" id="pp-tag" title="Write the IDs but don't touch Picard">Tag files only</button><button class="btn primary" id="pp-send" ${connected ? '' : 'disabled'}>Tag &amp; load in Picard</button></div>`);
    $('#dlg-cancel').addEventListener('click', closeDialog);
    const run = (tagOnly) => async (e) => {
      const btn = e.currentTarget;
      busy(btn, true, 'Working…');
      try {
        const res = await api('POST', '/api/picard/send', { path: state.album.path, release_mbid: rel, tag_only: tagOnly, clear_picard: $('#pp-clear').checked });
        state.picard.sent = res; state.picard.saved = false; state.picard.fingerprinted = false;
        closeDialog(); renderPicardCard();
        toast(tagOnly ? `Tagged ${res.tagged} files.` : `Tagged ${res.tagged} files and loaded them in Picard.`, 'ok');
      } catch (err) { busy(btn, false); toast(err.message, 'error'); }
    };
    $('#pp-tag').addEventListener('click', run(true));
    $('#pp-send').addEventListener('click', run(false));
  } catch (e) { closeDialog(); toast(e.message, 'error'); }
}

async function picardFingerprint() {
  const btn = $('#picard-fingerprint');
  busy(btn, true, 'Sending…');
  try {
    await api('POST', '/api/picard/fingerprint');
    state.picard.fingerprinted = true;
    toast('Told Picard to generate fingerprints. Watch its window for progress.', 'ok');
  } catch (e) { toast(e.message, 'error'); }
  renderPicardCard();
}

async function picardSave() {
  const btn = $('#picard-save');
  busy(btn, true, 'Sending…');
  try {
    await api('POST', '/api/picard/save');
    state.picard.saved = true;
    toast('Told Picard to save. Watch its window for progress.', 'ok');
  } catch (e) { toast(e.message, 'error'); }
  renderPicardCard();
}

async function picardClear() {
  try { await api('POST', '/api/picard/clear'); toast('Cleared saved files from Picard.', 'ok'); } catch (e) { toast(e.message, 'error'); }
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

// ---------------------------------------------------------------- navigation
window.addEventListener('popstate', () => { state.browse = null; go('browse'); });
document.addEventListener('click', (e) => {
  const brand = e.target.closest('a.brand');
  if (!brand || !state.config) return;
  e.preventDefault();
  loadBrowse('').then(() => go('browse'));
});

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
  loadEnforcerStatus();
  try { state.favs = (await api('GET', '/api/favourites')).favourites; } catch { /* favourites are optional */ }
  go('browse');
})();
