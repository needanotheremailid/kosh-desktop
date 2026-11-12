'use strict';
// Synthetic DOM only: executes the real module without a server, browser or library.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../ui/research_workflows.js'), 'utf8');

// D1: the sidebar shell has no old More menu, and a script may load before a host exists.
const absent = {window:{}, document:{querySelector:()=>null}};
vm.createContext(absent);
assert.doesNotThrow(() => vm.runInContext(source, absent), 'Research must load without any mount point or More menu');
assert.equal(typeof absent.window.KoshResearch, 'object', 'Find can always access window.KoshResearch after script load');
assert.equal(typeof absent.window.KoshResearch.showSearchRecordButton, 'function');
assert.doesNotMatch(source, /\.more-menu/, 'The retired menu cannot remain a dependency');

console.log('Synthesise script load checks passed');

// A small DOM model for selectors, delegated events and detaching/reattaching a page.
// It makes no claim about browser layout or accessibility rendering.
const decode = text => text.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&');
class Element {
  constructor(tag = 'div', attrs = {}) {
    this.tag = tag; this.attrs = attrs; this.children = []; this.parentNode = null; this.listeners = {};
    this.dataset = {}; this.id = attrs.id || ''; this.value = attrs.value || '';
    this.checked = 'checked' in attrs; this.disabled = 'disabled' in attrs;
    for (const [name, value] of Object.entries(attrs)) if (name.startsWith('data-')) this.dataset[name.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = value;
  }
  get isConnected() { return this.root || !!this.parentNode?.isConnected; }
  append(child) { if (child.parentNode) child.parentNode.children.splice(child.parentNode.children.indexOf(child), 1); this.children.push(child); child.parentNode = this; }
  replaceChildren(...children) { for (const child of this.children) child.parentNode = null; this.children = []; for (const child of children) this.append(child); }
  set textContent(value) { this.replaceChildren(); this.text = String(value); }
  get textContent() { return (this.text || '') + this.children.map(child => child.textContent).join(''); }
  set innerHTML(markup) {
    this.replaceChildren(); this.text = '';
    const stack = [this];
    for (const token of markup.match(/<[^>]+>|[^<]+/g) || []) {
      const close = token.match(/^<\/([^>]+)>/);
      if (close) { if (stack.length > 1) stack.pop(); continue; }
      const open = token.match(/^<([\w-]+)([\s\S]*?)>$/);
      if (!open) { const text = new Element('#text'); text.text = decode(token); stack.at(-1).append(text); continue; }
      const attrs = {};
      for (const attr of open[2].matchAll(/([\w-]+)(?:="([^"]*)")?/g)) attrs[attr[1]] = decode(attr[2] || '');
      const child = new Element(open[1], attrs); stack.at(-1).append(child);
      if (!['input','br','hr','img','meta'].includes(child.tag)) stack.push(child);
    }
    for (const node of this.querySelectorAll('textarea,select')) node.value = node.tag === 'textarea' ? node.textContent : (node.querySelector('option[selected]') || node.querySelector('option'))?.attrs.value || '';
  }
  get innerHTML() { return this.children.map(child => child.outerHTML).join(''); }
  get outerHTML() { return this.tag === '#text' ? this.text : '<' + this.tag + Object.entries(this.attrs).map(([key, value]) => ' ' + key + '="' + value + '"').join('') + '>' + (this.text || '') + this.innerHTML + '</' + this.tag + '>'; }
  matches(selector) {
    const checked = selector.endsWith(':checked'); selector = selector.replace(/:checked$/, '');
    if (checked && !this.checked) return false;
    if (selector.startsWith('#')) return this.id === selector.slice(1);
    if (selector.startsWith('.')) return (this.attrs.class || '').split(' ').includes(selector.slice(1));
    const attr = selector.match(/^(\w+)?\[([\w-]+)(?:="([^"]*)")?\]$/);
    if (attr) return (!attr[1] || this.tag === attr[1]) && attr[2] in this.attrs && (attr[3] === undefined || this.attrs[attr[2]] === attr[3]);
    return this.tag === selector;
  }
  querySelectorAll(selectors) { const result = []; for (const child of this.children) { if (selectors.split(',').some(selector => child.matches(selector))) result.push(child); result.push(...child.querySelectorAll(selectors)); } return result; }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  closest(selector) { return this.matches(selector) ? this : this.parentNode?.closest(selector) || null; }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  insertAdjacentHTML(position, markup) { const fragment = new Element(); fragment.innerHTML = markup; for (const child of [...fragment.children]) this.parentNode.append(child); }
  showModal() { this.open = true; }
  click() { this.clicked = true; }
  remove() { this.parentNode.children.splice(this.parentNode.children.indexOf(this), 1); this.parentNode = null; }
}
const tick = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => {resolve = yes; reject = no;}); return {promise, resolve, reject}; };
const plain = value => JSON.parse(JSON.stringify(value));
function fixture() {
  const body = new Element('body'); body.root = true;
  const main = new Element('main', {id:'main-view'}), assist = new Element('dialog', {id:'assist-dialog'}); body.append(main); body.append(assist);
  const calls = [], kept = [], downloads = [], overrides = new Map(), views = new Map();
  const context = {
    window:{KoshViews:{register:view => views.set(view.id, view)}},
    document:{body, createElement:tag => new Element(tag), querySelector:selector => body.querySelector(selector)},
    state:{workspace:'one',view:'synthesise',intent:1,doc:{id:'a'},stopped:false},
    discovery:{busy:false,result:null}, assistState:{busy:false},
    escapeHTML:value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char])),
    headline:(title, purpose) => '<div class="page-heading"><h1>' + title + '</h1><p>' + purpose + '</p></div>',
    request:async (route, data) => {
      calls.push({route, data:plain(data || null)});
      if (overrides.has(route)) return overrides.get(route)(data);
      if (route.startsWith('/research/overview?')) return {workspace_id:context.state.workspace,title:'Lantern research',notice:'Saved records only.',sources:[
        {id:'a',name:'<img src=x onerror="bad()">',units:3,text_units:2,evidence_rows:1,linked_notes:[{id:'n',title:'<script>bad()</script>',version:2}]},
        {id:'b',name:'Catalogue source',metadata_only:true,evidence_rows:0,linked_notes:[]},
        {id:'archived',name:'Hidden archived source',archived:true,linked_notes:[]}
      ]};
      if (route === '/notes') return {id:'new',...data};
      return {workspace_id:context.state.workspace,title:'Prepared record',markdown:'Exact [[source:a:1]]\n</textarea><script>bad()</script>',notice:'Review coverage.'};
    },
    flushEdits:async () => true, replaceNote:note => kept.push(note), notify(){}, renderAssist(){context.assistRenders = (context.assistRenders || 0) + 1;},
    openDocument:async id => {context.openedSource = id;}, selectNote:async id => {context.openedNote = id;},
    URL:{createObjectURL:blob => {downloads.push(blob); return 'blob:synthetic';},revokeObjectURL(){}}, Blob, setTimeout(){}
  };
  context.KoshViews = context.window.KoshViews; context.window = context;
  vm.createContext(context); vm.runInContext(source, context);
  const api = context.window.KoshResearch;
  const render = () => views.get('synthesise').render(main);
  const host = () => main.querySelector('#research-content');
  const click = async selector => { const target = host().querySelector(selector); assert.ok(target, selector + ' exists'); for (const listener of host().listeners.click) listener({target}); await tick(); };
  const navigateBack = () => {context.state.view = 'library'; context.state.intent++; main.replaceChildren(); context.state.view = 'synthesise'; context.state.intent++; render();};
  return {context, main, body, assist, calls, kept, downloads, overrides, views, api, render, host, click, navigateBack};
}

