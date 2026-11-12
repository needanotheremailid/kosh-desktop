'use strict';

/* Manual decisions only. Saved flow counts belong to screening.py, not this UI. */
window.KoshScreening = (() => {
  const workspaces = new Map();
  const filters = {undecided:'Undecided',maybe:'Maybe',include:'Included',exclude:'Excluded',all:'All'};
  const html = value => escapeHTML(String(value ?? ''));
  let host = null, hostWorkspace = null;

  function entry(workspaceId) {
    if (!workspaces.has(workspaceId)) workspaces.set(workspaceId, {
      value:null, sequence:0, pending:null, writing:null, attemptedIntent:null,
      signature:null, reloadRequired:false, error:'', message:'', filter:'undecided', stage:'title_abstract',
      reasons:new Map(), expanded:new Set(), criteriaDraft:null, criteriaOpen:null, rowErrors:new Map()
    });
    return workspaces.get(workspaceId);
  }
  function sourceSignature(workspaceId) {
    return JSON.stringify(state.data.documents.filter(doc => doc.workspace_id === workspaceId).map(doc => [doc.id,!!doc.archived]));
  }
  function current(workspaceId, ticket, value) {
    return !state.stopped && workspaceId === state.workspace && ticket.intent === state.intent && ticket.sequence === value.sequence;
  }
  function repaint(workspaceId) {
    if (!state.stopped && state.workspace === workspaceId && ['screen','overview'].includes(state.view)) render();
  }
  function needsLoad(workspaceId, value) {
    return value.attemptedIntent !== state.intent || value.signature !== sourceSignature(workspaceId);
  }
  async function load(workspaceId, force = false) {
    if (!workspaceId || state.stopped || workspaceId !== state.workspace) return;
    const value = entry(workspaceId);
    if (value.writing) return;
    if (value.pending?.intent === state.intent && !force) return value.pending.promise;
    const ticket = {intent:state.intent, sequence:++value.sequence};
    value.attemptedIntent = state.intent; value.signature = sourceSignature(workspaceId); value.error = '';
    value.pending = ticket;
    ticket.promise = (async () => {
      try {
        const result = await request('/screening?workspace_id=' + encodeURIComponent(workspaceId));
        if (!current(workspaceId,ticket,value)) return;
        if (result.workspace_id !== workspaceId) throw new Error('Screening returned a different workspace. Reload records.');
        value.value = result; value.reloadRequired = false;
      } catch (error) {
        if (current(workspaceId,ticket,value)) {value.error = error.message; value.reloadRequired = true;}
      } finally {
        if (value.pending === ticket) {
          value.pending = null;
          if (current(workspaceId,ticket,value)) repaint(workspaceId);
        }
      }
    })();
    return ticket.promise;
  }
  function counts(workspaceId) {
    if (!workspaceId) return null;
    const value = entry(workspaceId);
    if (workspaceId === state.workspace && needsLoad(workspaceId,value)) void load(workspaceId);
    return value.value?.flow || null;
  }
  function reasonKey(stage, id) { return stage + ':' + id; }
  function recordFor(value, id) { return value.value.records[id]?.[value.stage] || null; }
  function activeSources(value) {
    return documents().filter(doc => !doc.archived && (value.stage !== 'full_text' || ['include','maybe'].includes(value.value.records[doc.id]?.title_abstract?.decision)));
  }
  function matchesFilter(value, doc, filter = value.filter) {
    const record = recordFor(value,doc.id);
    return filter === 'all' || (filter === 'undecided' ? !record : record?.decision === filter);
  }
  function flowLine(flow) {
    const reasons = Object.entries(flow.full_text_excluded_by_reason).map(([reason,count]) => html(reason) + ': ' + html(count)).join('; ');
    return '<section class="screen-section screen-flow" aria-label="Screening flow"><dl class="screen-flow-counts">' + [
      ['Identified',flow.identified],['Screened at title/abstract',flow.title_abstract_screened],
      ['Excluded at title/abstract',flow.title_abstract_excluded],['Assessed at full text',flow.full_text_assessed],
      ['Excluded at full text',flow.full_text_excluded],['Included',flow.included],['Undecided',flow.undecided]
    ].map(([label,count]) => '<div><dt>' + html(label) + ': </dt><dd>' + html(count) + '</dd></div>').join('') + '</dl>' +
      (reasons ? '<p class="small muted">Full-text exclusion reasons — ' + reasons + '</p>' : '') +
      '<p class="small muted">Included means included at full text. Undecided includes sources still awaiting a final decision. Filters below count decisions at the selected stage.</p></section>';
  }
  function criteriaSection(value) {
    const draft = value.criteriaDraft || {include:value.value.criteria.include.join('\n'),exclude:value.value.criteria.exclude.join('\n')};
    const hasCriteria = value.value.criteria.include.length || value.value.criteria.exclude.length;
    const open = value.criteriaOpen ?? !hasCriteria;
    return '<details class="screen-section" id="screen-criteria"' + (open ? ' open' : '') + '><summary>Eligibility criteria</summary><p class="small muted">Your own rules, one criterion per line. Changes save only when you press Save criteria.</p>' +
      '<div class="screen-criteria-fields"><label for="screen-include">Include if<textarea id="screen-include" rows="3" data-screen-criteria="include">' + html(draft.include) + '</textarea></label>' +
      '<label for="screen-exclude">Exclude if<textarea id="screen-exclude" rows="3" data-screen-criteria="exclude">' + html(draft.exclude) + '</textarea></label></div>' +
      '<button class="button" data-screen-save-criteria' + (value.writing || value.pending || value.reloadRequired ? ' disabled' : '') + '>Save criteria</button></details>';
  }
  function sourceRow(doc, value) {
    const metadata = doc.metadata || {}, record = recordFor(value,doc.id), key = reasonKey(value.stage,doc.id);
    const reason = value.reasons.has(key) ? value.reasons.get(key) : record?.reason || '';
    const authors = Array.isArray(metadata.authors) ? metadata.authors.join(', ') : metadata.authors;
    const expanded = value.expanded.has(doc.id), error = value.rowErrors.get(key);
    const abstractId = 'screen-abstract-' + doc.id, reasonId = 'screen-reason-' + doc.id, errorId = 'screen-error-' + doc.id;
    return '<article class="screen-row" tabindex="0" data-screen-row="' + html(doc.id) + '"><div class="screen-source-copy"><h2>' + html(metadata.title || doc.name || 'Untitled source') + '</h2>' +
      ([authors,metadata.year,doc.kind].some(Boolean) ? '<p class="small muted">' + [authors,metadata.year,doc.kind].filter(Boolean).map(html).join(' · ') + '</p>' : '') +
      (metadata.abstract ? '<p class="screen-abstract' + (expanded ? ' is-expanded' : '') + '" id="' + html(abstractId) + '">' + html(metadata.abstract) + '</p><button class="text-button" data-screen-more="' + html(doc.id) + '" aria-expanded="' + expanded + '" aria-controls="' + html(abstractId) + '">' + (expanded ? 'Show less' : 'Show more') + '</button>' : '') +
      '</div><div class="screen-source-actions"><div class="screen-decisions" role="group" aria-label="Decision for this source">' + ['include','maybe','exclude'].map(choice => '<button class="button" data-screen-decision="' + choice + '" aria-pressed="' + (record?.decision === choice) + '"' + (value.writing || value.pending || value.reloadRequired ? ' disabled' : '') + '>' + {include:'Include',maybe:'Maybe',exclude:'Exclude'}[choice] + '</button>').join('') + '</div>' +
      '<input class="screen-reason" type="text" maxlength="2000" id="' + html(reasonId) + '" data-screen-reason="' + html(doc.id) + '" value="' + html(reason) + '" placeholder="Reason (required to exclude at full text)" aria-label="Reason' + (value.stage === 'full_text' ? ' (required to exclude at full text)' : ' (optional at title and abstract)') + '" aria-describedby="' + html(errorId) + '"' + (error ? ' aria-invalid="true"' : '') + '>' +
      '<p class="error-text small" id="' + html(errorId) + '" data-screen-row-status="' + html(doc.id) + '" role="status">' + html(error || '') + '</p>' +
      '<div class="screen-row-footer">' + (record ? '<span class="small muted"><time datetime="' + html(record.decided_at) + '" title="Decided ' + html(record.decided_at) + '">Decided ' + html(typeof dateLabel === 'function' ? dateLabel(record.decided_at) : record.decided_at) + '</time></span>' : '') +
      '<button class="text-button" data-screen-open="' + html(doc.id) + '">Open in Read</button></div></div></article>';
  }
  function setBusy(busy) {
    if (!host?.isConnected || state.view !== 'screen') return;
    for (const button of host.querySelectorAll('[data-screen-decision],[data-screen-save-criteria]')) button.disabled = busy;
    if (busy) host.querySelector('#screen-status').textContent = 'Saving your manual changes…';
  }
  async function save(workspaceId, route, fields, nextId = null) {
    const value = entry(workspaceId);
    if (workspaceId !== state.workspace || value.writing || value.pending || value.reloadRequired || !value.value || state.stopped) return;
    const ticket = {intent:state.intent,sequence:++value.sequence}, criteriaDraft = value.criteriaDraft;
    const stage = value.stage, filter = value.filter;
    value.writing = ticket; value.message = ''; value.error = ''; setBusy(true);
    let conflicted = false;
    try {
      const result = await request(route,{workspace_id:workspaceId,expected_version:value.value.version,...fields});
      if (!current(workspaceId,ticket,value)) return;
      if (result.workspace_id !== workspaceId) throw new Error('Screening returned a different workspace. Reload records.');
      value.value = result;
      if (route === '/screening/criteria' && value.criteriaDraft === criteriaDraft) {value.criteriaDraft = null; value.criteriaOpen = false;}
      value.message = route === '/screening/criteria' ? (value.criteriaDraft ? 'Earlier criteria saved. Newer edits are not saved yet.' : 'Criteria saved.') : 'Decision saved.';
    } catch (error) {
      if (!current(workspaceId,ticket,value)) return;
      if (error.status === 409) {
        conflicted = true;
        value.message = 'Records changed in another window. Your typed fields are kept. Reloading saved records…';
      } else value.error = error.message;
    } finally {
      if (value.writing === ticket) value.writing = null;
      if (current(workspaceId,ticket,value)) {
        if (conflicted) {
          await load(workspaceId,true);
          if (!state.stopped && state.workspace === workspaceId && state.intent === ticket.intent) {
            value.message = value.error ? 'Your typed fields are kept. Retry loading saved records before saving again.' : 'Saved records reloaded. Your typed fields are kept. Review them and press the button again.';
            if (!value.error && fields.document_id && value.stage === stage && value.filter === filter) {
              const doc = activeSources(value).find(source => source.id === fields.document_id);
              if (doc && !matchesFilter(value,doc)) {
                value.filter = 'all';
                value.message += ' Showing All so this source stays visible for your review.';
              } else if (!doc) value.message = 'Saved records reloaded. This source is archived or no longer eligible for this stage. Your typed reason is kept; review the source and its title/abstract decision before retrying.';
            }
            repaint(workspaceId);
          }
        } else {
          repaint(workspaceId);
          if (!value.error && nextId && state.view === 'screen' && value.stage === stage && value.filter === filter) [...host.querySelectorAll('[data-screen-row]')].find(row => row.dataset.screenRow === nextId)?.focus();
        }
      } else {
        // A completed write may have changed the server even though its old UI is gone.
        value.attemptedIntent = null;
        if (!state.stopped && workspaceId === state.workspace) {void load(workspaceId); repaint(workspaceId);}
      }
    }
  }
  function choose(workspaceId, id, choice) {
    const value = entry(workspaceId);
    if (workspaceId !== state.workspace || value.writing || value.pending || value.reloadRequired || !value.value) return;
    const doc = activeSources(value).find(source => source.id === id);
    if (!doc) return;
    const key = reasonKey(value.stage,id), record = recordFor(value,id);
    const reason = value.reasons.has(key) ? value.reasons.get(key) : record?.reason || '';
    let error = '';
    if (value.stage === 'full_text' && choice === 'exclude' && !reason.trim()) error = 'A reason is required before excluding at full text.';
    if (value.stage === 'title_abstract' && choice === 'exclude' && value.value.records[id]?.full_text) error = 'This source already has a full-text decision. Review it at Full text; title/abstract exclusion is unavailable.';
    if (error) {value.rowErrors.set(key,error); renderPage(host); return;}
    value.rowErrors.delete(key);
    const visible = activeSources(value).filter(source => matchesFilter(value,source));
    const index = visible.findIndex(source => source.id === id);
    const nextId = value.filter === 'undecided' ? (visible[index + 1] || visible[index - 1])?.id : null;
    void save(workspaceId,'/screening/decision',{document_id:id,stage:value.stage,decision:choice,reason},nextId);
  }
  function bind(page, workspaceId, value) {
    page.addEventListener('input',event => {
      const target = event.target;
      if (target.dataset.screenReason !== undefined) {
        value.reasons.set(reasonKey(value.stage,target.dataset.screenReason),target.value);
        value.rowErrors.delete(reasonKey(value.stage,target.dataset.screenReason));
        target.setAttribute('aria-invalid','false');
        const status = target.closest('[data-screen-row]').querySelector('[data-screen-row-status]'); status.textContent = '';
      }
      if (target.dataset.screenCriteria) {
        value.criteriaDraft = {include:page.querySelector('#screen-include').value,exclude:page.querySelector('#screen-exclude').value};
        value.criteriaOpen = true;
      }
    });
    page.querySelector('#screen-criteria')?.addEventListener('toggle',event => {if (page.isConnected && state.workspace === workspaceId) value.criteriaOpen = event.target.open;});
    page.addEventListener('click',event => {
      if (workspaceId !== state.workspace || state.stopped) return;
      const button = event.target.closest('button'); if (!button || button.disabled) return;
      if (button.dataset.screenDecision) choose(workspaceId,button.closest('[data-screen-row]').dataset.screenRow,button.dataset.screenDecision);
      else if (button.dataset.screenFilter) {value.filter = button.dataset.screenFilter; renderPage(host);}
      else if (button.dataset.screenStage) {value.stage = button.dataset.screenStage; renderPage(host);}
      else if (button.dataset.screenMore) {
        const id = button.dataset.screenMore;
        if (value.expanded.has(id)) value.expanded.delete(id); else value.expanded.add(id);
        renderPage(host);
      } else if (button.dataset.screenOpen) {
        void openDocument(button.dataset.screenOpen).catch(error => {if (!state.stopped && state.workspace === workspaceId) notify(error.message,true);});
      } else if (button.hasAttribute('data-screen-save-criteria')) {
        const lists = {include:page.querySelector('#screen-include').value,exclude:page.querySelector('#screen-exclude').value};
        const criteria = Object.fromEntries(Object.entries(lists).map(([key,text]) => [key,text.split(/\r?\n/).map(line => line.trim()).filter(Boolean)]));
        if (Object.values(criteria).some(list => list.length > 100 || list.some(line => line.length > 2000))) {
          value.error = 'Each list supports up to 100 criteria, with at most 2,000 characters per criterion.'; renderPage(host); return;
        }
        value.criteriaDraft = lists;
        void save(workspaceId,'/screening/criteria',{criteria});
      } else if (button.hasAttribute('data-screen-retry')) {void load(workspaceId,true); renderPage(host);}
    });
    page.addEventListener('keydown',event => {
      if (event.ctrlKey || event.altKey || event.metaKey || event.shiftKey || event.isComposing || event.repeat || event.target.closest('input,textarea,select,[contenteditable]')) return;
      const row = event.target.closest('[data-screen-row]'), choice = {i:'include',m:'maybe',e:'exclude'}[event.key];
      if (row && choice) {event.preventDefault(); choose(workspaceId,row.dataset.screenRow,choice);}
    });
  }
  function renderPage(main) {
    if (!main || state.stopped) return;
    const focused = document.activeElement;
    const savedFocus = hostWorkspace === state.workspace && main.contains(focused) && focused.id ? {id:focused.id,start:focused.selectionStart,end:focused.selectionEnd} : null;
    const restoreFocus = () => {
      const target = savedFocus && [...main.querySelectorAll('input,textarea')].find(field => field.id === savedFocus.id);
      if (target) {target.focus({preventScroll:true}); if (Number.isInteger(savedFocus.start)) target.setSelectionRange(savedFocus.start,savedFocus.end);}
    };
    host = main; hostWorkspace = state.workspace;
    const heading = headline('Screen','Decisions here are your own manual judgement; nothing is screened automatically.');
    if (!state.workspace) {main.innerHTML = heading + '<p>Choose or create a workspace before screening sources.</p>'; return;}
    const workspaceId = state.workspace, value = entry(workspaceId);
    if (needsLoad(workspaceId,value)) void load(workspaceId);
    const status = '<p id="screen-status" role="status" class="' + (value.error ? 'error-text' : 'muted') + '">' + html(value.error || value.message || (value.pending ? 'Loading saved screening records…' : '')) + '</p>' +
      (value.error ? '<button class="button" data-screen-retry>Reload screening records</button>' : '');
    if (!value.value) {
      main.innerHTML = heading + '<div id="screen-page">' + status + '</div>';
      bind(main.querySelector('#screen-page'),workspaceId,value); return;
    }
    const all = activeSources(value), visible = all.filter(doc => matchesFilter(value,doc));
    const filterBar = '<div class="screen-controls"><div class="screen-filter" role="group" aria-label="Filter decisions">' + Object.entries(filters).map(([key,label]) => '<button class="button" data-screen-filter="' + key + '" aria-pressed="' + (value.filter === key) + '">' + label + ' (' + all.filter(doc => matchesFilter(value,doc,key)).length + ')</button>').join('') + '</div>' +
      '<div class="screen-stage" role="group" aria-label="Screening stage">' + [['title_abstract','Title & abstract'],['full_text','Full text']].map(([key,label]) => '<button class="button" data-screen-stage="' + key + '" aria-pressed="' + (value.stage === key) + '">' + html(label) + '</button>').join('') + '</div></div>';
    const noSources = !documents().some(doc => !doc.archived);
    const empty = noSources ? '<p>No active sources yet. <button class="text-button" data-view="discover">Open Find to add sources</button></p>' :
      '<p>No sources in this filter.' + (value.filter === 'undecided' ? ' Everything at this stage is decided, or no sources are ready for this stage.' : '') + ' Choose another filter or stage.</p>';
    main.innerHTML = heading + '<div id="screen-page">' + flowLine(value.value.flow) + criteriaSection(value) + filterBar +
      '<p class="small muted">Focus a source row and press i to Include, m for Maybe or e to Exclude. Shortcuts do not run while typing a reason.</p>' + status +
      '<div class="screen-sources">' + (visible.length ? visible.map(doc => sourceRow(doc,value)).join('') : empty) + '</div></div>';
    bind(main.querySelector('#screen-page'),workspaceId,value);
    restoreFocus();
  }
  window.KoshViews.register({id:'screen',title:'Screen',subtitle:'Your manual eligibility decisions',render:renderPage});
  return {counts,load,render:renderPage};
})();
