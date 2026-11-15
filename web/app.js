"use strict";
/* Armory UI. All gear rules live on the server (loadout.py); this file only presents state and sends operations. */
const TOKEN = document.querySelector('meta[name=armory-token]').content;
const $ = (s, el = document) => el.querySelector(s);
const h = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === 'class') e.className = v; else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (v === true) e.setAttribute(k, ''); else if (v !== false && v != null) e.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k != null && k !== false) e.append(k.nodeType ? k : document.createTextNode(k));
  return e;
};
async function api(path, body) {
  const r = await fetch(path, body === undefined ? { headers: { 'X-Armory-Token': TOKEN } }
    : { method: 'POST', headers: { 'X-Armory-Token': TOKEN, 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const d = await r.json();
  if (d.error && !body) throw new Error(d.error);
  return d;
}

/* ---------- readable names (best effort; the internal name is always in the tooltip) ---------- */
const NAMES = {
  k98: 'Karabiner 98k', g41: 'Gewehr 41', g43: 'Gewehr 43', g43_scope: 'Gewehr 43 (scoped)', mp40_folded: 'MP 40 (stock folded)',
  mp40_unfolded: 'MP 40 (stock open)', mg34_belt: 'MG 34 (belt)', mg34_drum: 'MG 34 (drum)', mg42: 'MG 42', stg44: 'StG 44',
  fg42: 'FG 42', luger: 'Luger P08', p38: 'Walther P38', m24: 'Stick grenade (M24)', m24_splinter: 'Stick grenade, splinter sleeve',
  m24_smoke: 'Smoke grenade', m24_geballteladung: 'Bundled charge (Geballte Ladung)', bandage_ger: 'Bandage',
  shovel_ger: 'Entrenching tool', binocular: 'Binoculars', panzerfaust_60: 'Panzerfaust 60', panzerfaust_100: 'Panzerfaust 100',
};
const AMMO = { 'rifle_ger.clip': 'Rifle clips', 'rifle_ger.gewehr': 'Rifle magazines', mp40: 'MP 40 magazines', pistol: 'Pistol magazines',
  'mgun_ger.belt': 'MG belts', 'mgun_ger.drum': 'MG drums', stg44: 'StG 44 magazines' };
/* Army tags on item and skin names ("ger_stalhelm", "bandage_usa", "sov_41_rkka"): stripped for display, whatever the army. */
const ARMY_PRE = /^(ger|usa?|sov|rus|uk|eng|fin|can|pol|swe|fra|civ)_/, ARMY_SUF = /_(ger|usa?|sov|rus|uk|eng|fin|can|pol)$/;
/* The game's own English name for an item (read from its localization when Armory built the catalog), or null. */
const gameName = name => { const m = (S.save && S.save.item_names) || {}; return m[name] || m[name + '.weapon'] || null; };
function pretty(name) {
  if (NAMES[name]) return NAMES[name];
  const gn = gameName(name); if (gn) return gn;
  let s = name.replace(ARMY_PRE, '').replace(ARMY_SUF, '');
  s = s.replace(/stalhelm/, 'steel helmet').replace(/fieldcap/, 'field cap').replace(/sidecap/, 'side cap')
    .replace(/overseascap/, 'overseas cap').replace(/_/g, ' ');
  s = s.replace(/\b((?:m|mg|mp|stg|fg|k|g|pz|pzb)\d+[a-z]?)\b/gi, m => m.toUpperCase()).replace(/\bvar ?(\d)\b/g, '(v$1)');
  return s.charAt(0).toUpperCase() + s.slice(1);
}
const ammoLabel = stem => AMMO[stem] || gameName(stem) || pretty(stem.replace(/\./g, ' ')) + ' ammo';
const stemOf = e => e.tokens.slice(0, -1).join('.');
const ROLE_LABEL = { primary: 'Primary weapon', sidearm: 'Sidearm', skin: 'Uniform skin', launcher: 'Launcher', backup: 'Backup weapon', head: 'Headgear', grenade: 'Grenades', medical: 'Medical', tool: 'Tools', ammo: 'Ammunition' };
const ROLE_COLOR = { primary: 'var(--c-primary)', sidearm: 'var(--c-sidearm)', backup: 'var(--c-primary)', head: 'var(--c-head)', grenade: 'var(--c-grenade)',
  medical: 'var(--c-medical)', tool: 'var(--c-tool)', ammo: 'var(--c-ammo)', other: 'var(--c-other)', launcher: 'var(--c-other)' };

/* ---------- state ---------- */
const S = { saves: [], save: null, cur: {}, orig: {}, look: {}, look0: {}, skinList: null, sel: null, undo: [], redo: [], picker: null, selTile: null, gameRunning: false,
  collapsed: new Set(), config: null };
/* which squads are folded is a per-save convenience; storage can be blocked, so never depend on it */
const collKey = () => 'armory-collapsed:' + (S.save ? S.save.dir + '|' + S.save.file : '');
function saveCollapsed() { try { localStorage.setItem(collKey(), JSON.stringify([...S.collapsed])); } catch (e) { /* ignore */ } }
function loadCollapsed() { try { S.collapsed = new Set(JSON.parse(localStorage.getItem(collKey()) || '[]')); } catch (e) { S.collapsed = new Set(); } }

/* Editor sections (Rank, Weapons & gear, Pack, ...) can be hidden. The choice is remembered across saves and soldiers. */
const HID_KEY = 'armory-hidden-sections';
const HIDDEN = new Set((() => { try { return JSON.parse(localStorage.getItem(HID_KEY) || '[]'); } catch (e) { return []; } })());
function toggleSection(id) {
  if (HIDDEN.has(id)) HIDDEN.delete(id); else HIDDEN.add(id);
  try { localStorage.setItem(HID_KEY, JSON.stringify([...HIDDEN])); } catch (e) { /* ignore */ }
  renderEditor();
}
/* A titled section whose body can be hidden. `summary` stays visible while hidden so you still see the state at a glance. */
function fold(id, title, summary, body, cls = '') {
  const hidden = HIDDEN.has(id);
  return h('section', { class: `fold ${cls}${hidden ? ' is-hidden' : ''}` },
    h('header', { class: 'fold-head' },
      h('h2', {}, title),
      hidden && summary ? h('span', { class: 'muted fold-sum' }, summary) : null,
      h('button', { class: 'btn small ghost fold-btn', 'aria-expanded': String(!hidden), 'aria-label': `${hidden ? 'Show' : 'Hide'} ${title}`, onclick: () => toggleSection(id) }, hidden ? 'Show' : 'Hide')),
    hidden ? null : body);
}
const keyOf = lo => JSON.stringify(lo.entries.map(e => [e.tokens, e.mid, e.x, e.y, e.user]));
const invChanged = eid => keyOf(S.cur[eid]) !== keyOf(S.orig[eid]);
const perksChanged = eid => JSON.stringify(S.look[eid].perks || null) !== JSON.stringify(S.look0[eid].perks || null);
const lookChanged = eid => !!S.look[eid] && (S.look[eid].skin !== S.look0[eid].skin || S.look[eid].vet !== S.look0[eid].vet || perksChanged(eid) || S.look[eid].icon !== S.look0[eid].icon || S.look[eid].tag !== S.look0[eid].tag || S.look[eid].portrait !== S.look0[eid].portrait);
const nameChanged = eid => !!S.names[eid] && JSON.stringify(S.names[eid]) !== JSON.stringify(S.names0[eid]);
const changed = eid => invChanged(eid) || lookChanged(eid) || nameChanged(eid);
const changedEids = () => Object.keys(S.cur).filter(changed);
const soldier = eid => S.save.soldiers.find(s => s.eid === eid);
const plural = r => /man$/.test(r) ? r.replace(/man$/, 'men') : r + 's';
const label = s => `${s.role} ${S.save.soldiers.filter(x => x.role === s.role).length > 1 ? s.n : ''}`.trim();

function toast(msg, err = false) {
  const t = h('div', { class: 'toast' + (err ? ' err' : '') }, msg);
  $('#toasts').append(t); setTimeout(() => t.remove(), err ? 7000 : 4500);
}
function setNotice(msg, err = false) {
  const n = $('#notice'); n.textContent = msg || ''; n.classList.toggle('hidden', !msg); n.classList.toggle('err', err);
}

/* ---------- undo / redo (whole-map snapshots; loadouts are tiny) ---------- */
const snap = () => JSON.stringify({ cur: S.cur, look: S.look, names: S.names });
const restore = s => { const o = JSON.parse(s); S.cur = o.cur; S.look = o.look; S.names = o.names || S.names; };
function commit(newMap) {
  S.undo.push(snap()); S.redo = []; Object.assign(S.cur, newMap); renderAll();
}
function commitLook(newMap) {                       // newMap: {eid: {skin, vet}}
  S.undo.push(snap()); S.redo = []; for (const [e, v] of Object.entries(newMap)) S.look[e] = { ...S.look[e], ...v }; renderAll();
}
function undo() { if (!S.undo.length) return; S.redo.push(snap()); restore(S.undo.pop()); renderAll(); }
function redo() { if (!S.redo.length) return; S.undo.push(snap()); restore(S.redo.pop()); renderAll(); }

/* ---------- operations ---------- */
function targetsFor(scope) {
  const s = soldier(S.sel);
  if (scope === 'squad' && s.squad != null) return S.save.soldiers.filter(x => x.squad === s.squad).map(x => x.eid);
  if (scope === 'role') return S.save.soldiers.filter(x => x.role === s.role).map(x => x.eid);
  return [s.eid];
}
async function applyOp(op, scope = 'one') {
  const targets = targetsFor(scope), out = {}, skipped = [];
  let msgs = [], before = null;
  for (const eid of targets) {
    const r = await api('/api/op', { loadout: S.cur[eid], op });
    if (r.error) { skipped.push(`${label(soldier(eid))}: ${r.error}`); continue; }
    out[eid] = r.loadout; if (eid === S.sel) { before = S.cur[eid]; msgs = describeChanges(eid, before, r.loadout); }
  }
  if (!Object.keys(out).length) { toast(skipped[0] || 'Nothing changed', true); return false; }
  commit(out);
  const n = Object.keys(out).length;
  toast(n === 1 ? (msgs.join(' · ') || 'Done') : `Applied to ${n} soldiers${skipped.length ? `, skipped ${skipped.length} (${skipped[0]})` : ''}`);
  return true;
}

/* ---------- soldier list ---------- */
function renderSoldiers() {
  const box = $('#soldier-list'); box.replaceChildren();
  if (!S.save) { box.append(h('p', { class: 'muted pad' }, 'Open a save to see your soldiers.')); return; }
  const q = $('#soldier-search').value.trim().toLowerCase();
  const groups = new Map();
  for (const s of S.save.soldiers) (groups.get(s.squad) || groups.set(s.squad, []).get(s.squad)).push(s);
  for (const [sq, list] of groups) {
    const info = S.save.squads.find(x => x.index === sq);
    const cards = list.filter(s => !q || (label(s) + ' ' + summary(s)).toLowerCase().includes(q));
    if (!cards.length) continue;
    const key = String(sq), open = !!q || !S.collapsed.has(key), nChanged = cards.filter(s => changed(s.eid)).length;
    box.append(h('button', { class: 'squad', 'aria-expanded': open, title: open ? 'Collapse this squad' : 'Expand this squad',
      onclick: () => { if (S.collapsed.has(key)) S.collapsed.delete(key); else S.collapsed.add(key); saveCollapsed(); renderSoldiers(); } },
      h('span', { class: 'chev', 'aria-hidden': true }, open ? '▾' : '▸'),
      h('span', { class: 'sq-text' }, h('span', { class: 'sq-title' }, info ? `${info.label} · ${plural(info.main_role)}` : 'Unassigned'),
        info && info.game_name ? h('span', { class: 'sq-sub' }, info.game_name) : null),
      nChanged ? h('span', { class: 'dot', title: `${nChanged} changed` }) : null, h('span', { class: 'sq-count' }, cards.length)));
    if (!open) continue;
    for (const s of cards) box.append(h('button', { class: 'card', 'aria-current': s.eid === S.sel, onclick: () => select(s.eid) },
      h('b', {}, label(s), changed(s.eid) ? h('span', { class: 'dot', title: 'Has unsaved changes' }) : null),
      h('small', {}, summary(s))));
  }
}
function summary(s) {
  const lo = S.cur[s.eid], w = lo.entries.find(e => e.role === 'primary'), hd = lo.entries.find(e => e.user === 'head');
  return [w && pretty(w.tokens[0]), hd && pretty(hd.tokens[0])].filter(Boolean).join(' · ') || 'No gear';
}
function select(eid) { S.sel = eid; S.picker = null; S.selTile = null; renderAll(); }

/* ---------- editor ---------- */
function groupBy(entries, role) {
  const m = new Map();
  for (const e of entries.filter(e => e.role === role)) { const k = e.key; (m.get(k) || m.set(k, []).get(k)).push(e); }
  return [...m];
}
// The gun in his hands, a backup gun carried in the pack, the launcher: found the same way the server does it.
function slotEntry(lo, role) {
  const filled = es => es.filter(e => e.mid.includes('filled'));
  if (role === 'launcher' || role === 'sidearm') return filled(lo.entries.filter(e => e.role === role))[0];
  const guns = filled(lo.entries.filter(e => e.role === 'primary')).sort((a, b) => (a.user !== 'hand_right') - (b.user !== 'hand_right'));
  if (role === 'primary') return guns[0];
  if (role === 'backup') return guns[1];
  return lo.entries.find(e => e.role === role && (role !== 'head' || e.user === 'head'));
}
function slotChanged(role) {
  if (['primary', 'backup', 'launcher'].includes(role)) {
    const k = lo => { const e = slotEntry(lo, role); return e ? e.tokens.join(' ') : ''; };
    return k(S.orig[S.sel]) !== k(S.cur[S.sel]);
  }
  const a = S.orig[S.sel].entries.filter(e => e.role === role).map(e => e.tokens.join(' ')).sort().join('|');
  const b = S.cur[S.sel].entries.filter(e => e.role === role).map(e => e.tokens.join(' ')).sort().join('|');
  return a !== b;
}
function slotCard(role, body, extra) {
  return h('div', { class: 'slot' + (slotChanged(role) ? ' changed' : ''), style: `--c:${ROLE_COLOR[role]}` },
    h('header', {}, h('span', {}, ROLE_LABEL[role]), extra), body);
}
function single(role, verb) {
  const lo = S.cur[S.sel];
  const e = slotEntry(lo, role);
  const body = h('button', { class: 'pick', onclick: () => openPicker(role, 'equip'), 'aria-label': `${verb} ${ROLE_LABEL[role]}` },
    h('strong', { title: e ? e.tokens[0] : '' }, e ? pretty(e.tokens[0]) : 'Nothing'),
    h('span', {}, e ? `${e.size[0]}×${e.size[1]} cells` : 'Click to choose one'), h('em', {}, e ? 'Change…' : 'Add…'));
  const rm = e ? h('button', { class: 'btn small ghost', title: 'Remove', onclick: () => applyOp({ kind: 'remove', id: e.id }) }, 'Remove') : null;
  return slotCard(role, body, rm);
}
function counted(role, addLabel) {
  const lo = S.cur[S.sel], rows = groupBy(lo.entries, role);
  const list = h('div', { class: 'rows' }, rows.length ? rows.map(([name, es]) => h('div', { class: 'row' },
    h('span', { title: name }, pretty(es[0].tokens[0])),
    h('span', { class: 'qty' }, h('button', { class: 'btn small', 'aria-label': `Remove one ${pretty(es[0].tokens[0])}`, onclick: () => applyOp({ kind: 'remove_name', name }) }, '−'),
      h('b', {}, es.length), h('button', { class: 'btn small', 'aria-label': `Add one ${pretty(es[0].tokens[0])}`, onclick: () => applyOp({ kind: 'add', name }) }, '+')))
  ) : h('span', { class: 'muted' }, 'None'));
  return slotCard(role, h('div', { class: 'rows' }, list, h('button', { class: 'btn small', onclick: () => openPicker(role, 'add') }, addLabel)));
}
function ammoCard() {
  const lo = S.cur[S.sel], m = new Map();
  for (const e of lo.entries.filter(e => e.role === 'ammo')) { const k = stemOf(e); (m.get(k) || m.set(k, []).get(k)).push(e); }
  const rows = [...m].map(([stem, es]) => {
    const rounds = es.reduce((a, e) => a + (parseInt(e.mid[0]) || 0), 0);
    return h('div', { class: 'row' }, h('span', { title: stem }, `${ammoLabel(stem)} `, h('small', { class: 'muted' }, `${rounds} rounds`)),
      h('span', { class: 'qty' }, h('button', { class: 'btn small', 'aria-label': `Fewer ${ammoLabel(stem)}`, onclick: () => applyOp({ kind: 'ammo', stem, n: Math.max(0, es.length - 1) }) }, '−'),
        h('b', {}, es.length), h('button', { class: 'btn small', 'aria-label': `More ${ammoLabel(stem)}`, onclick: () => applyOp({ kind: 'ammo', stem, n: es.length + 1 }) }, '+')));
  });
  return slotCard('ammo', h('div', { class: 'rows' }, rows.length ? rows : h('span', { class: 'muted' }, 'No ammunition'),
    h('button', { class: 'btn small', onclick: () => openPicker('ammo', 'add') }, 'Add ammo…'),
    h('small', { class: 'muted' }, 'Swapping a weapon swaps its ammo. Use “Add ammo” for anything else, like spare drums for an assistant.')));
}
function appearanceCard() {
  const lk = S.look[S.sel];
  return h('div', { class: 'slot' + (lk.skin !== S.look0[S.sel].skin ? ' changed' : ''), style: '--c:var(--c-head)' },
    h('header', {}, h('span', {}, 'Uniform')),
    h('button', { class: 'pick', onclick: () => openPicker('skin', 'equip'), 'aria-label': 'Change uniform' },
      h('strong', { title: lk.skin }, prettySkin(lk.skin)), h('span', {}, 'Uniform skin'), h('em', {}, 'Change…')));
}
/* Rank is a soldier-wide trait, not an item: its own full-width section under the item slots. */
function rankSection() {
  const s = soldier(S.sel), lk = S.look[S.sel], max = S.save.vet_max ?? 8, was = S.look0[S.sel].vet;
  const spread = scope => { const t = targetsFor(scope), m = {}; for (const e of t) m[e] = { vet: lk.vet }; commitLook(m); toast(`Rank ${rankLabel(lk.vet)} applied to ${t.length} soldiers`); };
  return fold('rank', 'Rank', rankLabel(lk.vet), h('div', {},
    h('small', { class: 'muted' }, 'Veterancy level: affects reload speed, stamina and toughness. Separate from his gear and uniform.'),
    h('div', { class: 'seg rank-seg', role: 'group', 'aria-label': 'Rank' },
      Array.from({ length: max + 1 }, (_, n) => h('button', { 'aria-pressed': String(n === lk.vet), title: `Level ${n}`, onclick: () => commitLook({ [S.sel]: { vet: n } }) },
        (n === lk.vet ? '✓ ' : '') + n))),
    h('p', { class: 'rank-now' }, `${rankLabel(lk.vet)}${lk.vet !== was ? ` (was ${rankLabel(was)})` : ''}`),
    h('div', { class: 'actions', style: 'justify-content:flex-start;gap:6px;margin-top:8px' },
      s.squad != null ? h('button', { class: 'btn small', onclick: () => spread('squad') }, 'Same rank for squad') : null,
      h('button', { class: 'btn small', onclick: () => spread('role') }, `Same rank for all ${plural(s.role)}`))),
    'rank-section' + (lk.vet !== was ? ' changed' : ''));
}
/* One short bullet per thing a control changes, shown right under the control. Falsy notes are skipped. */
function perkNotes(notes) {
  const ns = notes.flat().filter(Boolean);
  return ns.length ? h('ul', { class: 'perk-notes' }, ns.map(n => h('li', {}, n))) : null;
}
const NEEDS_GEAR = { sniper_vision: 'needs a scoped rifle', medic: 'needs a medic bag' };

/* ---------- Identity: name (save) + icon and tag (breed) ---------- */
const ICON_LABEL = { rifle: 'Rifleman', autorifle: 'Automatic rifle', smg: 'SMG', tech: 'Crew / technical', mg: 'Machine gun', bazooka: 'Rocket launcher', sniper: 'Sniper',
  pistol: 'Pistol', signaller: 'Signaller', stg: 'Assault rifle', atrifle: 'AT rifle', flamer: 'Flamethrower', riflegrenade: 'Rifle grenade', shotgun: 'Shotgun',
  officer: 'Officer', at: 'Anti-tank', tankmans_39: 'Tankman' };
const TAG_LABEL = { soldier: 'Soldier', crew: 'Crew', soldier_pzfaust: 'Panzerfaust AT', soldier_pzscheck: 'Panzerschreck AT', soldier_atr: 'AT rifle',
  soldier_atr_grenade: 'AT rifle grenade', soldier_bazooka: 'Bazooka / PIAT AT' };
const nationOf = s => (s.breed.startsWith('mp/') ? s.breed.split('/')[1] : '');
/* Which army's gear to offer: the selected soldier's own nation, else the save's army. The server decides what that means
   (a known army narrows the lists, an unknown one gets everything). */
const armyOf = () => ({ army: S.save.army || '', nation: S.sel ? nationOf(soldier(S.sel)) : '' });
const prettyPortrait = p => (p || 'none').replace(/^[a-z]{2,4}_/, '').replace(/_/g, ' ').replace(/^./, c => c.toUpperCase()) + (p ? `  (${p})` : '');
function nameLists(eid) { return (S.save.name_lists || {})[nationOf(soldier(eid))]; }
function nameOf(eid, pair) {
  const l = nameLists(eid); if (!l || !pair) return 'unknown';
  return `${l.first[pair[0]] ?? '?'} ${l.last[pair[1]] ?? '?'}`.trim();
}
function identitySection() {
  const s = soldier(S.sel), lk = S.look[S.sel], lk0 = S.look0[S.sel], ident = S.save.identity || {}, nat = (ident.by_nation || {})[nationOf(s)] || ident;
  const lists = nameLists(S.sel), pair = S.names[S.sel], changedName = nameChanged(S.sel);
  const iconChanged = lk.icon !== lk0.icon, tagChanged = lk.tag !== lk0.tag, portraitChanged = lk.portrait !== lk0.portrait;
  const weapons = S.cur[S.sel].entries.filter(e => e.mid.includes('filled')).map(e => (e.key || '').replace(/\.weapon$/, ''));
  const tagFor = nat.tag_for_weapon || {};                         // this nation's weapon -> tag table, read from its own breeds
  const expected = weapons.map(w => tagFor[w]).find(Boolean) || 'soldier';
  const seg = (label, buttons, ...notes) => h('div', { class: 'perk-item' }, h('div', { class: 'perk-row' }, h('span', { class: 'perk-label' }, label), h('div', { class: 'seg', role: 'group', 'aria-label': label }, buttons)), perkNotes(notes));
  const btn = (on, text, fn, title) => h('button', { 'aria-pressed': String(on), title: title || '', onclick: fn }, (on ? '✓ ' : '') + text);

  let nameRow;
  if (!lists || !pair) nameRow = h('p', { class: 'muted' }, 'Names for this soldier\'s nation can\'t be read, so he can\'t be renamed here.');
  else {
    const dl = (id, arr) => h('datalist', { id }, arr.map(n => h('option', { value: n })));
    const field = (which, idx, arr, id, ph) => h('input', { class: 'name-in', list: id, placeholder: ph, value: arr[idx] ?? '', 'aria-label': ph,
      onchange: ev => {
        const v = ev.target.value.trim(), i = arr.findIndex(n => n.toLowerCase() === v.toLowerCase());
        if (i < 0) { toast(`"${v}" isn't in the game's ${which} list. Pick one from the suggestions.`, true); ev.target.value = arr[idx] ?? ''; return; }
        const p = [...pair]; p[which === 'first' ? 0 : 1] = i; S.undo.push(snap()); S.redo = []; S.names[S.sel] = p; renderAll();
      } });
    const rnd = () => { const r = n => Math.floor(Math.random() * n); S.undo.push(snap()); S.redo = []; S.names[S.sel] = [r(lists.first.length), r(lists.last.length)]; renderAll(); };
    nameRow = h('div', { class: 'perk-row' }, h('span', { class: 'perk-label' }, 'Name'),
      field('first', pair[0], lists.first, 'dl-first', 'First name'), field('last', pair[1], lists.last, 'dl-last', 'Surname'), dl('dl-first', lists.first), dl('dl-last', lists.last),
      h('button', { class: 'btn small', title: 'Pick a random name from the game\'s list', onclick: rnd }, 'Random'),
      changedName ? h('button', { class: 'btn small ghost', onclick: () => { S.undo.push(snap()); S.redo = []; S.names[S.sel] = [...S.names0[S.sel]]; renderAll(); } }, 'Reset name') : null);
  }
  const body = h('div', {},
    h('div', { class: 'perk-item' }, nameRow, perkNotes(["Pick from the game's own name list: type to search, or press Random."])),
    (nat.icons || []).length ? seg('Icon', nat.icons.map(i => btn(i === lk.icon, ICON_LABEL[i] || i, () => commitLook({ [S.sel]: { icon: i } }), `Unit-card icon: ${i}`)),
      'The symbol on his unit card. It does not change what he can do.') : null,
    (nat.tags || []).length ? seg('Tag', nat.tags.map(t => btn(t === lk.tag, TAG_LABEL[t] || t, () => commitLook({ [S.sel]: { tag: t } }), t)),
      'The label the game uses for his role. Anti-tank carriers have their own tag.') : null,
    (nat.portraits || []).length ? h('div', { class: 'perk-item' },
      h('div', { class: 'perk-row' }, h('span', { class: 'perk-label' }, 'Portrait'),
        h('select', { class: 'portrait-sel', 'aria-label': 'Portrait', onchange: ev => commitLook({ [S.sel]: { portrait: ev.target.value } }) },
          [...new Set([lk.portrait, ...nat.portraits].filter(Boolean))].map(p => h('option', { value: p, selected: p === lk.portrait }, prettyPortrait(p))))),
      perkNotes(['The face picture the game shows for him: the unit card and his dialogue. Pick the branch he belongs to. It is only a picture, it does not change what he can do.'])) : null,
    lk.tag && lk.tag !== 'crew' && lk.tag !== expected
      ? h('p', { class: 'perk-now' }, `The game normally tags a soldier with his kit as “${TAG_LABEL[expected] || expected}”. `,
        h('button', { class: 'btn small', onclick: () => commitLook({ [S.sel]: { tag: expected } }) }, 'Use that tag')) : null);
  const sum = [pair ? nameOf(S.sel, pair) : '', ICON_LABEL[lk.icon] || lk.icon, TAG_LABEL[lk.tag] || lk.tag, lk.portrait ? prettyPortrait(lk.portrait).replace(/\s+\(.*\)$/, '') : ''].filter(Boolean).join(' · ');
  return fold('identity', 'Identity', sum, body, 'identity-section' + (changedName || iconChanged || tagChanged || portraitChanged ? ' changed' : ''));
}

/* ---------- Skills: which weapon he is trained with, how tough he is, and his specialties (breed {perks}, see perks.py) ---------- */
const FAMILY = { '': 'Untrained', rifle: 'Rifle', smg: 'SMG', mg: 'Machine gun', loader: 'Loader', loader_smg: 'Loader (SMG)' };
const STYLE = { standard: 'Standard', recon: 'Scout', defense: 'Defender' };
const STYLE_HINT = { standard: 'balanced', recon: 'fast, more stamina, less health', defense: 'slow, heals quickly' };
const EXTRA = {
  stealth: ['Stealth', 'Harder to spot, a little faster'], medic: ['Medic', 'Can heal, more stamina, can place a medic flag'],
  marksman: ['Marksman', 'Top rifle skill (level 8)'], sniper_vision: ['Sniper optics', 'Rifle scope and aimed shots, long-range vision'],
  binocular_vision: ['Binoculars', 'Field glasses and far sight'], skilled_repair: ['Repairs', 'Can repair vehicles at full speed'],
  engineer: ['Engineer', 'Builds fortifications, barricades and heavy MG nests'],
};
const WEAPON_LABEL = { rifle: 'Rifle', smg: 'SMG', mgun: 'Machine gun', mgun_light: 'Light MG', pistol: 'Pistol', melee: 'Melee', avoidance: 'Dodging' };
const skillParts = (pr, name) => (pr.skills || []).find(s => s.name === name);
const skillLabel = (pr, name) => { const s = skillParts(pr, name); return !name ? 'Not set' : !s ? name : s.family ? `${FAMILY[s.family]} ${s.level}` : 'Untrained'; };
const tierParts = (pr, name) => (pr.tiers || []).find(t => t.name === name);
const tierLabel = (pr, name) => { const t = tierParts(pr, name); return !name ? 'Not set' : !t ? name : `Tier ${t.tier} · ${STYLE[t.style]}`; };
const pct = v => v == null ? '?' : Math.round(v * 100) + '%';
function perksSummary(pr, p) {
  if (!p) return '';
  const bits = [skillLabel(pr, p.skill), tierLabel(pr, p.tier)];
  if (p.at) bits.push(`Anti-tank ${p.at}`);
  for (const e of p.extras || []) bits.push((EXTRA[e] || [e])[0]);
  return bits.join(' · ');
}
function skillsSection() {
  const pr = S.save.perk_presets || {}, s = soldier(S.sel), lk = S.look[S.sel], cur = lk.perks, was = S.look0[S.sel].perks;
  const changed = perksChanged(S.sel);
  if (!cur || !(pr.skills || []).length)
    return fold('skills', 'Skills', '', h('p', { class: 'muted' }, 'This soldier\'s skills can\'t be read yet. Restart Armory (it reads new soldier types when it starts), then reopen the save.'), 'skills-section');
  const set = patch => commitLook({ [S.sel]: { perks: { ...cur, ...patch } } });
  const spread = scope => { const t = targetsFor(scope), m = {}; for (const e of t) m[e] = { perks: JSON.parse(JSON.stringify(cur)) }; commitLook(m); toast(`Skills applied to ${t.length} soldiers`); };
  const cs = skillParts(pr, cur.skill), fam = cs ? cs.family : null, lvl = cs ? cs.level : 2;
  const families = [...new Set(pr.skills.map(x => x.family))];
  const pickSkill = (f, l) => { const hit = pr.skills.find(x => x.family === f && x.level === (f ? l : 0)) || pr.skills.find(x => x.family === f); if (hit) set({ skill: hit.name }); };
  const ct = tierParts(pr, cur.tier), tiers = [...new Set(pr.tiers.map(x => x.tier))].sort(), styles = ['standard', 'recon', 'defense'];
  const pickTier = (t, st) => { const hit = pr.tiers.find(x => x.tier === t && x.style === st); if (hit) set({ tier: hit.name }); };
  const seg = (label, buttons, ...notes) => h('div', { class: 'perk-item' }, h('div', { class: 'perk-row' }, h('span', { class: 'perk-label' }, label), h('div', { class: 'seg', role: 'group', 'aria-label': label }, buttons)), perkNotes(notes));
  const btn = (on, text, fn, title, dis) => h('button', { 'aria-pressed': String(on), title: title || '', disabled: !!dis, onclick: fn }, (on ? '✓ ' : '') + text);
  const body = h('div', {},
    h('small', { class: 'muted' }, 'Skills come from his soldier type. Rank adds on top of them.'),
    seg('Trained with', families.map(f => btn(f === fam, FAMILY[f] || f, () => pickSkill(f, lvl), f ? `${FAMILY[f]}, keeps the current level` : 'No weapon training')),
      'The weapon he is best with. It gets +1 skill level over his other weapons.'),
    seg('Skill level', [1, 2, 3, 4, 5].map(l => btn(!!fam && l === lvl, String(l), () => pickSkill(fam, l), `Level ${l} of 5`, !fam)),
      'How good he is with every weapon. Higher = more accurate shots and steadier aim.',
      cs && cs.levels && Object.keys(cs.levels).length ? 'He shoots at: ' + Object.entries(cs.levels).filter(([k]) => WEAPON_LABEL[k])
        .sort((a, b) => b[1] - a[1]).map(([k, v]) => `${WEAPON_LABEL[k]} ${v}`).join(' · ') : null),
    seg('Toughness', tiers.map(t => btn(!!ct && t === ct.tier, String(t), () => pickTier(t, ct ? ct.style : 'standard'), `Tier ${t}`)),
      'How much health, stamina and healing he has. A higher tier gives more of all three.'),
    seg('Build', styles.map(st => btn(!!ct && st === ct.style, STYLE[st], () => pickTier(ct ? ct.tier : 2, st), STYLE_HINT[st])),
      'Standard: balanced.', 'Scout: runs faster and longer, but has less health.', 'Defender: walks slower, but heals much faster.',
      ct ? `Now: health ${pct(ct.health)} (about ${Math.round(ct.health * 200)} on the in-game bar) · stamina ${pct(ct.stamina)} · speed ${ct.speed ?? '?'}× · healing ${pct(ct.regen)}` : null),
    seg('Anti-tank', Array.from({ length: (pr.at_max || 6) + 1 }, (_, n) => btn(n === cur.at, n ? String(n) : 'None', () => set({ at: n }), n ? `Rocket and AT-rifle skill ${n}` : 'No extra anti-tank training')),
      'Skill with rocket launchers and anti-tank rifles. None = only what his training gives him.'),
    seg('Specialties', (pr.extras || []).map(x => btn((cur.extras || []).includes(x), (EXTRA[x] || [x])[0], () => set({ extras: (cur.extras || []).includes(x) ? cur.extras.filter(y => y !== x) : [...(cur.extras || []), x] }), (EXTRA[x] || ['', ''])[1])),
      'Extra roles. Click to switch each on or off:',
      (pr.extras || []).map(x => h('span', { class: (cur.extras || []).includes(x) ? 'on' : '' }, h('b', {}, (EXTRA[x] || [x])[0]), ': ', (EXTRA[x] || ['', ''])[1].replace(/^./, c => c.toLowerCase()),
        NEEDS_GEAR[x] ? ` (${NEEDS_GEAR[x]})` : ''))),
    h('div', { class: 'actions', style: 'justify-content:flex-start;gap:6px;margin-top:8px' },
      s.squad != null ? h('button', { class: 'btn small', onclick: () => spread('squad') }, 'Same skills for squad') : null,
      h('button', { class: 'btn small', onclick: () => spread('role') }, `Same skills for all ${plural(s.role)}`),
      changed ? h('button', { class: 'btn small ghost', onclick: () => commitLook({ [S.sel]: { perks: JSON.parse(JSON.stringify(was)) } }) }, 'Reset skills') : null));
  return fold('skills', 'Skills', perksSummary(pr, cur), body, 'skills-section' + (changed ? ' changed' : ''));
}

function renderEditor() {
  const view = $('#soldier-view');
  $('#welcome').classList.toggle('hidden', !!S.save);
  view.classList.toggle('hidden', !S.save || !S.sel);
  if (S.save && !S.sel) { $('#welcome').classList.remove('hidden'); $('#welcome h1').textContent = `${S.save.name}: pick a soldier`; }
  if (!S.save || !S.sel) return;
  const s = soldier(S.sel), lo = S.cur[S.sel], sq = S.save.squads.find(x => x.index === s.squad);
  view.replaceChildren(
    h('div', { class: 'sv-head' },
      h('div', {}, h('h1', {}, label(s)), h('p', { class: 'muted' }, sq ? `${sq.label} · ${sq.count} soldiers` : '')),
      h('div', { class: 'sv-actions' },
        h('button', { class: 'btn', disabled: !changed(S.sel), onclick: () => { commit({ [S.sel]: JSON.parse(JSON.stringify(S.orig[S.sel])) }); toast('Soldier reset to the saved loadout'); } }, 'Reset this soldier'),
        h('button', { class: 'btn', onclick: copyDialog }, 'Copy loadout to…'))),
    identitySection(), rankSection(), skillsSection(),
    fold('gear', 'Weapons & gear', '', h('div', { class: 'slots' }, single('primary', 'Change'), ammoCard(), single('backup', 'Change'), single('launcher', 'Change'), single('sidearm', 'Change'), single('head', 'Change'), appearanceCard(),
      counted('grenade', 'Add grenade…'), counted('medical', 'Add medical…'), counted('tool', 'Add tool…')), 'gear-section'),
    packView(lo), changesView());
}

/* ---------- pack grid (drag to rearrange; optional) ---------- */
function packView(lo) {
  const [W, H] = S.save.grid, cell = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--cell')) || 42;
  const used = lo.entries.reduce((a, e) => a + e.size[0] * e.size[1], 0);
  const grid = h('div', { class: 'grid', style: `height:${cell * H}px` });
  const ghost = h('div', { class: 'dropghost hidden' }); grid.append(ghost);
  const fits = (e, x, y) => x >= 0 && y >= 0 && x + e.size[0] <= W && y + e.size[1] <= H &&
    !lo.entries.some(o => o.id !== e.id && x < o.x + o.size[0] && o.x < x + e.size[0] && y < o.y + o.size[1] && o.y < y + e.size[1]);
  const orig = new Set(S.orig[S.sel].entries.map(e => e.tokens.join(' ') + e.x + ',' + e.y));
  let drag = null;
  for (const e of lo.entries) {
    const t = h('div', { class: 'tile' + (S.selTile === e.id ? ' sel' : '') + (orig.has(e.tokens.join(' ') + e.x + ',' + e.y) ? '' : ' new'),
      draggable: 'true', tabindex: 0, role: 'button', title: `${e.role === 'ammo' ? ammoLabel(stemOf(e)) : pretty(e.tokens[0])} (${e.size[0]}×${e.size[1]}) — drag to move`,
      style: `--c:${ROLE_COLOR[e.role]};left:${e.x * cell}px;top:${e.y * cell}px;width:${e.size[0] * cell - 2}px;height:${e.size[1] * cell - 2}px`,
      onclick: ev => { ev.stopPropagation(); S.selTile = e.id; renderEditor(); },
      onkeydown: ev => { if (ev.key === 'Delete' || ev.key === 'Backspace') { ev.preventDefault(); applyOp({ kind: 'remove', id: e.id }); } },
      ondragstart: ev => { const r = t.getBoundingClientRect(); drag = { e, ox: Math.floor((ev.clientX - r.left) / cell), oy: Math.floor((ev.clientY - r.top) / cell) }; ev.dataTransfer.effectAllowed = 'move'; ev.dataTransfer.setData('text/plain', 'x'); },
      ondragend: () => { ghost.classList.add('hidden'); drag = null; } },
      e.role === 'ammo' ? ammoLabel(stemOf(e)) : pretty(e.tokens[0]));
    grid.append(t);
  }
  grid.addEventListener('dragover', ev => {
    if (!drag) return; ev.preventDefault();
    const r = grid.getBoundingClientRect(), x = Math.floor((ev.clientX - r.left) / cell) - drag.ox, y = Math.floor((ev.clientY - r.top) / cell) - drag.oy;
    ghost.classList.remove('hidden'); ghost.classList.toggle('bad', !fits(drag.e, x, y));
    Object.assign(ghost.style, { left: x * cell + 'px', top: y * cell + 'px', width: drag.e.size[0] * cell - 2 + 'px', height: drag.e.size[1] * cell - 2 + 'px' });
  });
  grid.addEventListener('drop', ev => {
    if (!drag) return; ev.preventDefault();
    const r = grid.getBoundingClientRect(), x = Math.floor((ev.clientX - r.left) / cell) - drag.ox, y = Math.floor((ev.clientY - r.top) / cell) - drag.oy;
    const e = drag.e; drag = null; ghost.classList.add('hidden');
    if (!fits(e, x, y)) { toast('That spot is taken or outside the pack', true); return; }
    applyOp({ kind: 'move', id: e.id, x, y });
  });
  const sel = lo.entries.find(e => e.id === S.selTile);
  const legend = h('div', { class: 'legend' }, ['primary', 'sidearm', 'head', 'grenade', 'medical', 'tool', 'ammo'].map(r => h('span', { style: `--c:${ROLE_COLOR[r]}` }, h('i'), ROLE_LABEL[r])));
  return fold('pack', 'Pack', `${used} of ${W * H} cells used`, h('div', {},
    h('div', { class: 'pack-head' }, h('span', { class: 'muted' }, `${used} of ${W * H} cells used`),
      h('div', { class: 'meter', 'aria-hidden': true }, h('i', { style: `width:${Math.round(100 * used / (W * H))}%` })),
      h('button', { class: 'btn small', title: 'Re-arrange everything neatly: weapons, ammo, grenades, medical, tools', onclick: () => applyOp({ kind: 'sort' }) }, 'Auto-sort pack'),
      sel ? h('span', {}, h('b', {}, pretty(sel.tokens[0])), ' ', h('button', { class: 'btn small', onclick: () => applyOp({ kind: 'remove', id: sel.id }) }, 'Remove')) : h('span', { class: 'muted' }, 'Optional: drag items to rearrange')),
    grid, legend), 'pack');
}

/* ---------- plain-language change list ---------- */
function describeChanges(eid, from = S.orig[eid], to = S.cur[eid]) {
  const a = from.entries, b = to.entries, out = [];
  const one = (role, headOnly) => {
    const f = es => es.find(e => e.role === role && (!headOnly || e.user === 'head'));
    const x = f(a), y = f(b);
    if ((x && x.tokens[0]) !== (y && y.tokens[0])) out.push(`${ROLE_LABEL[role]}: ${x ? pretty(x.tokens[0]) : 'none'} → ${y ? pretty(y.tokens[0]) : 'none'}`);
  };
  one('primary'); one('sidearm'); one('head', true);
  for (const role of ['launcher', 'backup']) { const f = x => { const e = slotEntry(x, role); return e ? pretty(e.tokens[0]) : 'none'; }; if (f(from) !== f(to)) out.push(`${ROLE_LABEL[role]}: ${f(from)} → ${f(to)}`); }
  const count = (es, role) => { const m = new Map(); for (const e of es.filter(e => e.role === role)) { const k = role === 'ammo' ? ammoLabel(stemOf(e)) : pretty(e.tokens[0]); m.set(k, (m.get(k) || 0) + 1); } return m; };
  for (const role of ['ammo', 'grenade', 'medical', 'tool']) {
    const ca = count(a, role), cb = count(b, role);
    for (const k of new Set([...ca.keys(), ...cb.keys()])) if ((ca.get(k) || 0) !== (cb.get(k) || 0)) out.push(`${k}: ${ca.get(k) || 0} → ${cb.get(k) || 0}`);
  }
  if (!out.length && keyOf(from) !== keyOf(to)) out.push('Items rearranged in the pack');
  return out;
}
const prettySkin = n => { const s = (n || 'unknown').replace(ARMY_PRE, '').replace(/_/g, ' '); return s.charAt(0).toUpperCase() + s.slice(1); };
const RANK_NAMES = ['Recruit', 'Trained', 'Seasoned', 'Experienced', 'Hardened', 'Veteran', 'Elite', 'Master', 'Legend'];
const rankLabel = n => `Level ${n} · ${RANK_NAMES[n] || ''}`.replace(/ · $/, '');
function lookLines(eid) {
  const a = S.look0[eid], b = S.look[eid], out = [];
  if (!a || !b) return out;
  if (a.skin !== b.skin) out.push(`Uniform: ${prettySkin(a.skin)} → ${prettySkin(b.skin)}`);
  if (a.vet !== b.vet) out.push(`Rank: ${rankLabel(a.vet)} → ${rankLabel(b.vet)}`);
  if (a.icon !== b.icon) out.push(`Icon: ${ICON_LABEL[a.icon] || a.icon || 'none'} → ${ICON_LABEL[b.icon] || b.icon || 'none'}`);
  if (a.tag !== b.tag) out.push(`Tag: ${TAG_LABEL[a.tag] || a.tag || 'none'} → ${TAG_LABEL[b.tag] || b.tag || 'none'}`);
  if (a.portrait !== b.portrait) out.push(`Portrait: ${prettyPortrait(a.portrait)} → ${prettyPortrait(b.portrait)}`);
  if (nameChanged(eid)) out.push(`Name: ${nameOf(eid, S.names0[eid])} → ${nameOf(eid, S.names[eid])}`);
  if (perksChanged(eid)) { const pr = S.save.perk_presets || {}; out.push(`Skills: ${perksSummary(pr, a.perks)} → ${perksSummary(pr, b.perks)}`); }
  return out;
}
const allChanges = eid => describeChanges(eid).concat(lookLines(eid));
function changesView() {
  const ls = allChanges(S.sel);
  return fold('changes', 'What changed on this soldier', ls.length ? `${ls.length} change${ls.length === 1 ? '' : 's'}` : 'nothing yet',
    ls.length ? h('ul', {}, ls.map(l => h('li', {}, l))) : h('p', { class: 'muted' }, 'Nothing yet. Click a slot above to start.'), 'changes');
}

/* ---------- picker ---------- */
async function openPicker(role, mode) {
  S.picker = { role, mode, everything: false, query: '', scope: 'one', items: null };
  renderPicker(); await loadCandidates();
}
async function loadCandidates() {
  const p = S.picker; p.items = null; renderPicker();
  if (p.role === 'skin') {
    const r = await api('/api/skins', { everything: p.everything, mods: S.save.mods, ...armyOf() });
    const cur = S.look[S.sel].skin, curGroup = (r.skins.find(k => k.name === cur) || {}).group;
    p.items = r.skins.map(k => ({ name: k.name, display: prettySkin(k.name), group: k.group, mod: k.mod, fits: true, size: [0, 0], ammo: null }))
      .sort((a, b) => (b.group === curGroup) - (a.group === curGroup));      // the uniform family he already wears comes first
  } else if (p.role === 'ammo') {
    const r = await api('/api/ammo_candidates', { loadout: S.cur[S.sel], everything: p.everything, mods: S.save.mods, ...armyOf() });
    p.items = (r.items || []).map(i => ({ ...i, display: ammoLabel(i.name), match: i.carried, hint: i.carried ? 'Fits your ' + i.for_weapons.map(pretty).join(' and ') : '', ammo: null }));
  } else {
    const r = await api('/api/candidates', { loadout: S.cur[S.sel], role: p.role, everything: p.everything, mods: S.save.mods, ...armyOf() });
    p.items = r.items || [];
  }
  renderPicker();
}
function renderPicker() {
  const body = $('#picker-body'), p = S.picker;
  $('#picker-empty').classList.toggle('hidden', !!p); body.classList.toggle('hidden', !p);
  if (!p) return;
  const s = soldier(S.sel), sq = S.save.squads.find(x => x.index === s.squad);
  const nSq = sq ? targetsFor('squad').length : 0, nRole = targetsFor('role').length;
  // h() turns `true` into an empty attribute, so aria-pressed must be the string "true"/"false" for the CSS to match.
  const scopeBtn = (v, text) => h('button', { 'aria-pressed': String(p.scope === v), onclick: () => { p.scope = v; renderPicker(); } },
    p.scope === v ? '✓ ' + text : text);
  const cur = new Map(); for (const e of S.cur[S.sel].entries) cur.set(e.key, (cur.get(e.key) || 0) + 1);
  const q = p.query.toLowerCase();
  const items = (p.items || []).filter(i => !q || (pretty(i.display) + ' ' + i.display).toLowerCase().includes(q));
  const head = h('div', { class: 'picker-head' },
    h('div', { class: 'top' }, h('h2', {}, p.mode === 'equip' ? `Choose: ${ROLE_LABEL[p.role]}` : `Add: ${ROLE_LABEL[p.role]}`),
      h('button', { class: 'btn small', onclick: () => { S.picker = null; renderPicker(); } }, 'Close')),
    h('div', {}, h('div', { class: 'scope-note' }, 'Apply to'),
      h('div', { class: 'seg', role: 'group', 'aria-label': 'Apply to' }, scopeBtn('one', 'Just ' + label(s)), sq ? scopeBtn('squad', `Squad (${nSq})`) : null, scopeBtn('role', `All ${plural(s.role)} (${nRole})`)),
      h('div', { class: 'scope-note scope-now' }, 'Changes ' + (p.scope === 'one' ? label(s) + ' only' : p.scope === 'squad' ? `all ${nSq} soldiers in this squad` : `all ${nRole} ${plural(s.role)} in the save`))),
    h('input', { type: 'search', placeholder: 'Search…', value: p.query, 'aria-label': 'Search items', oninput: ev => { p.query = ev.target.value; renderPicker(); const i = $('#picker-body input'); i.focus(); i.setSelectionRange(99, 99); } }),
    h('label', { class: 'scope-note' }, h('input', { type: 'checkbox', checked: p.everything, onchange: ev => { p.everything = ev.target.checked; loadCandidates(); } }), ` Show items from every nation${S.save.army_known ? ` (not just ${S.save.army_info.label})` : ''}`));
  const skinRows = () => {
    const out = []; let g = null;
    for (const i of items) {
      if (i.group !== g) { g = i.group; out.push(h('h3', { class: 'group-head' }, prettySkin(g))); }
      const isCur = S.look[S.sel].skin === i.name;
      out.push(h('button', { class: 'item' + (isCur ? ' match' : ''), title: i.name, onclick: () => {
        const m = {}; for (const e of targetsFor(p.scope)) m[e] = { skin: i.name };
        commitLook(m); S.picker = null; renderPicker(); toast(`Uniform: ${i.display}` + (Object.keys(m).length > 1 ? ` (${Object.keys(m).length} soldiers)` : ''));
      } }, h('strong', {}, isCur ? '✓ ' : '', i.display, i.mod ? h('span', { class: 'badge mod' }, i.mod) : null),
        isCur ? h('span', { class: 'badge cur' }, 'Current') : h('span', {}), h('small', {}, i.name)));
    }
    return out;
  };
  const rows = p.items === null ? [h('p', { class: 'muted pad' }, 'Loading…')] : p.role === 'skin' ? (items.length ? skinRows() : [h('p', { class: 'muted pad' }, 'Nothing matches.')]) : items.length ? items.map(i => {
    const isAmmo = p.role === 'ammo';
    const qty = isAmmo ? (i.have || 0) : (cur.get(i.name) || 0), isCur = p.mode === 'equip' && qty > 0 && i.fits !== undefined && S.cur[S.sel].entries.some(e => e.key === i.name && (p.role !== 'head' || e.user === 'head'));
    return h('button', { class: 'item' + (i.match ? ' match' : ''), 'aria-disabled': !i.fits, title: i.display, onclick: async () => {
      if (!i.fits) { toast(i.why || 'Does not fit', true); return; }
      const ok = await applyOp(isAmmo ? { kind: 'add_ammo', stem: i.name } : p.mode === 'equip' ? { kind: 'equip', role: p.role, name: i.name } : { kind: 'add', name: i.name }, p.scope);
      if (ok && p.mode === 'equip') { S.picker = null; renderPicker(); } else if (ok) loadCandidates();
    } },
      h('strong', {}, i.match ? '✓ ' : '', pretty(i.display), i.match ? h('span', { class: 'badge fit' }, 'Fits this gun') : null, i.mod ? h('span', { class: 'badge mod', title: 'From a mod this save uses' }, i.mod) : null), isCur ? h('span', { class: 'badge cur' }, 'Equipped') : (qty && p.mode === 'add' ? h('span', { class: 'badge cur' }, `Carrying ${qty}`) : h('span', { class: 'badge' }, `${i.size[0]}×${i.size[1]}`)),
      h('small', {}, [i.ammo ? `Uses ${ammoLabel(i.ammo).toLowerCase()}` : null, isAmmo ? `${i.stack} rounds each` : null, i.hint || null, i.fits ? null : h('span', { class: 'why' }, i.why)].filter(Boolean).flatMap((x, k) => k ? [' · ', x] : [x])));
  }) : [h('p', { class: 'muted pad' }, 'Nothing matches. Try “Show items from every nation”.')];
  body.replaceChildren(head, h('div', { class: 'list' }, rows));
}

/* ---------- copy loadout ---------- */
function copyDialog() {
  const s = soldier(S.sel), d = $('#dlg'); d.replaceChildren(
    h('h2', {}, `Copy ${label(s)}'s loadout to…`),
    h('p', { class: 'muted' }, 'The other soldiers get exactly this gear. You can undo it.'),
    h('div', { class: 'actions', style: 'justify-content:flex-start;flex-wrap:wrap' },
      ...[['squad', `His squad (${targetsFor('squad').length - 1} others)`], ['role', `All ${plural(s.role)} (${targetsFor('role').length - 1} others)`]].map(([sc, t]) => h('button', { class: 'btn', onclick: () => {
        const out = {}; for (const eid of targetsFor(sc)) if (eid !== s.eid) out[eid] = { ...JSON.parse(JSON.stringify(S.cur[S.sel])), eid };
        d.close(); if (Object.keys(out).length) { commit(out); toast(`Copied to ${Object.keys(out).length} soldiers`); } } }, t))),
    h('div', { class: 'actions' }, h('button', { class: 'btn', onclick: () => d.close() }, 'Cancel')));
  d.showModal();
}

/* ---------- review & save ---------- */
async function reviewDialog() {
  const d = $('#dlg'), eids = changedEids();
  const st = await api('/api/state'); S.gameRunning = st.game_running; renderChip();
  const base = S.save.name.replace(/ \(Armory\)$/, '') + ' (Armory)';
  const input = h('input', { type: 'text', id: 'copy-name', value: base, 'aria-describedby': 'copy-help' });
  let mode = 'copy';                                          // 'copy' (safe default) or 'overwrite'
  const fixBox = h('input', { type: 'checkbox', id: 'fix-resupply', checked: true });
  const sure = h('input', { type: 'checkbox', id: 'sure' });
  const go = h('button', { class: 'btn primary' }, 'Save copy');
  const copyBox = h('div', { class: 'mode-body' }, h('label', { for: 'copy-name' }, 'Name of the new copy'), input,
    h('small', { id: 'copy-help', class: 'muted' }, `A new save is created next to your others. “${S.save.file}” is never modified, and the copy gets its own name so saving in game can't overwrite your original.`));
  const warnBox = h('div', { class: 'mode-body warn hidden' },
    h('p', {}, h('b', {}, '⚠ This replaces “' + S.save.file + '”.')),
    h('p', {}, 'Your changes go straight into the original campaign. Armory first keeps a backup in its own ', h('code', {}, 'backups'), ' folder, but the game will no longer have the unedited version in the list.'),
    h('label', { class: 'check' }, sure, ' I understand — replace the original'));
  const radio = (v, title, sub) => h('label', { class: 'mode' }, h('input', { type: 'radio', name: 'savemode', value: v, checked: v === mode, onchange: () => {
    mode = v; copyBox.classList.toggle('hidden', v !== 'copy'); warnBox.classList.toggle('hidden', v !== 'overwrite');
    go.textContent = v === 'copy' ? 'Save copy' : 'Overwrite original'; go.classList.toggle('danger', v === 'overwrite'); sync(); } }),
    h('span', {}, h('b', {}, title), h('small', {}, sub)));
  const sync = () => { go.disabled = S.gameRunning || (mode === 'overwrite' && !sure.checked); };
  sure.addEventListener('change', sync);
  go.addEventListener('click', async () => {
    go.disabled = true; const label0 = go.textContent; go.textContent = 'Saving…';
    const looks = {};
    const names = {};
    for (const e of eids.filter(nameChanged)) names[e] = S.names[e];
    for (const e of eids.filter(lookChanged)) {
      const v = {}; if (S.look[e].icon !== S.look0[e].icon) v.icon = S.look[e].icon; if (S.look[e].tag !== S.look0[e].tag) v.tag = S.look[e].tag; if (S.look[e].portrait !== S.look0[e].portrait) v.portrait = S.look[e].portrait; if (S.look[e].skin !== S.look0[e].skin) v.skin = S.look[e].skin; if (S.look[e].vet !== S.look0[e].vet) v.vet = S.look[e].vet; if (perksChanged(e)) v.perks = S.look[e].perks; looks[e] = v;
    }
    const r = await api('/api/save', { file: S.save.file, dir: S.save.dir, name: input.value.trim() || base, edits: eids.filter(invChanged).map(e => S.cur[e]), looks, names,
      overwrite: mode === 'overwrite', fix_resupply: fixBox.checked });
    if (r.error) { go.textContent = label0; sync(); toast(r.error, true); return; }
    d.replaceChildren(h('h2', {}, 'Saved ✓'), h('div', { class: 'ok-box' }, h('p', {}, h('b', {}, r.file)), h('p', { class: 'muted' }, r.path)),
      r.overwrote ? h('p', {}, 'The original was replaced. A backup of how it was is in ', h('code', {}, r.backup_dir), '.')
        : h('p', {}, 'In the game, open ', h('b', {}, 'Campaign → Load'), ' and pick this copy. Your original save was not touched.'),
      r.breeds ? h('p', { class: 'muted' }, `Armory added ${r.breeds} custom soldier type${r.breeds > 1 ? 's' : ''} (a small local mod called “armory_breeds”) so supply crates can refill these soldiers. `,
        h('b', {}, 'Restart the game'), ' if it was open — it only reads mods at startup.') : null,
      h('div', { class: 'actions' }, h('button', { class: 'btn primary', onclick: () => d.close() }, 'Done')));
    refreshSaves();
  });
  const groups = new Map();                                  // identical change lists collapse into one line
  for (const eid of eids) { const k = allChanges(eid).join('; '); (groups.get(k) || groups.set(k, []).get(k)).push(eid); }
  const names = es => { const ls = es.map(e => label(soldier(e))); return ls.length > 3 ? `${ls[0]} … ${ls[ls.length - 1]} (${ls.length} soldiers)` : ls.join(', '); };
  d.replaceChildren(...[h('h2', {}, `Review ${eids.length} changed soldier${eids.length > 1 ? 's' : ''}`),
    S.gameRunning ? h('p', { class: 'notice err', style: 'border-radius:8px' }, 'The game is running. Close it, or go back to the main menu, then reopen this window.') : null,
    h('ul', {}, [...groups].map(([txt, es]) => h('li', {}, h('b', {}, names(es)), ': ', txt))),
    h('div', { class: 'modes' }, radio('copy', 'Save as a new copy', 'Recommended. Your original stays exactly as it is.'),
      radio('overwrite', 'Overwrite the original', 'Replaces this save (a backup is kept).')),
    copyBox, warnBox,
    h('label', { class: 'check', title: 'Adds a tiny local mod so supply crates refill edited soldiers' }, fixBox, ' Keep edited soldiers resupplied by crates (recommended)'),
    h('div', { class: 'actions' }, h('button', { class: 'btn', onclick: () => d.close() }, 'Back'), go)].filter(Boolean));
  sync();
  d.showModal();
}

/* ---------- settings: where is the game? ---------- */
function settingsDialog(firstRun = false) {
  const d = $('#dlg'), c = S.config || {};
  const gameIn = h('input', { type: 'text', value: c.game_dir || '', placeholder: 'C:\\Program Files (x86)\\Steam\\steamapps\\common\\Call to Arms - Gates of Hell', 'aria-describedby': 'game-help' });
  const profIn = h('input', { type: 'text', value: c.profiles_dir || '', placeholder: 'C:\\Users\\you\\Documents\\My Games\\gates of hell\\profiles' });
  const status = (ok, auto) => h('small', { class: ok ? 'okc' : 'badc' }, ok ? (auto ? '✓ found automatically' : '✓ looks right') : '✗ not found — paste the folder path');
  const save = h('button', { class: 'btn primary', onclick: async () => {
    save.disabled = true; save.textContent = 'Reading game data…';
    const r = await api('/api/config', { game_dir: gameIn.value, profiles_dir: profIn.value });
    save.disabled = false; save.textContent = 'Save settings';
    if (r.error) { toast(r.error, true); return; }
    S.config = r.config; d.close(); toast('Settings saved'); await refreshSaves();
  } }, 'Save settings');
  d.replaceChildren(h('h2', {}, firstRun ? 'Where is Gates of Hell?' : 'Settings'),
    h('p', { class: 'muted' }, firstRun ? 'Armory couldn\'t find everything on its own. Paste the folders below (right-click a folder in Explorer → Copy as path). Leave a box empty to search automatically.' : 'Folders Armory reads from. Leave a box empty to search automatically.'),
    h('label', { for: 'g' }, 'Game folder (contains “resource” and “binaries”)'), Object.assign(gameIn, { id: 'g' }), status(c.game_ok, c.auto_game),
    h('label', { for: 'p' }, 'Save profiles folder (contains your profile folders)'), Object.assign(profIn, { id: 'p' }), status(c.profiles_ok, c.auto_profiles),
    c.workshop_dir ? h('small', { class: 'muted' }, 'Workshop mods: ' + c.workshop_dir) : null,
    h('div', { class: 'actions' }, h('button', { class: 'btn', onclick: () => d.close() }, firstRun ? 'Later' : 'Cancel'), save));
  d.showModal();
}

/* ---------- chrome ---------- */
function renderChip() {
  const c = $('#game-chip'); c.className = 'chip ' + (S.gameRunning ? 'bad' : 'ok');
  c.textContent = S.gameRunning ? 'Game is running — close it before saving' : 'Game closed — safe to save';
}
function renderBar() {
  const n = S.save ? changedEids().length : 0;
  $('#bar-status').textContent = n ? `${n} soldier${n > 1 ? 's' : ''} changed — nothing is saved until you review` : 'No changes yet';
  $('#review-btn').disabled = !n; $('#undo-btn').disabled = !S.undo.length; $('#redo-btn').disabled = !S.redo.length;
}
function renderAll() { renderSoldiers(); renderEditor(); renderPicker(); renderBar(); }
function renderSaves() {
  const sel = $('#save-select'), keep = sel.value; sel.replaceChildren(h('option', { value: '' }, S.saves.length ? 'Choose a campaign save…' : 'No saves found'));
  for (const s of S.saves) sel.append(h('option', { value: s.dir + '|' + s.file },
    `${s.name} — ${s.file} · ${s.army || '?'} · ${new Date(s.mtime * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}${s.mods ? ` · ${s.mods} mods` : ''}`));
  if (keep && [...sel.options].some(o => o.value === keep)) sel.value = keep;
  $('#open-btn').disabled = !sel.value;
}
async function refreshSaves() {
  const r = await api('/api/state'); S.saves = r.saves; S.gameRunning = r.game_running; S.config = r.config; renderSaves(); renderChip();
  if (!r.config.ok && !$('#dlg').open) settingsDialog(true);
}
async function openSave() {
  const [dir, file] = $('#save-select').value.split('|');
  try {
    const d = await api(`/api/open?dir=${encodeURIComponent(dir)}&file=${encodeURIComponent(file)}`);
    S.save = d; loadCollapsed(); S.cur = {}; S.orig = {}; S.look = {}; S.look0 = {}; S.names = {}; S.names0 = {}; S.skinList = null; S.undo = []; S.redo = []; S.picker = null; S.sel = null;
    for (const s of d.soldiers) {
      S.cur[s.eid] = JSON.parse(JSON.stringify(s.loadout)); S.orig[s.eid] = JSON.parse(JSON.stringify(s.loadout));
      const lk = { skin: s.skin, vet: s.vet, perks: s.perks || null, icon: s.icon || null, tag: s.tag || null, portrait: s.portrait || null };
      S.look[s.eid] = { ...lk, perks: lk.perks && JSON.parse(JSON.stringify(lk.perks)) }; S.look0[s.eid] = lk;
      if (s.name_id) { S.names[s.eid] = [...s.name_id]; S.names0[s.eid] = [...s.name_id]; }
    }
    $('#soldier-search').disabled = false; S.gameRunning = d.game_running; renderChip();
    setNotice(d.army_known ? '' : `This is a ${d.army ? `"${d.army}" ` : ''}campaign Armory doesn't know. Its item and uniform lists aren't narrowed to one army, so you'll see everything the game has (and names, icons and tags are read from each soldier's own type).`);
    if (d.soldiers.length) select(d.soldiers.find(s => s.role !== 'Supply crate')?.eid || d.soldiers[0].eid); else renderAll();
    if (!d.soldiers.length) setNotice('This save has no soldiers with inventories yet (buy some units first).', true);
  } catch (e) { setNotice('Could not open that save: ' + e.message, true); }
}

window.addEventListener('keydown', ev => {
  const typing = /input|textarea|select/i.test(ev.target.tagName);
  if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'z' && !typing) { ev.preventDefault(); ev.shiftKey ? redo() : undo(); }
  else if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'y' && !typing) { ev.preventDefault(); redo(); }
  else if (ev.key === 'Escape' && S.picker && !$('#dlg').open) { S.picker = null; renderPicker(); }
});
$('#save-select').addEventListener('change', e => { $('#open-btn').disabled = !e.target.value; });
$('#open-btn').addEventListener('click', openSave);
$('#undo-btn').addEventListener('click', undo); $('#redo-btn').addEventListener('click', redo);
$('#review-btn').addEventListener('click', reviewDialog);
$('#settings-btn').addEventListener('click', () => settingsDialog(false));
$('#soldier-search').addEventListener('input', renderSoldiers);
refreshSaves().catch(e => setNotice('Could not talk to the Armory server: ' + e.message, true));
renderAll();