(async () => {
  const f = fixture();
  assert.equal(f.views.get('synthesise').title, 'Synthesise', 'The module registers its actual renderer');
  assert.doesNotThrow(() => f.api.render(null), 'A missing main host does not break the public API');
  f.render(); await tick();
  assert.match(f.main.innerHTML, /<h1>Synthesise<\/h1>/);
  for (const id of ['sources','packet','comparison','question','checklists','preview']) assert.ok(f.main.querySelector('#research-' + id + '-title'), 'Labelled page section: ' + id);
  assert.equal(f.host().querySelectorAll('[data-research-source]').length, 2, 'Only active sources are offered');
  assert.equal(f.host().querySelectorAll('[data-research-recipe]').length, 7, 'All seven checklists remain available');
  assert.equal(f.host().querySelector('#research-budget').value, '24000');
  assert.equal(f.main.querySelector('script'), null, 'Imported draft titles stay text');
  assert.equal(f.main.querySelector('img'), null, 'Imported source names stay text');
  assert.equal(f.calls.length, 1); assert.match(f.calls[0].route, /^\/research\/overview\?workspace_id=one$/);
  assert.equal(f.calls[0].data, null, 'Opening Synthesise only reads saved records');
  assert.match(f.host().querySelector('#research-output').textContent, /Nothing prepared yet/, 'Y2: preview is empty-stated before preparation');
  assert.equal(f.host().querySelector('#research-source-filter'), null, 'Y1: a short source list needs no filter');
  assert.equal(f.host().querySelector('#research-selection-count').textContent, 'Selected: 1 of 10');
  assert.doesNotMatch(f.host().textContent, /No saved draft links/, 'Y1: omit empty backlink lines');
  await f.click('[data-research-build="packet"]');
  assert.deepEqual(f.calls.at(-1), {route:'/research/packet',data:{workspace_id:'one',document_ids:['a'],max_chars:24000}});
  const preview = f.host().querySelector('#research-preview');
  assert.match(preview.value, /Exact \[\[source:a:1\]\]/); assert.equal(f.main.querySelector('script'), null, 'Preview markup cannot execute');
  f.host().querySelector('#research-question').value = 'Keep this typed question';
  f.navigateBack();
  assert.equal(f.host().querySelector('#research-preview'), preview, 'Navigation retains the unsaved preview');
  assert.equal(f.host().querySelector('#research-question').value, 'Keep this typed question');
  await f.click('[data-research-open="a"]'); assert.equal(f.context.openedSource, 'a');
  await f.click('[data-research-note="n"]'); assert.equal(f.context.openedNote, 'n');

  // A slow save must flush first, and remains protected after leaving and returning.
  const flush = deferred(), save = deferred(); f.context.flushEdits = () => flush.promise;
  f.overrides.set('/notes', () => save.promise);
  await f.click('#research-save'); await f.click('#research-save');
  assert.equal(f.calls.filter(call => call.route === '/notes').length, 0, 'Pending edits finish before a draft is saved');
  flush.resolve(true); await tick();
  assert.equal(f.calls.filter(call => call.route === '/notes').length, 1);
  f.navigateBack(); await f.click('#research-save');
  assert.equal(f.calls.filter(call => call.route === '/notes').length, 1, 'Returning during a save cannot submit it twice');
  save.resolve({id:'saved',workspace_id:'one'}); await tick(); await f.click('#research-save');
  assert.equal(f.calls.filter(call => call.route === '/notes').length, 1, 'A saved preview cannot be saved twice');
  assert.equal(f.kept.length, 1); assert.equal(f.host().querySelector('#research-save').disabled, true);
  f.context.flushEdits = async () => true;

  for (const key of Object.keys(f.api.recipes)) {
    await f.click('[data-research-recipe="' + key + '"]');
    assert.ok(!('readonly' in f.host().querySelector('#research-preview').attrs), 'Checklist is editable: ' + key);
  }
  const editable = f.host().querySelector('#research-preview'); editable.value = '# My reviewed plan\n- [x] Read original';
  f.host().listeners.input[0]({target:editable});
  await f.click('#research-download'); assert.equal(await f.downloads[0].text(), editable.value, 'Download keeps the edited checklist exactly');
  f.overrides.delete('/notes'); await f.click('#research-save'); assert.equal(f.calls.at(-1).data.body, editable.value);

  const beforeQuestion = f.calls.length; await f.click('#research-ask');
  assert.equal(f.calls.length, beforeQuestion, 'Question handoff makes no provider or preview request itself');
  assert.equal(f.assist.open, true); assert.equal(f.context.assistRenders, 1);
  assert.deepEqual(plain(f.context.assistState.input), {workspace_id:'one',task:'ask',question:'Keep this typed question',document_ids:['a']});

  // Neither workspace switches nor a newer request can accept an older result.
  const old = deferred(); f.overrides.set('/research/packet', () => old.promise);
  await f.click('[data-research-build="packet"]');
  f.context.state.workspace = 'two'; f.context.state.intent++; f.render(); await tick();
  old.resolve({workspace_id:'one',title:'STALE WORKSPACE',markdown:'Do not show'}); await tick();
  assert.doesNotMatch(f.main.innerHTML, /STALE WORKSPACE|Do not show/);
  assert.equal(f.host().querySelector('#research-preview'), null, 'A workspace switch clears the old preview');
  const late = deferred(); f.overrides.set('/research/packet', () => late.promise);
  await f.click('[data-research-build="packet"]'); f.navigateBack();
  await f.click('[data-research-build="comparison"]');
  late.resolve({workspace_id:'two',title:'STALE REQUEST',markdown:'Late packet'}); await tick();
  assert.doesNotMatch(f.main.innerHTML, /STALE REQUEST|Late packet/);
  assert.equal(f.host().querySelector('#research-preview').value.startsWith('Exact '), true, 'The newer comparison wins');
  assert.deepEqual(f.calls.findLast(call => call.route === '/research/comparison').data, {workspace_id:'two',document_ids:['a']});

  // Find keeps its explicit search-record write, including in-flight deduplication.
  const form = new Element('form', {id:'discovery-form'}); f.body.append(form);
  f.context.discovery.result = {search_record:{workspace_id:'two',title:'Bounded search',body:'Query and index totals'}};
  f.api.showSearchRecordButton(); assert.ok(f.body.querySelector('#save-search-record'));
  const pending = deferred(); f.overrides.set('/notes', () => pending.promise);
  const first = f.api.saveSearchRecord(), second = f.api.saveSearchRecord(); await tick();
  const searchCalls = f.calls.filter(call => call.route === '/notes' && call.data.title === 'Bounded search');
  assert.equal(searchCalls.length, 1);
  pending.resolve({id:'search-note',workspace_id:'two'}); await Promise.all([first, second]); await f.api.saveSearchRecord();
  assert.equal(f.body.querySelector('#save-search-record').dataset.saved, 'true');
  assert.equal(f.calls.filter(call => call.route === '/notes' && call.data.title === 'Bounded search').length, 1);

  // A source-bound tool always needs 1–10 selected sources, and busy blocks another run.
  const guarded = fixture(); guarded.render(); await tick();
  const boxes = guarded.host().querySelectorAll('[data-research-source]'); boxes[0].checked = false;
  await guarded.click('[data-research-build="packet"]');
  assert.match(guarded.main.querySelector('#research-status').textContent, /one to ten sources/);
  assert.equal(guarded.calls.length, 1, 'No selection means no preparation request');
  const realQuery = guarded.host().querySelectorAll.bind(guarded.host());
  guarded.host().querySelectorAll = selector => selector === '[data-research-source]:checked' ? Array.from({length:11}, (_, index) => ({value:'source-' + index})) : realQuery(selector);
  await guarded.click('[data-research-build="comparison"]'); assert.equal(guarded.calls.length, 1, 'Eleven sources are refused');
  guarded.host().querySelectorAll = realQuery; boxes[0].checked = true;
  const blockedBuild = deferred(); guarded.overrides.set('/research/packet', () => blockedBuild.promise);
  await guarded.click('[data-research-build="packet"]'); await guarded.click('[data-research-build="comparison"]');
  assert.equal(guarded.calls.filter(call => call.route === '/research/comparison').length, 0, 'Busy preparation blocks another tool');
  blockedBuild.resolve({workspace_id:'one',title:'Packet',markdown:'Review me'}); await tick();
  guarded.context.flushEdits = async () => false;
  await guarded.click('#research-save'); assert.equal(guarded.calls.filter(call => call.route === '/notes').length, 0, 'An unsuccessful edit flush blocks saving');
  const blockedFlush = deferred(); guarded.context.flushEdits = () => blockedFlush.promise;
  await guarded.click('#research-save'); guarded.context.state.workspace = 'two'; guarded.context.state.intent++;
  blockedFlush.resolve(true); await tick();
  assert.equal(guarded.calls.filter(call => call.route === '/notes').length, 0, 'A workspace change during the flush cannot save into either workspace');

  const question = fixture(); question.render(); await tick();
  question.host().querySelector('#research-question').value = 'A bounded question';
  const questionFlush = deferred(); question.context.flushEdits = () => questionFlush.promise;
  await question.click('#research-ask'); question.context.state.workspace = 'two'; question.context.state.intent++;
  questionFlush.resolve(true); await tick();
  assert.equal(question.assist.open, undefined, 'A workspace change during the flush cancels the question handoff');
  assert.equal(question.context.assistState.input, undefined);

  const loading = fixture(), oldOverview = deferred();
  loading.overrides.set('/research/overview?workspace_id=one', () => oldOverview.promise);
  loading.render(); loading.context.state.workspace = 'two'; loading.context.state.intent++; loading.render(); await tick();
  oldOverview.resolve({workspace_id:'one',title:'OLD OVERVIEW',sources:[]}); await tick();
  assert.doesNotMatch(loading.main.innerHTML, /OLD OVERVIEW/);
  assert.equal(loading.host().querySelectorAll('[data-research-source]').length, 2, 'An old overview cannot replace the new workspace picker');

  const refreshing = fixture(); refreshing.render(); await tick();
  await refreshing.click('[data-research-recipe="reading"]');
  refreshing.host().querySelector('#research-question').value = 'Keep my question';
  const editedPlan = refreshing.host().querySelector('#research-preview'); editedPlan.value = 'My unsaved plan';
  refreshing.host().listeners.input[0]({target:editedPlan});
  refreshing.overrides.set('/research/overview?workspace_id=one', async () => ({title:'Refreshed sources',notice:'Saved state',sources:[
    {id:'a',name:'Original source',text_units:1,units:1,evidence_rows:1,linked_notes:[]},
    {id:'new',name:'Newly imported source',text_units:1,units:1,evidence_rows:0,linked_notes:[]}
  ]}));
  refreshing.navigateBack(); await tick();
  assert.match(refreshing.main.innerHTML, /Newly imported source/, 'Returning refreshes sources and backlinks from saved records');
  assert.equal(refreshing.host().querySelector('#research-preview').value, 'My unsaved plan', 'Refreshing sources keeps the edited preview');
  assert.equal(refreshing.host().querySelector('#research-question').value, 'Keep my question');
  assert.deepEqual(refreshing.host().querySelectorAll('[data-research-source]:checked').map(box => box.value), ['a'], 'Existing selections are kept and new sources require explicit selection');

  const stopped = fixture(), rejectedOverview = deferred();
  stopped.overrides.set('/research/overview?workspace_id=one', () => rejectedOverview.promise);
  stopped.render(); stopped.context.state.stopped = true;
  const stoppedMarkup = stopped.main.innerHTML, stoppedStatus = stopped.main.querySelector('#research-status').textContent;
  rejectedOverview.reject(new Error('Late error after Quit')); await tick();
  assert.equal(stopped.main.innerHTML, stoppedMarkup, 'A late error cannot write the page after Quit');
  assert.equal(stopped.main.querySelector('#research-status').textContent, stoppedStatus);

  // Y1: filtering is local and keeps selected, hidden sources in the tool payload.
  const picker = fixture();
  const manySources=Array.from({length:13}, (_,index)=>({id:index===0?'a':'source-'+index,name:index===0?'Selected lantern':'Lantern '+index,text_units:1,units:1,evidence_rows:0,linked_notes:[]}));
  picker.overrides.set('/research/overview?workspace_id=one',async()=>({workspace_id:'one',title:'Many lanterns',notice:'Saved records only.',sources:manySources}));
  picker.render();await tick();
  const titleFilter=picker.host().querySelector('#research-source-filter');assert.ok(titleFilter,'Y1: more than twelve sources offer a title filter');
  titleFilter.value='  LANTERN 12  ';picker.host().listeners.input[0]({target:titleFilter});
  assert.equal(picker.host().querySelectorAll('[data-research-source-row]').filter(row=>!row.hidden).length,1,'Title filter trims whitespace and ignores case');
  const extra=picker.host().querySelector('[value="source-12"]');extra.checked=true;
  picker.host().listeners.change[0]({target:extra});
  assert.equal(picker.host().querySelector('#research-selection-count').textContent,'Selected: 2 of 10','Count includes a hidden selection');
  assert.equal(picker.calls.length,1,'Filtering and selecting make no requests');
  await picker.click('[data-research-build="comparison"]');
  assert.deepEqual(picker.calls.at(-1).data,{workspace_id:'one',document_ids:['a','source-12']},'Filtering does not silently remove chosen sources');
  picker.navigateBack();await tick();
  assert.equal(picker.host().querySelector('#research-source-filter').value,'  LANTERN 12  ','Refresh retains the filter');
  assert.equal(picker.host().querySelector('#research-selection-count').textContent,'Selected: 2 of 10','Refresh retains both selections');
  const noMatch=picker.host().querySelector('#research-source-filter');noMatch.value='No matching title';picker.host().listeners.input[0]({target:noMatch});
  assert.equal(picker.host().querySelector('#research-filter-empty').hidden,false,'An unmatched filter explains the empty list');
  noMatch.value='';picker.host().listeners.input[0]({target:noMatch});
  assert.equal(picker.host().querySelectorAll('[data-research-source-row]').filter(row=>!row.hidden).length,13,'Clearing the filter restores the list');
  assert.equal(picker.host().querySelector('#research-filter-empty').hidden,true);

  // Route all entry points through the shell, so its standard single-item highlight applies.
  const app = fs.readFileSync(path.join(__dirname, '../ui/app.js'), 'utf8').replace(/\r\n/g, '\n');
  const overview = fs.readFileSync(path.join(__dirname, '../ui/overview.js'), 'utf8');
  assert.doesNotMatch(app, /synthesisDialogIntent|KoshResearch\.open\(/, 'The temporary dialog bridge is gone');
  assert.match(app, /label:'Research workflows'[^\n]+view:'synthesise'/, 'Ctrl K retains the old command name and opens the page');
  assert.match(overview, /row\('synthesise', 'Synthesise'/, 'Overview uses the registered page id');
  const route = app.match(/if\(name==='research-workflows'\)\{([^\n]+?)return;\}/);
  assert.ok(route, 'Legacy workflow actions have an explicit page route');
  const routed = []; const routing = {setView:async id => routed.push(id)}; vm.createContext(routing);
  await vm.runInContext('(async () => {' + route[1] + '})()', routing);
  assert.deepEqual(routed, ['synthesise']);
  console.log('Synthesise page, guards and search record checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
