/* Local research artefacts. This page never sends content to a provider. */
window.KoshResearch = (() => {
  let page, host, status, workspace = null, overview = null, result = null;
  let sequence = 0, pageIntent = 0, busy = false, saved = false, loading = false;
  const savedSearches = new WeakSet();
  const savingSearches = new WeakSet(), savingResults = new WeakSet();
  const html = value => escapeHTML(String(value ?? ''));
  const recipes = {
    reading: {title: 'Read a paper carefully', steps: ['Record the research question in your own words.', 'Check the source details against the paper.', 'Read methods, results and limitations in the original.', 'Use a reading packet to inspect exact extracted text; check any missing pages or images.', 'Save exact quotes with page or section links.', 'Record your interpretation separately from the quoted evidence.', 'Check each claim against its source before using it in a draft.']},
    search: {title: 'Plan and record a literature search', steps: ['Write a focused question and define its scope.', 'List each main concept, its synonyms and any limits.', 'Prepare the query for the selected index; review it before sending.', 'Search the index explicitly and save its search record.', 'Record why each useful paper matters; an index result is not the full paper.', 'Import authorised full texts and check citation details.', 'Record missed indexes, failed searches and the next query to try. This checklist is not a formal screening protocol.']},
    synthesis: {title: 'Compare sources before writing', steps: ['Choose the sources relevant to this question.', 'Read each source and save manual findings in Evidence.', 'Keep design, findings and limitations separate.', 'Prepare a source comparison from the saved rows.', 'Check missing fields in the original papers; do not turn Not recorded into a negative finding.', 'Write where the studies agree and disagree, with source links.', 'Recheck the saved row versions when the evidence changes.']},
    manuscript: {title: 'Build a source-linked manuscript', steps: ['Choose a configurable manuscript outline in Write.', 'Fill in only verified author-supplied methods and findings.', 'Cite while writing and keep the source beside the draft.', 'Review each factual claim against the original passage.', 'Run Writing check and Project review; these do not certify scientific correctness.', 'Review tables, figures, equations and bibliography in the exported document.', 'Complete the journal requirements and required disclosures before submission.']},
    analysis: {title: 'Prepare an analysis handoff', steps: ['State the exact question and intended result.', 'Identify the selected dataset and its data dictionary.', 'Describe units, missing values and the planned method.', 'Keep original data unchanged and choose separate output filenames.', 'Ask an authorised analysis tool to propose its method and code for review; this checklist runs no code.', 'Check assumptions, numerical results and uncertainty independently.', 'Retain the approved code, input identity, tool version and output together.']},
    presentation: {title: 'Turn findings into figures or slides', steps: ['State the audience and one point each figure or slide must explain.', 'Link every factual statement to a reviewed source or approved analysis.', 'Choose the form: table, chart, diagram, poster or slide deck.', 'Prepare the content in Kosh and use a separately authorised creation tool for unsupported formats.', 'Check units, labels, legibility, missing values and uncertainty.', 'Inspect the final exported pages or slides before sharing.']},
    reviewer: {title: 'Respond to reviewer comments', steps: ['Save the exact reviewer comment in Reviewer responses.', 'Link the comment to the correct saved manuscript passage.', 'Write the proposed change and response separately.', 'Edit the draft deliberately and recheck its citations.', 'Check stale passage links after revisions.', 'Export the response letter and read it beside the final manuscript.']}
  };

  function setBusy(value) {
    busy = value;
    if (state.stopped) return;
    for (const button of host.querySelectorAll('[data-research-build],#research-save,#research-download,[data-research-recipe],#research-ask,#research-question,#research-budget,#research-preview,#research-source-filter,[data-research-source]')) button.disabled = value || (button.id === 'research-save' && saved);
  }
  function active(ticket = sequence) { return ticket === sequence && workspace === state.workspace && pageIntent === state.intent && state.view === 'synthesise' && !state.stopped && page?.isConnected; }
  function fail(error) { if (active()) {status.textContent = error.message; status.className = 'error-text';} }
  function outputMarkdown() { return result?.markdown || result?.body || ''; }
  function renderOutput() {
    const target = host.querySelector('#research-output');
    if (!target) return;
    target.innerHTML = !result ? '<p class="muted">Nothing prepared yet</p>' : '<h3>' + html(result.title) + '</h3><p>' + html(result.notice || 'Review this local record before saving.') + '</p>' +
      (result.sources ? '<ul class="research-coverage">' + result.sources.map(source => '<li><strong>' + html(source.name) + '</strong> — ' + html(source.coverage) +
        ' · ' + source.chars_included + ' of ' + source.chars_total + ' extracted characters' + (source.chars_omitted ? ' · ' + source.chars_omitted + ' left out' : '') + '</li>').join('') + '</ul>' : '') +
      '<label for="research-preview">Prepared Markdown · review before saving or using with an agent</label><textarea id="research-preview" ' + (result.editable ? '' : 'readonly ') + 'spellcheck="false">' + html(outputMarkdown()) + '</textarea>' +
      '<div class="research-actions"><button class="button primary" id="research-save" ' + (saved ? 'disabled' : '') + '>' + (saved ? 'Saved as a separate draft' : 'Save as a separate draft') + '</button><button class="button" id="research-download">Download Markdown</button></div>';
  }
  function updateSourcePicker() {
    const query=(host.querySelector('#research-source-filter')?.value||'').trim().toLocaleLowerCase();
    let visible=0;
    for(const row of host.querySelectorAll('[data-research-source-row]')) {
      row.hidden=!row.querySelector('strong').textContent.toLocaleLowerCase().includes(query);
      if(!row.hidden)visible++;
    }
    const count=host.querySelector('#research-selection-count');
    if(count)count.textContent='Selected: '+host.querySelectorAll('[data-research-source]:checked').length+' of 10';
    const empty=host.querySelector('#research-filter-empty');
    if(empty)empty.hidden=visible>0;
  }
  function renderSources() {
    const priorBoxes = [...host.querySelectorAll('[data-research-source]')];
    const selected = new Set(priorBoxes.filter(box => box.checked).map(box => box.value));
    const budget = host.querySelector('#research-budget')?.value;
    const question = host.querySelector('#research-question')?.value;
    const filter = host.querySelector('#research-source-filter')?.value;
    const active = overview.sources.filter(source => !source.archived);
    host.innerHTML = '<p class="muted small">' + html(overview.notice) + '</p><section class="research-section" aria-labelledby="research-sources-title"><h2 id="research-sources-title">Choose sources</h2><p>Choose one to ten sources for a reading packet, comparison or question.</p>' +
      (active.length ? '<div class="research-source-controls">' + (active.length>12?'<label for="research-source-filter">Filter by title<input type="search" id="research-source-filter" placeholder="Filter sources by title" aria-controls="research-source-list"></label>':'') + '<p class="small muted" id="research-selection-count" role="status" aria-live="polite"></p></div><div class="research-source-list" id="research-source-list">' + active.map(source => '<section class="research-source" data-research-source-row><label><input type="checkbox" data-research-source value="' + source.id + '" ' +
        (state.doc?.id === source.id ? 'checked' : '') + '> <strong>' + html(source.name) + '</strong></label><p class="research-source-meta muted small">' +
        (source.metadata_only ? 'Catalogue metadata only' : source.text_units + ' text-bearing page(s) / section(s) of ' + source.units) + ' · ' + source.evidence_rows + ' saved evidence row(s)' +
        (source.linked_notes.length ? ' · Used in ' + source.linked_notes.map(note => '<button type="button" class="text-button" role="link" data-research-note="' + note.id + '">' + html(note.title || 'Untitled draft') + ' · v' + note.version + '</button>').join(', ') : '') + '</p>' +
        '<button type="button" class="text-button research-source-open" data-research-open="' + source.id + '">Open source</button></section>').join('') + '</div><p class="small muted" id="research-filter-empty" hidden>No sources match this title.</p>' : '<p>No active sources yet. <button class="text-button" data-view="discover">Open Find to import sources</button></p>') +
      '</section><section class="research-section" aria-labelledby="research-packet-title"><h2 id="research-packet-title">Reading packet</h2><label for="research-budget">Extracted-text budget</label><select id="research-budget"><option value="12000">12,000 characters</option><option value="24000" selected>24,000 characters</option><option value="64000">64,000 characters</option><option value="100000">100,000 characters</option></select>' +
      '<p class="muted small">Equal text coverage per source, not proof of reading or a model token budget.</p><button class="button primary" data-research-build="packet">Prepare reading packet</button></section>' +
      '<section class="research-section" aria-labelledby="research-comparison-title"><h2 id="research-comparison-title">Compare saved evidence</h2><p>Compare saved evidence; check Not recorded fields in the original sources.</p><button class="button" data-research-build="comparison">Prepare source comparison</button></section>' +
      '<section class="research-section" aria-labelledby="research-question-title"><h2 id="research-question-title">Ask about selected sources</h2><label for="research-question">Your question</label><textarea id="research-question" rows="3" maxlength="4000" placeholder="What do these sources agree on, and what remains uncertain?"></textarea><p class="muted small">Review the exact excerpt-only prompt in Agent assistance before authorising a send.</p><div class="research-actions"><button type="button" class="button" id="research-ask">Choose agent &amp; review excerpts</button></div></section>' +
      '<section class="research-section research-recipes" aria-labelledby="research-checklists-title"><h2 id="research-checklists-title">Planning checklists</h2><p>Choose a checklist, then edit it in the preview. Creating one does not run its steps.</p>' + Object.entries(recipes).map(([key, recipe]) => '<button class="text-button" data-research-recipe="' + key + '">' + html(recipe.title) + '</button>').join('') + '</section>' +
      '<section class="research-section" aria-labelledby="research-preview-title"><h2 id="research-preview-title">Preview, save or download</h2><p class="muted small">Preparation stays local. Nothing is saved until you choose Save as a separate draft. Questions open Agent assistance for separate preview and consent.</p><div id="research-output"></div></section>';
    if (budget !== undefined) host.querySelector('#research-budget').value = budget;
    if (question !== undefined) host.querySelector('#research-question').value = question;
    if (budget !== undefined) for (const box of host.querySelectorAll('[data-research-source]')) box.checked = selected.has(box.value);
    if (filter !== undefined && host.querySelector('#research-source-filter')) host.querySelector('#research-source-filter').value = filter;
    updateSourcePicker();
    renderOutput(); setBusy(savingResults.has(result));
  }
  function mount(main) {
    page = document.createElement('div'); page.className = 'research-page';
    page.innerHTML = headline('Synthesise', 'Compare saved evidence, prepare reading packets and plan your next research step.') + '<p id="research-status" class="muted" role="status" aria-live="polite"></p><div id="research-content"></div>';
    host = page.querySelector('#research-content'); status = page.querySelector('#research-status');
    main.replaceChildren(page);
    host.addEventListener('click', event => {
      const button = event.target.closest('button'); if (!button) return;
      if (!active() || busy) return;
      const ticket = sequence, onError = error => {if (active(ticket)) fail(error);};
      if (button.dataset.researchBuild) build(button.dataset.researchBuild).catch(onError);
      else if (button.id === 'research-ask') prepareQuestion().catch(onError);
      else if (button.dataset.researchRecipe) { const recipe = recipes[button.dataset.researchRecipe]; if (!recipe) return;
        result = {workspace_id: workspace, title: recipe.title, editable: true, markdown: '# ' + recipe.title + '\n\n' + recipe.steps.map(step => '- [ ] ' + step).join('\n'), notice: 'An editable checklist. No AI request, code execution, search, screening or submission was performed.'}; saved = false; renderOutput(); }
      else if (button.id === 'research-save') save().catch(onError);
      else if (button.id === 'research-download' && result) downloadText(outputMarkdown(), 'Kosh-research.md');
      else if (button.dataset.researchOpen) openDocument(button.dataset.researchOpen).catch(error => notify(error.message, true, true));
      else if (button.dataset.researchNote) selectNote(button.dataset.researchNote).catch(error => notify(error.message, true, true));
      else if (button.dataset.researchRetry) load().catch(fail);
    });
    host.addEventListener('input', event => {
      if (event.target.id === 'research-source-filter') {if (!busy && active()) updateSourcePicker(); return;}
      if (event.target.id !== 'research-preview' || !result?.editable || busy || !active()) return;
      result.markdown = event.target.value; saved = false;
      const button = host.querySelector('#research-save'); button.disabled = false; button.textContent = 'Save as a separate draft';
    });
    host.addEventListener('change', event => {
      if (event.target.dataset.researchSource !== undefined && !busy && active()) updateSourcePicker();
    });
  }
  function render(main) {
    if (!main) return;
    const changed = !page || workspace !== state.workspace;
    if (changed) {
      sequence++; workspace = state.workspace; pageIntent = state.intent;
      result = null; saved = false; overview = null; busy = false; loading = false;
      mount(main);
    } else {
      if (page.parentNode !== main) main.replaceChildren(page);
      if (pageIntent !== state.intent) {
        sequence++; pageIntent = state.intent; loading = false; setBusy(savingResults.has(result));
        if (overview && !result) status.textContent = 'Choose a tool to prepare a new preview. Pending preparation was cancelled by navigation.';
        if (overview) load().catch(fail);
      }
    }
    if (!workspace) {status.textContent = 'Create a workspace first, then add your sources.'; return;}
    if (!overview && !loading) load().catch(fail);
  }
  async function load() {
    const ticket = ++sequence;
    loading = true;
    status.className = 'muted'; status.textContent = 'Loading saved source links…'; if (!overview) host.textContent = '';
    try {
      const response = await request('/research/overview?workspace_id=' + encodeURIComponent(workspace));
      if (!active(ticket)) return;
      overview = response; renderSources(); status.textContent = overview.title + ' · local saved-state view';
    } catch (error) {
      if(state.stopped)return;
      if (active(ticket)) {fail(error); if (!overview) host.innerHTML = '<button class="button" data-research-retry="true">Retry loading source links</button>';}
    } finally {if (ticket === sequence) loading = false;}
  }
  async function build(kind) {
    if (busy || workspace !== state.workspace) return;
    const ids = [...host.querySelectorAll('[data-research-source]:checked')].map(box => box.value);
    if (!ids.length || ids.length > 10) throw new Error('Choose one to ten sources first.');
    const ticket = ++sequence, targetWorkspace = workspace;
    result = null; saved = false; renderOutput(); setBusy(true); status.className = 'muted'; status.textContent = 'Preparing locally…';
    try {
      const response = await request('/research/' + kind, {workspace_id: targetWorkspace, document_ids: ids, ...(kind === 'packet' ? {max_chars: Number(host.querySelector('#research-budget').value)} : {})});
      if (!active(ticket) || targetWorkspace !== state.workspace) return;
      result = response; renderOutput(); status.textContent = 'Prepared for review. Nothing has been saved or sent.';
    } catch (error) {if (active(ticket)) fail(error);}
    finally {if (ticket === sequence) setBusy(false);}
  }
  async function prepareQuestion() {
    if (busy || workspace !== state.workspace) return;
    if (assistState.busy) throw new Error('Wait for the active agent request before preparing another one.');
    const ids = [...host.querySelectorAll('[data-research-source]:checked')].map(box => box.value);
    const question = host.querySelector('#research-question').value.trim(), targetWorkspace = workspace;
    if (!ids.length || ids.length > 10) throw new Error('Choose one to ten sources first.');
    if (!question) throw new Error('Enter a question about those sources first.');
    const ticket = ++sequence;
    setBusy(true);
    try {
      if (!await flushEdits() || targetWorkspace !== state.workspace || !active(ticket)) return;
      assistState.input = {workspace_id: targetWorkspace, task: 'ask', question, document_ids: ids};
      assistState.preview = null; assistState.result = null;
      renderAssist(); document.querySelector('#assist-dialog').showModal();
    } catch (error) {if (active(ticket)) fail(error);}
    finally {if (ticket === sequence) setBusy(false);}
  }
  async function save() {
    if (!result || saved || busy || savingResults.has(result)) return;
    const snapshot = result, body = outputMarkdown(), targetWorkspace = workspace;
    if (targetWorkspace !== state.workspace || snapshot.workspace_id !== targetWorkspace) throw new Error('Workspace changed. Reopen Synthesise.');
    const ticket = ++sequence;
    savingResults.add(snapshot);
    setBusy(true);
    try {
      if (!await flushEdits() || targetWorkspace !== state.workspace || !active(ticket)) return;
      const note = await request('/notes', {workspace_id: targetWorkspace, title: snapshot.title, body});
      replaceNote(note);
      if (state.stopped || snapshot !== result || targetWorkspace !== state.workspace) return;
      saved = true; status.className = 'muted'; status.textContent = 'Saved as a separate draft. Existing writing was retained.';
      renderOutput();
    } catch (error) {
      if(state.stopped)return;
      if (snapshot === result && targetWorkspace === workspace) {status.textContent = error.message; status.className = 'error-text';}
    } finally {savingResults.delete(snapshot); if (snapshot === result) setBusy(false);}
  }
  function downloadText(text, filename) {
    const url = URL.createObjectURL(new Blob([text], {type: 'text/markdown;charset=utf-8'}));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename; document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function saveSearchRecord() {
    const record = discovery.result?.search_record;
    if (!record || record.workspace_id !== state.workspace || discovery.busy) throw new Error('Run a search in this workspace first.');
    if (savedSearches.has(record) || savingSearches.has(record)) return;
    savingSearches.add(record);
    const button = document.querySelector('#save-search-record'); if (button) button.disabled = true;
    const workspaceId = state.workspace;
    try {
      if (!await flushEdits() || workspaceId !== state.workspace) return;
      const note = await request('/notes', {workspace_id: workspaceId, title: record.title, body: record.body});
      replaceNote(note); savedSearches.add(record); if (button?.isConnected) {button.textContent = 'Search record saved'; button.dataset.saved = 'true';}
      notify('Search record saved as a separate draft. It records this bounded search, not a complete literature review.');
    } finally {savingSearches.delete(record); if (button?.isConnected && button.dataset.saved !== 'true') button.disabled = false;}
  }
  function showSearchRecordButton() {
    const form = document.querySelector('#discovery-form'), record = discovery.result?.search_record;
    if (!form || !record || record.workspace_id !== state.workspace || document.querySelector('#save-search-record')) return;
    form.insertAdjacentHTML('afterend', '<p><button type="button" class="button" id="save-search-record" ' + (savedSearches.has(record) ? 'disabled' : '') + '>' + (savedSearches.has(record) ? 'Search record saved' : 'Save this search record') + '</button> <span class="muted small">Keeps the query, date, returned records, index totals and failures as a local draft.</span></p>');
    document.querySelector('#save-search-record').onclick = () => saveSearchRecord().catch(error => notify(error.message, true, true));
  }
  return {render, saveSearchRecord, showSearchRecordButton, recipes};
})();
window.KoshViews?.register({id:'synthesise', title:'Synthesise', render:window.KoshResearch.render});
