'use strict';
// Executes the real module with invented sources and a small DOM, without a browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../ui/screening.js'), 'utf8');
const plain = value => JSON.parse(JSON.stringify(value));
const escape = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const decode = value => value.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&');
let focused = null;
class Element {
  constructor(tag = 'div', attrs = {}) {
    this.tagName = tag.toUpperCase(); this.tag = tag; this.attrs = attrs; this.children = []; this.parentNode = null; this.listeners = {};
    this.dataset = {}; this.id = attrs.id || ''; this.value = attrs.value || ''; this.disabled = 'disabled' in attrs; this.open = 'open' in attrs;
    for (const [name, value] of Object.entries(attrs)) if (name.startsWith('data-')) this.dataset[name.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = value;
  }
  get isConnected() { return this.root || !!this.parentNode?.isConnected; }
  append(child) { this.children.push(child); child.parentNode = this; }
  replaceChildren(...children) { for (const child of this.children) child.parentNode = null; this.children = []; for (const child of children) this.append(child); }
  set textContent(value) { this.replaceChildren(); this.text = String(value); }
  get textContent() { return (this.text || '') + this.children.map(child => child.textContent).join(''); }
  set innerHTML(markup) {
    this.markup = markup; this.replaceChildren(); this.text = '';
    const stack = [this];
    for (const token of markup.match(/<[^>]+>|[^<]+/g) || []) {
      if (/^<\//.test(token)) { if (stack.length > 1) stack.pop(); continue; }
      const open = token.match(/^<([\w-]+)([\s\S]*?)>$/);
      if (!open) { const child = new Element('#text'); child.text = decode(token); stack.at(-1).append(child); continue; }
      const attrs = {};
      for (const attr of open[2].matchAll(/([\w-]+)(?:="([^"]*)")?/g)) attrs[attr[1]] = decode(attr[2] || '');
      const child = new Element(open[1], attrs); stack.at(-1).append(child);
      if (!['input','br','hr','img'].includes(child.tag)) stack.push(child);
    }
    for (const node of this.querySelectorAll('textarea,select')) node.value = node.tag === 'textarea' ? node.textContent : (node.querySelector('option[selected]') || node.querySelector('option'))?.attrs.value || '';
  }
  get innerHTML() { return this.children.map(child => child.outerHTML).join(''); }
  get outerHTML() { return this.tag === '#text' ? escape(this.text || '') : '<' + this.tag + Object.entries(this.attrs).map(([key, value]) => ' ' + key + '="' + escape(value) + '"').join('') + '>' + escape(this.text || '') + this.innerHTML + '</' + this.tag + '>'; }
  matches(selector) {
    if (selector.startsWith('#')) return this.id === selector.slice(1);
    if (selector.startsWith('.')) return (this.attrs.class || '').split(' ').includes(selector.slice(1));
    const attr = selector.match(/^(\w+)?\[([\w-]+)(?:="([^"]*)")?\]$/);
    if (attr) return (!attr[1] || this.tag === attr[1]) && attr[2] in this.attrs && (attr[3] === undefined || this.attrs[attr[2]] === attr[3]);
    return this.tag === selector;
  }
  querySelectorAll(selectors) { const result = []; for (const child of this.children) { if (selectors.split(',').some(selector => child.matches(selector.trim()))) result.push(child); result.push(...child.querySelectorAll(selectors)); } return result; }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  closest(selector) { return selector.split(',').some(part => this.matches(part.trim())) ? this : this.parentNode?.closest(selector) || null; }
  contains(node) { return node === this || this.children.some(child => child.contains(node)); }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  getAttribute(name) { return this.attrs[name] ?? null; }
  hasAttribute(name) { return name in this.attrs; }
  focus() { focused = this; }
  setSelectionRange(start, end) { this.selectionStart = start; this.selectionEnd = end; }
}
const tick = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => {resolve = yes; reject = no;}); return {promise, resolve, reject}; };
const initial = workspace_id => ({workspace_id, version:7, criteria:{include:['Original lantern studies'],exclude:['No usable outcome']}, records:{},
  flow:{identified:3,title_abstract_screened:0,title_abstract_excluded:0,full_text_assessed:0,full_text_excluded:0,full_text_excluded_by_reason:{},included:0,undecided:3}});
const decision = (value, reason = '') => ({decision:value, reason, decided_at:'2026-11-12T18:00:00Z'});
function fixture() {
  focused = null;
  const main = new Element('main'); main.root = true;
  const calls = [], overrides = new Map(), views = new Map(), saved = new Map([['one',initial('one')],['two',initial('two')]]);
  const context = {
    window:{KoshViews:{register:view => views.set(view.id, view),has:id => views.has(id),get:id => views.get(id)}},
    document:{get activeElement() {return focused;}, querySelector:selector => main.querySelector(selector)},
    state:{workspace:'one',view:'screen',intent:1,stopped:false,data:{notes:[],matrix:[],documents:[
      {id:'a',workspace_id:'one',name:'lantern.pdf',metadata:{title:'<img src=x onerror="bad()">',authors:'<b>Invented Author</b>',year:'2024',abstract:'</p><script>bad()</script>\nA lantern abstract.'}},
      {id:'b',workspace_id:'one',name:'Second source.txt',metadata:{}},
      {id:'c',workspace_id:'one',name:'Third source.txt',metadata:{}},
      {id:'archived',workspace_id:'one',name:'Never show archived',archived:true,metadata:{}},
      {id:'other',workspace_id:'two',name:'Other workspace',metadata:{}}
    ]}},
    escapeHTML:escape, headline:(title, subtitle) => '<div class="page-heading"><h1>' + escape(title) + '</h1><p>' + escape(subtitle) + '</p></div>',
    documents:() => context.state.data.documents.filter(doc => doc.workspace_id === context.state.workspace),
    openDocument:async id => {context.opened = id;}, notify(){},
    render:() => {context.renderCount = (context.renderCount || 0) + 1; views.get(context.state.view)?.render(main);},
    request:async (route, data) => {
      calls.push({route,data:plain(data ?? null)});
      if (overrides.has(route)) return overrides.get(route)(data);
      if (route.startsWith('/screening?')) return plain(saved.get(decodeURIComponent(route.split('=')[1])));
      const value = plain(saved.get(data.workspace_id)); value.version++;
      if (route === '/screening/criteria') value.criteria = plain(data.criteria);
      else if (route === '/screening/decision') {
        value.records[data.document_id] ||= {title_abstract:null,full_text:null,history:[]};
        value.records[data.document_id][data.stage] = decision(data.decision,data.reason);
      } else throw new Error('Unexpected route: ' + route);
      saved.set(data.workspace_id,value); return plain(value);
    }
  };
  context.KoshViews = context.window.KoshViews; context.window = context;
  vm.createContext(context); vm.runInContext(source,context);
  const api = context.KoshScreening;
  const render = () => views.get('screen').render(main);
  const fire = async (type, target, extra = {}) => {
    assert.ok(target,'Event target exists');
    const event = {target, preventDefault(){this.defaultPrevented = true;}, ...extra};
    for (let node = target; node; node = node.parentNode) for (const handler of node.listeners[type] || []) handler(event);
    await tick(); return event;
  };
  const click = selector => fire('click', main.querySelector(selector));
  const input = async (selector, text) => {const field = main.querySelector(selector); assert.ok(field,selector); field.value = text; await fire('input',field);};
  const posts = () => calls.filter(call => call.data);
  return {context,main,calls,overrides,views,saved,api,render,fire,click,input,posts};
}

(async () => {
  const f = fixture();
  assert.ok(f.views.has('screen'),'Registers screen');
  assert.equal(typeof f.api.counts,'function','Defines KoshScreening.counts');
  assert.equal(f.api.counts('one'),null,'Counts are unknown before load');
  assert.equal(f.api.counts('one'),null,'Repeated counts deduplicate pending load');
  await tick();
  assert.deepEqual(plain(f.api.counts('one')),initial('one').flow);
  assert.equal(f.calls.length,1);
  assert.deepEqual(f.calls[0],{route:'/screening?workspace_id=one',data:null},'Helper adds /api; query remains in path');
  f.render(); await tick();
  assert.match(f.main.textContent,/Screen/);
  for (const text of ['Identified','Screened at title/abstract','Excluded at title/abstract','Assessed at full text','Excluded at full text','Included','Undecided','Eligibility criteria','Include if','Exclude if','Maybe','All','Title & abstract','Full text']) assert.ok(f.main.textContent.includes(text),text);
  assert.equal(f.main.querySelectorAll('[data-screen-row]').length,3,'All active undecided sources');
  assert.doesNotMatch(f.main.textContent,/Never show archived|Other workspace/);
  assert.equal(f.main.querySelector('img'),null); assert.equal(f.main.querySelector('script'),null); assert.equal(f.main.querySelector('b'),null);
  assert.match(f.main.innerHTML,/&lt;script&gt;bad\(\)&lt;\/script&gt;/,'Abstract escaped');
  assert.equal(f.main.querySelector('#screen-criteria').open,false,'Existing criteria collapsed initially');
  assert.match(f.main.textContent,/Second source\.txt/,'Filename fallback');
  await f.click('[data-screen-more="a"]');
  assert.equal(f.main.querySelector('[data-screen-more="a"]').getAttribute('aria-expanded'),'true');
  await f.click('[data-screen-open="a"]'); assert.equal(f.context.opened,'a');
  await f.click('[data-screen-decision="include"]');
  assert.deepEqual(f.posts().at(-1),{route:'/screening/decision',data:{workspace_id:'one',expected_version:7,document_id:'a',stage:'title_abstract',decision:'include',reason:''}});
  assert.equal(f.main.querySelectorAll('[data-screen-row]').length,2);
  assert.equal(focused.dataset.screenRow,'b','Focus moves to next undecided source');
  await f.click('[data-screen-filter="include"]');
  assert.equal(f.main.querySelector('[data-screen-decision="include"]').getAttribute('aria-pressed'),'true');
  assert.match(f.main.textContent,/2026/,'Decision timestamp displayed');
  await f.click('[data-screen-filter="all"]');
  await f.click('[data-screen-stage="full_text"]');
  assert.equal(f.main.querySelectorAll('[data-screen-row]').length,1,'Full text only includes eligible title/abstract sources');
  const before = f.posts().length;
  await f.click('[data-screen-decision="exclude"]');
  assert.equal(f.posts().length,before,'Full-text exclusion requires a reason locally');
  assert.match(f.main.textContent,/reason.*required|required.*reason/i);
  await f.input('[data-screen-reason="a"]','  No relevant outcome  ');
  await f.click('[data-screen-decision="exclude"]');
  assert.deepEqual(f.posts().at(-1).data,{workspace_id:'one',expected_version:8,document_id:'a',stage:'full_text',decision:'exclude',reason:'  No relevant outcome  '});

  // A conflict reloads the last saved version; retry is manual and typed text survives.
  await f.input('[data-screen-reason="a"]','My typed <reason>');
  const conflict = Object.assign(new Error('Changed elsewhere'),{status:409});
  f.overrides.set('/screening/decision',async () => {throw conflict;});
  const newer = plain(f.saved.get('one')); newer.version = 12; newer.flow.full_text_excluded_by_reason = {'<script>reason</script>':2}; f.saved.set('one',newer);
  await f.click('[data-screen-decision="exclude"]'); await tick();
  assert.equal(f.main.querySelector('[data-screen-reason="a"]').value,'My typed <reason>');
  assert.match(f.main.textContent,/press.*again/i); assert.equal(f.main.querySelector('script'),null);
  assert.equal(f.posts().at(-1).data.expected_version,9);
  f.overrides.delete('/screening/decision');
  await f.click('[data-screen-decision="exclude"]');
  assert.equal(f.posts().at(-1).data.expected_version,12);

  await f.input('#screen-include','First rule\n\n Second rule '); await f.input('#screen-exclude','Exclude rule');
  await f.click('[data-screen-save-criteria]');
  assert.deepEqual(f.posts().at(-1),{route:'/screening/criteria',data:{workspace_id:'one',expected_version:13,criteria:{include:['First rule','Second rule'],exclude:['Exclude rule']}}});

  const keyboard = fixture(); keyboard.render(); await tick();
  let row = keyboard.main.querySelector('[data-screen-row]');
  await keyboard.fire('keydown',row,{key:'m'});
  assert.equal(keyboard.posts().at(-1).data.decision,'maybe');
  const reason = keyboard.main.querySelector('[data-screen-reason]');
  const keyPosts = keyboard.posts().length;
  await keyboard.fire('keydown',reason,{key:'i'});
  await keyboard.fire('keydown',keyboard.main.querySelector('[data-screen-row]'),{key:'e',ctrlKey:true});
  assert.equal(keyboard.posts().length,keyPosts,'Typing and modified shortcuts do not save');
  await keyboard.fire('keydown',keyboard.main.querySelector('[data-screen-row]'),{key:'i'});
  assert.equal(keyboard.posts().at(-1).data.decision,'include');
  await keyboard.fire('keydown',keyboard.main.querySelector('[data-screen-row]'),{key:'e'});
  assert.equal(keyboard.posts().at(-1).data.decision,'exclude');
  assert.equal(keyboard.main.querySelectorAll('[data-screen-row]').length,0);
  assert.match(keyboard.main.textContent,/Everything at this stage is decided/);

  const empty = fixture(); empty.context.state.workspace = null; empty.render();
  assert.match(empty.main.textContent,/workspace/i); assert.equal(empty.calls.length,0);
  empty.context.state.workspace = 'one'; empty.context.state.data.documents = []; empty.render(); await tick();
  assert.match(empty.main.textContent,/Find/); assert.equal(empty.main.querySelectorAll('[data-screen-row]').length,0);
  await keyboard.click('[data-screen-filter="include"]'); assert.equal(keyboard.main.querySelectorAll('[data-screen-row]').length,1);

  // An older workspace response must not enter the cache, repaint, or overwrite a new workspace.
  const stale = fixture(), old = deferred(); stale.overrides.set('/screening?workspace_id=one',() => old.promise);
  stale.render(); stale.context.state.workspace = 'two'; stale.context.state.intent++; stale.render(); await tick();
  const currentMarkup = stale.main.innerHTML;
  const wrong = initial('one'); wrong.criteria.include = ['STALE WORKSPACE']; old.resolve(wrong); await tick();
  assert.equal(stale.main.innerHTML,currentMarkup); assert.doesNotMatch(stale.main.textContent,/STALE WORKSPACE/);
  stale.overrides.delete('/screening?workspace_id=one'); stale.context.state.workspace = 'one'; stale.context.state.intent++;
  assert.equal(stale.api.counts('one'),null,'Discarded old response never populated cache'); await tick();

  const lateSave = fixture(), pendingSave = deferred(); lateSave.render(); await tick();
  lateSave.overrides.set('/screening/decision',() => pendingSave.promise);
  await lateSave.click('[data-screen-decision="include"]'); await lateSave.click('[data-screen-decision="include"]');
  assert.equal(lateSave.posts().length,1,'Pending write cannot be submitted twice');
  lateSave.context.state.workspace = 'two'; lateSave.context.state.intent++; lateSave.render(); await tick();
  const otherMarkup = lateSave.main.innerHTML;
  const late = initial('one'); late.criteria.include = ['LATE SAVE']; pendingSave.resolve(late); await tick();
  assert.equal(lateSave.main.innerHTML,otherMarkup);

  const stopped = fixture(), pendingLoad = deferred(); stopped.overrides.set('/screening?workspace_id=one',() => pendingLoad.promise);
  stopped.render(); stopped.context.state.stopped = true; const stoppedMarkup = stopped.main.innerHTML;
  pendingLoad.reject(new Error('Late after Quit')); await tick(); assert.equal(stopped.main.innerHTML,stoppedMarkup);

  // Two reads for the same workspace may finish in the opposite order.
  const ordered = fixture(), first = deferred();
  ordered.overrides.set('/screening?workspace_id=one',() => first.promise); ordered.render();
  ordered.overrides.delete('/screening?workspace_id=one'); await ordered.api.load('one',true);
  const obsolete = initial('one'); obsolete.version = 2; obsolete.flow.included = 99;
  first.resolve(obsolete); await tick(); assert.equal(ordered.api.counts('one').included,0,'Newest read wins');

  // Changing criteria during a pending save cannot erase the newer unsaved text.
  const editing = fixture(), criteriaSave = deferred(); editing.render(); await tick();
  await editing.input('#screen-include','Submitted criteria');
  editing.overrides.set('/screening/criteria',() => criteriaSave.promise);
  await editing.click('[data-screen-save-criteria]');
  await editing.input('#screen-include','Newer unsaved criteria');
  const savedCriteria = initial('one'); savedCriteria.version = 8; savedCriteria.criteria.include = ['Submitted criteria'];
  criteriaSave.resolve(savedCriteria); await tick();
  assert.equal(editing.main.querySelector('#screen-include').value,'Newer unsaved criteria','Late save keeps newer edits');
  assert.match(editing.main.textContent,/Newer edits are not saved yet/);

  const criteriaConflict = fixture(); criteriaConflict.render(); await tick();
  await criteriaConflict.input('#screen-include','My include rule'); await criteriaConflict.input('#screen-exclude','My exclude rule');
  criteriaConflict.overrides.set('/screening/criteria',async () => {throw conflict;});
  criteriaConflict.saved.get('one').version = 21;
  await criteriaConflict.click('[data-screen-save-criteria]'); await tick();
  assert.equal(criteriaConflict.main.querySelector('#screen-include').value,'My include rule');
  assert.equal(criteriaConflict.main.querySelector('#screen-exclude').value,'My exclude rule');
  criteriaConflict.overrides.delete('/screening/criteria'); await criteriaConflict.click('[data-screen-save-criteria]');
  assert.equal(criteriaConflict.posts().at(-1).data.expected_version,21);

  // A concurrent decision can remove this source from Undecided. Keep its retry visible.
  const decidedElsewhere = fixture(); decidedElsewhere.render(); await tick();
  await decidedElsewhere.input('[data-screen-reason="a"]','Keep my pending judgement');
  decidedElsewhere.saved.get('one').records.a = {title_abstract:decision('maybe','Other window'),full_text:null,history:[]};
  decidedElsewhere.saved.get('one').version = 22;
  decidedElsewhere.overrides.set('/screening/decision',async () => {throw conflict;});
  await decidedElsewhere.click('[data-screen-decision="include"]'); await tick();
  assert.equal(decidedElsewhere.main.querySelector('[data-screen-reason="a"]')?.value,'Keep my pending judgement','Conflicting source remains visible to review and retry');
  assert.equal(decidedElsewhere.main.querySelector('[data-screen-filter="all"]').getAttribute('aria-pressed'),'true');

  // A failed conflict reload keeps fields, blocks stale writes, and offers retry.
  const failedReload = fixture(); failedReload.render(); await tick();
  await failedReload.input('[data-screen-reason="a"]','Retained across failure');
  failedReload.overrides.set('/screening/decision',async () => {throw conflict;});
  failedReload.overrides.set('/screening?workspace_id=one',async () => {throw new Error('Local read failed');});
  await failedReload.click('[data-screen-decision="include"]'); await tick();
  assert.equal(failedReload.main.querySelector('[data-screen-reason="a"]').value,'Retained across failure');
  const beforeFailedRetry = failedReload.posts().length;
  await failedReload.click('[data-screen-decision="include"]');
  assert.equal(failedReload.posts().length,beforeFailedRetry,'Do not save against state that failed to reload');
  failedReload.overrides.delete('/screening?workspace_id=one'); failedReload.overrides.delete('/screening/decision');
  await failedReload.click('[data-screen-retry]'); await tick();
  await failedReload.click('[data-screen-decision="include"]');
  assert.equal(failedReload.posts().at(-1).data.reason,'Retained across failure');

  // New/archived sources refresh saved flow once; metadata is read from current sources.
  const changed = fixture(); changed.render(); await tick(); const initialReads = changed.calls.length;
  changed.context.state.data.documents.push({id:'new',workspace_id:'one',name:'Newly added source'});
  changed.saved.get('one').flow.identified = 4; changed.saved.get('one').flow.undecided = 4;
  changed.render(); await tick();
  assert.equal(changed.api.counts('one').identified,4); assert.equal(changed.calls.length,initialReads + 1);
  assert.equal(changed.main.querySelectorAll('[data-screen-row]').length,4);
  changed.context.state.data.documents.find(doc => doc.id === 'new').archived = true;
  changed.saved.get('one').flow.identified = 3; changed.render(); await tick();
  assert.equal(changed.api.counts('one').identified,3); assert.equal(changed.main.querySelectorAll('[data-screen-row]').length,3);

  // Both permitted title/abstract decisions enter full text; excluded sources do not.
  const stages = fixture(), stageState = stages.saved.get('one');
  stageState.records = {
    a:{title_abstract:decision('include'),full_text:decision('include'),history:[]},
    b:{title_abstract:decision('maybe'),full_text:null,history:[]},
    c:{title_abstract:decision('exclude','Not eligible'),full_text:null,history:[]}
  };
  stageState.flow = {identified:3,title_abstract_screened:3,title_abstract_excluded:1,full_text_assessed:1,full_text_excluded:0,full_text_excluded_by_reason:{},included:1,undecided:1};
  stages.render(); await tick(); await stages.click('[data-screen-filter="all"]');
  assert.match(stages.main.textContent,/Undecided \(0\).*Maybe \(1\).*Included \(1\).*Excluded \(1\).*All \(3\)/);
  const titleInclude = stages.main.querySelector('[data-screen-row="a"]');
  await stages.fire('click',titleInclude.querySelector('[data-screen-decision="exclude"]'));
  assert.equal(stages.posts().length,0,'Existing full-text decision prevents title/abstract exclusion locally');
  await stages.click('[data-screen-stage="full_text"]');
  assert.deepEqual(stages.main.querySelectorAll('[data-screen-row]').map(node => node.dataset.screenRow),['a','b']);
  assert.match(stages.main.textContent,/Undecided \(1\).*Maybe \(0\).*Included \(1\).*Excluded \(0\).*All \(2\)/);
  assert.match(stages.main.textContent,/Screened at title\/abstract: 3/);
  await stages.click('[data-screen-filter="undecided"]');
  const stageReason = stages.main.querySelector('[data-screen-reason="b"]'); stageReason.focus(); stageReason.setSelectionRange(0,0);
  stages.render(); assert.equal(focused,stages.main.querySelector('[data-screen-reason="b"]'),'Rerender retains text input focus');

  // Existing Overview actually consumes loaded counts and enables Open Screen.
  const overview = fixture(); overview.context.state.view = 'overview';
  overview.context.nextStep = () => null; overview.context.draftCitationEntries = () => [];
  const overviewState = overview.saved.get('one'); overviewState.flow.included = 2; overviewState.flow.undecided = 1;
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../ui/overview.js'),'utf8'),overview.context);
  overview.context.render(); await tick();
  assert.match(overview.main.textContent,/2 included sources · 1 undecided source/);
  assert.equal(overview.main.querySelector('[data-view="screen"]').disabled,false);
  assert.equal(overview.calls.length,1,'Overview loads screening counts in the background');
  console.log('Screening page, decisions, conflicts and workspace guards passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
