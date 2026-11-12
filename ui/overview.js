'use strict';

/* Workspace progress is derived from saved records, never from a completion flag. */
window.KoshOverview = (() => {
  const readingErrors = new Map();
  let loadingWorkspace = null;

  function counts(data, workspaceId, reading = null) {
    const result = {sources:0,catalogue:0,imported:0,reading:null,evidenceRows:0,evidenceSources:0,drafts:0,citations:0,citedSources:0,claims:null};
    if (!workspaceId) return result;
    const sources = data.documents.filter(source => source.workspace_id === workspaceId && !source.archived);
    const drafts = data.notes.filter(note => note.workspace_id === workspaceId);
    const rows = data.matrix.filter(row => row.workspace_id === workspaceId);
    const imported = sources.filter(source => source.kind !== 'catalogue' && !source.metadata?.catalogue_source);
    const sourceIds = new Set(sources.map(source => source.id));
    result.sources = sources.length;
    result.imported = imported.length;
    result.catalogue = sources.length - imported.length;
    result.evidenceRows = rows.length;
    result.evidenceSources = new Set(rows.filter(row => sourceIds.has(row.document_id)).map(row => row.document_id)).size;
    result.drafts = drafts.length;
    const citedSources = new Set();
    for (const note of drafts) {
      for (const citation of draftCitationEntries(note.body || '', data.documents, workspaceId)) {
        result.citations += citation.count;
        if (citation.valid) citedSources.add(citation.doc.id);
      }
    }
    result.citedSources = citedSources.size;
    if (reading?.workspace_id !== workspaceId) return result;
    const readingSources = new Map(reading.sources.map(source => [source.document_id, source]));
    result.reading = {unread:0,reading:0,read:0};
    for (const source of imported) {
      const status = readingSources.get(source.id)?.status || 'unread';
      result.reading[status]++;
    }
    result.claims = {total:0,needsSource:0,attached:0,checked:0,stale:0};
    const draftById = new Map(drafts.map(note => [note.id, note]));
    for (const claim of reading.claims) {
      const note = draftById.get(claim.note_id);
      if (claim.archived || !note) continue;
      result.claims.total++;
      const stale = !!claim.stale || claim.note_version !== note.version || !(note.body || '').includes(claim.claim_anchor);
      if (stale) result.claims.stale++;
      if (claim.status === 'needs_source') result.claims.needsSource++;
      if (claim.status === 'attached') result.claims.attached++;
      if (claim.status === 'checked' && !stale) result.claims.checked++;
    }
    return result;
  }

  const quantity = (count, singular, plural = singular + 's') => count + ' ' + (count === 1 ? singular : plural);
  const registered = id => ['discover','read','evidence','write'].includes(id) || window.KoshViews.has(id);
  function viewButton(id, label) {
    return '<button class="button" data-view="' + escapeHTML(id) + '"' + (registered(id) ? '' : ' disabled') + '>' + escapeHTML(label) + '</button>';
  }
  function row(id, title, description, progress) {
    return '<li class="overview-step"><div class="overview-step-copy"><h2>' + escapeHTML(title) + '</h2><p>' + escapeHTML(description) + '</p><p class="overview-progress small">' + escapeHTML(progress) + '</p></div>' + viewButton(id, 'Open ' + title) + '</li>';
  }
  function nextAction() {
    const step = nextStep();
    if (!step) return '';
    const unavailable = step.view && !registered(step.view);
    const button = step.label ? '<button class="button" ' + (step.view ? 'data-view="' + escapeHTML(step.view) + '"' : 'data-action="' + escapeHTML(step.action) + '"') + (unavailable ? ' disabled' : '') + '>' + escapeHTML(step.label) + '</button>' : '';
    return '<section class="overview-next" aria-label="Suggested next action"><div><h2>Do this next</h2><p>' + escapeHTML(step.text) + (unavailable ? ' This step is not available yet.' : '') + '</p></div>' + button + '</section>';
  }
  function render(main) {
    if (!state.workspace) {
      main.innerHTML = headline('Overview', 'Keep one project\u2019s sources, evidence and writing together.') + '<section class="overview-start"><h2>Create a workspace</h2><p>A workspace holds the sources and drafts for one project.</p><button class="button primary" data-action="create-workspace">Create a workspace</button></section>';
      return;
    }
    const workspaceId = state.workspace;
    const reading = typeof KoshReading !== 'undefined' ? KoshReading.current() : null;
    const progress = counts(state.data, workspaceId, reading);
    const readingError = readingErrors.get(workspaceId);
    let screen = 'Not started';
    // A later Screen module supplies its own workspace-scoped summary.
    if (window.KoshScreening && typeof window.KoshScreening.counts === 'function') {
      const flow = window.KoshScreening.counts(workspaceId);
      if (flow && Number.isInteger(flow.included) && Number.isInteger(flow.undecided)) screen = quantity(flow.included, 'included source') + ' \u00b7 ' + quantity(flow.undecided, 'undecided source');
    }
    const read = progress.reading ? quantity(progress.reading.unread, 'unread source') + ' \u00b7 ' + progress.reading.reading + ' reading \u00b7 ' + progress.reading.read + ' read' : readingError ? 'Saved reading status could not load.' : typeof KoshReading !== 'undefined' ? 'Loading saved reading status\u2026' : 'Saved reading status is not loaded.';
    const claims = progress.claims;
    const verify = quantity(progress.citations, 'citation marker') + ' in saved drafts' + (claims ? ' \u00b7 ' + quantity(claims.total, 'claim link') + ': ' + claims.needsSource + ' need source, ' + claims.attached + ' attached, ' + claims.checked + ' checked by you, ' + claims.stale + ' stale' : ' \u00b7 claim links are not loaded');
    main.innerHTML = headline('Overview', 'Follow your research from finding sources to checking the final draft.') + nextAction() +
      '<ol class="overview-path" aria-label="Research path">' +
      row('discover', 'Find', 'Search indexes, look up references or import source files.', quantity(progress.sources, 'active source') + ' \u00b7 ' + progress.catalogue + ' reference only \u00b7 ' + progress.imported + ' imported') +
      row('screen', 'Screen', 'Decide which sources belong in this project.', screen + (registered('screen') ? '' : ' \u00b7 Screen is not available yet')) +
      row('read', 'Read', 'Read the original and save useful passages.', read) +
      row('evidence', 'Extract', 'Record the question, design, findings and limitations.', quantity(progress.evidenceRows, 'saved evidence row') + ' \u00b7 ' + quantity(progress.evidenceSources, 'active source') + ' represented') +
      row('synthesise', 'Synthesise', 'Compare sources and prepare a reading packet or checklist.', quantity(progress.evidenceSources, 'active source') + ' with saved evidence to compare') +
      row('write', 'Write', 'Develop your draft with citations beside the source.', quantity(progress.drafts, 'saved note or draft', 'saved notes and drafts')) +
      row('verify', 'Verify', 'Check citations and claim links against the originals.', verify + (registered('verify') ? '' : ' \u00b7 Verify is not available yet')) +
      '</ol><p class="overview-footnote small muted">Counts describe saved records in this workspace. A read status, attached source or checked link does not certify the science.</p>' +
      (readingError ? '<p class="overview-load-error small" role="status">' + escapeHTML(readingError) + ' <button class="text-button" data-overview-retry>Retry reading status</button></p>' : '');
    const retry = main.querySelector('[data-overview-retry]');
    if (retry) retry.addEventListener('click', () => {readingErrors.delete(workspaceId); render(main);});
    if (!reading && !readingError && typeof KoshReading !== 'undefined' && loadingWorkspace !== workspaceId) {
      loadingWorkspace = workspaceId;
      KoshReading.load().then(() => {
        if (state.workspace === workspaceId && state.view === 'overview' && !state.stopped) render(main);
      }).catch(error => {
        readingErrors.set(workspaceId, error.message);
        if (state.workspace === workspaceId && state.view === 'overview' && !state.stopped) render(main);
      }).finally(() => {if (loadingWorkspace === workspaceId) loadingWorkspace = null;});
    }
  }
  window.KoshViews.register({id:'overview',title:'Overview',subtitle:'Where this project stands',render});
  return {counts};
})();
