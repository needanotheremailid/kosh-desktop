'use strict';
window.KoshAutoBackup = (() => {
  let hooks, dialog, statusView, busy = false, preview = null, savedSets = [], timer, activeJob = null, trackingInterrupted = false;
  const find = selector => dialog.querySelector(selector);
  const stamp = seconds => seconds === null || seconds === undefined ? 'Never' : new Date(seconds * 1000).toLocaleString();
  const errorText = message => { find('#auto-backup-error').textContent = message || ''; };
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function setBusy(value) {
    busy = value;
    for (const control of dialog.querySelectorAll('input,select,button:not([data-auto-close])')) control.disabled = value;
    find('#auto-backup-restore').disabled = value || !preview || !find('#auto-backup-approve').checked;
    find('#local-backup-cancel').disabled = !activeJob?.cancellable || activeJob.cancel_requested || !['queued','running'].includes(activeJob.state);
    find('#local-backup-resume').disabled = value || !trackingInterrupted || !activeJob;
  }
  function renderPending() {
    const pending = hooks.pendingSummary(), exclusions = [];
    if (pending.conflicts) exclusions.push(pending.conflicts + ' conflicted draft' + (pending.conflicts === 1 ? '' : 's') + ' (browser recovery)');
    if (pending.evidence) exclusions.push(pending.evidence + ' evidence row' + (pending.evidence === 1 ? '' : 's') + ' awaiting Save reviewed row');
    if (pending.reviewer) exclusions.push(pending.reviewer + ' unsaved reviewer comment' + (pending.reviewer === 1 ? '' : 's') + ' (browser recovery)');
    const notice = find('#auto-backup-pending');
    notice.textContent = exclusions.length ? 'Backup contains saved records only. Not included: ' + exclusions.join('; ') + '. Save or preserve these fields separately.' : '';
    notice.hidden = !exclusions.length;
  }
  function renderStatus(status) {
    statusView = status;
    find('#auto-backup-status').textContent = status.running ? 'Backing up saved work…' : status.enabled ? (status.scheduler_alive ? 'Automatic backups enabled' : 'Automatic backups enabled · scheduler is not running') : 'Automatic backups off';
    find('#auto-backup-last-success').textContent = stamp(status.last_success);
    find('#auto-backup-last-failure').textContent = stamp(status.last_failure);
    find('#auto-backup-next').textContent = !status.enabled ? 'Off' : status.next_due <= Date.now() / 1000 ? 'Due while Kosh is open' : stamp(status.next_due);
    find('#auto-backup-last-path').textContent = status.last_set_path || 'No completed automatic backup yet.';
    find('#auto-backup-last-error').textContent = [status.last_error, status.clock_warning].filter(Boolean).join(' ');
    find('#auto-backup-notice').textContent = status.notice;
    renderPending();
    if (!busy && status.active_job) renderJob(status.active_job);
  }
  const phases = {queued:'Queued',starting:'Starting',preparing_backup:'Preparing saved backup',writing_source:'Writing an original',checking_archive:'Checking written ZIP bytes',preparing_preview:'Preparing restore preview',staging_archive:'Staging a verified ZIP',validating_archive:'Validating archive entries',verifying_source:'Verifying an original',reading_source:'Reading an original',extracting_source:'Checking source extraction',saving_validation_text:'Saving temporary validation text',validating_records:'Checking saved records',checking_annotation:'Checking annotation geometry',validating_history:'Checking saved history',preview_ready:'Completing preview',preview_committed:'Completing preview',publishing:'Publishing validated backup',complete:'Complete',failed:'Failed',cancelled:'Cancelled'};
  function renderJob(job) {
    activeJob = job;
    const label = job.operation === 'backup' ? 'Local backup' : job.operation === 'automatic' ? 'All-workspace backup' : 'Restore preview';
    const bytes = Number.isFinite(job.bytes_total) && job.bytes_total > 0 ? ' · ' + (job.bytes_done / 1048576).toFixed(1) + ' / ' + (job.bytes_total / 1048576).toFixed(1) + ' MiB in this phase' : '';
    find('#local-backup-job-status').textContent = label + ': ' + (job.cancel_requested && !['complete','failed','cancelled'].includes(job.state) ? 'Cancellation requested; waiting for the current safe checkpoint' : phases[job.phase] || job.phase) + bytes;
    const progress = find('#local-backup-progress');
    progress.hidden = !bytes;
    if (bytes) progress.value = Math.min(100, Math.floor(job.bytes_done * 100 / job.bytes_total));
    find('#local-backup-cancel').disabled = !job.cancellable || job.cancel_requested || !['queued','running'].includes(job.state);
    find('#local-backup-recovery').textContent = job.recovery_path && ['failed','cancelled'].includes(job.state) ? 'Retained incomplete output: ' + job.recovery_path + ' · ' + (typeof job.retained_bytes === 'number' ? job.retained_bytes + ' known bytes' : 'size unavailable') + '. Existing work is unchanged.' : '';
  }
  async function runJob(body) {
    clearPreview();
    let job = await hooks.request('/local-backup/jobs', body);
    trackingInterrupted = false;
    return waitForJob(job);
  }
  async function waitForJob(job) {
    let failures = 0;
    renderJob(job);
    while (!['complete','failed','cancelled'].includes(job.state)) {
      await new Promise(resolve => setTimeout(resolve, 350));
      try {
        job = await hooks.request('/local-backup/jobs?job_id=' + encodeURIComponent(job.job_id));
        failures = 0;
      } catch (error) {
        if (++failures < 3) continue;
        trackingInterrupted = true;
        throw new Error(error.message + ' Tracking is interrupted; the job may still be running or completed. Use Resume tracking to read this same job. No write was replayed.');
      }
      renderJob(job);
    }
    trackingInterrupted = false;
    if (job.state !== 'complete') throw new Error(job.error || 'Operation did not complete. Existing saved work was retained.');
    return job.result;
  }
  function renderPreview(value) {
    preview = value;
    const details = find('#auto-backup-preview-details');
    details.replaceChildren();
    details.append(element('h4', preview.title));
    details.append(element('p', preview.documents + ' source(s) · ' + preview.notes + ' note(s) · ' + preview.revisions + ' earlier revision(s)'));
    details.append(element('p', preview.history_included ? 'Revision history included.' : 'Revision history excluded.'));
    details.append(element('p', preview.notice, 'muted small'));
    details.append(element('p', 'SHA-256: ' + preview.sha256, 'auto-backup-path'));
    if (preview.path) details.append(element('p', preview.path, 'auto-backup-path'));
    if (preview.unverified_citations) details.append(element('p', preview.unverified_citations + ' earlier citation(s) remain unverified. Review their retained originals after restoring.', 'transformation-warning'));
    find('#auto-backup-approval').hidden = false;
  }
  async function saveLocal(typedPath = null) {
    await open();
    await perform(async () => {
      const workspace = hooks.workspace();
      if (!workspace) throw new Error('Create or choose a workspace first.');
      if (!await hooks.flushEdits()) throw new Error('Pending ordinary edits could not save. Keep this window open and resolve the error first.');
      renderPending();
      if (hooks.workspace() !== workspace) throw new Error('The workspace changed. Choose the workspace again before backing up.');
      const selected = typeof typedPath === 'string' ? {cancelled:false,path:typedPath.trim()} : await hooks.request('/local-dialog', {kind:'backup-save'});
      if (selected.cancelled) return;
      if (!selected.path) throw new Error('Enter a complete local ZIP output path. The parent folder must already exist.');
      const result = await runJob({operation:'backup',workspace_id:workspace,path:selected.path,include_history:true});
      find('#local-backup-job-status').textContent = 'Saved and validated local ZIP: ' + result.path + ' · ' + result.bytes + ' bytes. Revision history included.';
      await refreshStatus();
    });
  }
  async function openLocal(typedPath = null) {
    await open();
    await perform(async () => {
      const selected = typeof typedPath === 'string' ? {cancelled:false,path:typedPath.trim()} : await hooks.request('/local-dialog', {kind:'backup-open'});
      if (selected.cancelled) return;
      if (!selected.path) throw new Error('Enter the complete path of one existing local ZIP.');
      renderPreview(await runJob({operation:'preview',path:selected.path}));
    });
  }
  async function refreshStatus(populate = false) {
    const status = await hooks.request('/auto-backup');
    if (!dialog.open) return;
    renderStatus(status);
    if (populate) {
      find('#auto-backup-enabled').checked = status.enabled;
      find('#auto-backup-destination').value = status.destination;
      find('#auto-backup-interval').value = status.interval_minutes;
    }
  }
  function clearPreview() {
    preview = null;
    find('#auto-backup-preview-details').replaceChildren();
    find('#auto-backup-approve').checked = false;
    find('#auto-backup-approval').hidden = true;
    find('#auto-backup-restore').disabled = true;
  }
  function renderWorkspaces() {
    clearPreview();
    const selected = savedSets.find(item => item.set_id === find('#auto-backup-set').value);
    const workspaces = find('#auto-backup-workspace');
    workspaces.replaceChildren();
    for (const entry of selected?.workspaces || []) {
      const option = element('option', entry.title);
      option.value = entry.workspace_id;
      workspaces.append(option);
    }
    find('#auto-backup-preview').disabled = busy || !selected;
  }
  async function refreshSets() {
    const result = await hooks.request('/auto-backup/sets');
    savedSets = result.sets;
    const select = find('#auto-backup-set');
    select.replaceChildren();
    for (const saved of savedSets) {
      const option = element('option', stamp(saved.created_at) + ' · ' + saved.workspaces.length + ' workspace(s)');
      option.value = saved.set_id;
      select.append(option);
    }
    find('#auto-backup-empty').textContent = result.unavailable ? result.unavailable : !savedSets.length ? 'No completed automatic backup sets in the selected folder.' : '';
    find('#auto-backup-set-issues').textContent = result.issues.length ? result.issues.length + ' set(s) have unreadable manifests and are excluded. Their files are retained.' : '';
    renderWorkspaces();
    await refreshStatus();
  }
  async function perform(task) {
    if (busy) return;
    errorText('');
    setBusy(true);
    try { await task(); }
    catch (error) { errorText(error.message); }
    finally { setBusy(false); find('#auto-backup-preview').disabled = !savedSets.length; }
  }
  async function open() {
    if (!dialog || dialog.open) return;
    document.querySelector('#settings-dialog')?.close();
    document.querySelector('#tools-dialog')?.close();
    dialog.showModal();
    renderPending();
    await perform(async () => { await refreshStatus(true); await refreshSets(); });
    clearInterval(timer);
    timer = setInterval(() => {
      if (dialog.open && !busy) refreshStatus().catch(error => errorText(error.message));
    }, 15000);
  }
  function mount(options) {
    if (dialog) return;
    hooks = options;
    dialog = element('dialog');
    dialog.id = 'auto-backup-dialog';
    dialog.setAttribute('aria-labelledby', 'auto-backup-title');
    dialog.innerHTML = '<div class="dialog-heading"><h2 id="auto-backup-title">Local backup &amp; restore</h2><button class="icon-button" data-auto-close aria-label="Close backup preferences">×</button></div>' +
      '<p>Save a workspace ZIP with history or choose a local ZIP for a read-only restore preview. Large libraries use the same streaming route as automatic backups. ZIPs are unencrypted; existing source, record and manifest bounds still apply.</p><div class="dialog-actions"><button class="button primary" id="local-backup-save">Save workspace ZIP locally</button><button class="button" id="local-backup-open">Choose ZIP &amp; preview restore</button></div><details><summary>Type a local path instead of using a dialog</summary><p class="muted small">Use a complete absolute path. Save needs an existing parent folder and a new .zip filename; restore reads only the named existing ZIP.</p><label for="local-backup-save-path">New local ZIP output path</label><input id="local-backup-save-path" autocomplete="off"><button class="button" id="local-backup-save-typed">Save ZIP at this path</button><label for="local-backup-open-path">Existing local ZIP path</label><input id="local-backup-open-path" autocomplete="off"><button class="button" id="local-backup-open-typed">Preview this ZIP</button></details><p id="local-backup-job-status" role="status" aria-live="polite"></p><progress id="local-backup-progress" max="100" hidden></progress><button class="button" id="local-backup-cancel" disabled>Cancel current operation</button><button class="button" id="local-backup-resume" disabled>Resume tracking</button><p class="muted small">Cancellation stops at a safe checkpoint before publication. A current PDF/image parser must finish first. Approved restore apply runs to completion.</p><p class="auto-backup-path" id="local-backup-recovery"></p><h3>Automatic backup schedule</h3>' +
      '<p>Choose a local folder outside Kosh’s application and data folders. A separate drive provides better protection against loss of this computer. Scheduled backups include every workspace.</p>' +
      '<label class="backup-history"><input id="auto-backup-enabled" type="checkbox"> Enable automatic local backups</label>' +
      '<label for="auto-backup-destination">Existing local backup folder</label><button class="button" id="auto-backup-choose-folder">Choose backup folder</button><input id="auto-backup-destination" autocomplete="off" placeholder="Choose or paste the existing folder path">' +
      '<label for="auto-backup-interval">Interval while Kosh is open · minutes</label><input id="auto-backup-interval" type="number" min="15" max="10080" step="1">' +
      '<p class="muted small">15 minutes to 7 days. Backups catch up when Kosh next opens. No scheduled Windows task is installed; no earlier backup is deleted.</p>' +
      '<div class="dialog-actions"><button class="button" id="auto-backup-save">Save backup preferences</button><button class="button primary" id="auto-backup-run">Back up saved work now</button></div>' +
      '<section class="tool-section"><h3>Status</h3><p id="auto-backup-status" role="status" aria-live="polite">Loading…</p><p id="auto-backup-pending" class="transformation-warning" role="status" aria-live="polite" hidden></p><dl class="auto-backup-facts"><dt>Last success</dt><dd id="auto-backup-last-success">Never</dd><dt>Last failure</dt><dd id="auto-backup-last-failure">Never</dd><dt>Next backup</dt><dd id="auto-backup-next">Off</dd></dl><p class="auto-backup-path" id="auto-backup-last-path"></p><p class="error-text" id="auto-backup-last-error"></p><p class="muted small" id="auto-backup-notice"></p></section>' +
      '<section class="tool-section"><h3>Preview a saved restore</h3><p>Review one workspace from a completed automatic set. Restoring creates a separate workspace.</p><button class="text-button" id="auto-backup-refresh-sets">Refresh backup sets</button><p id="auto-backup-empty" class="muted small"></p><p id="auto-backup-set-issues" class="error-text"></p><label for="auto-backup-set">Backup set</label><select id="auto-backup-set"></select><label for="auto-backup-workspace">Workspace</label><select id="auto-backup-workspace"></select><button class="button" id="auto-backup-preview">Validate restore preview</button><div id="auto-backup-preview-details"></div><label class="backup-history" id="auto-backup-approval" hidden><input type="checkbox" id="auto-backup-approve"> Restore this validated ZIP into a separate workspace.</label><div class="dialog-actions"><button class="button primary" id="auto-backup-restore" disabled>Restore into new workspace</button></div></section><p class="error-text" id="auto-backup-error" role="alert"></p>';
    document.body.append(dialog);
    const settings = document.querySelector('#settings-dialog');
    if (settings) {
      const section = element('section', undefined, 'tool-section');
      section.append(element('h3', 'Local backup'));
      section.append(element('p', 'Opt in to automatic backups of every workspace, including originals and revision history.', 'muted small'));
      const button = element('button', 'Automatic local backups', 'button');
      button.id = 'open-auto-backup';
      button.addEventListener('click', open);
      section.append(button);
      settings.append(section);
    }
    const tools = document.querySelector('#backup-button')?.closest('.tool-section');
    if (tools) {
      const compatibility = element('details');
      compatibility.append(element('summary', 'Portable browser ZIP alternative · 47 MiB limit'));
      for (const node of [...tools.childNodes]) compatibility.append(node);
      tools.append(element('h3', 'Local workspace backup & restore'));
      const save = element('button', 'Save workspace ZIP locally', 'button primary'), restore = element('button', 'Choose ZIP & preview restore', 'button'), preferences = element('button', 'Automatic backup preferences & saved sets', 'button');
      save.addEventListener('click', saveLocal);restore.addEventListener('click', openLocal);preferences.addEventListener('click', open);
      tools.append(save, restore, preferences, element('p', 'Local ZIPs include history, support larger libraries and restore into a separate workspace. Earlier backups remain; no overwrite or pruning.', 'muted small'), compatibility);
    }
    find('[data-auto-close]').addEventListener('click', () => { if (!busy) dialog.close(); else errorText('Wait for completion or use Cancel current operation. Approved restore cannot be interrupted.'); });
    dialog.addEventListener('cancel', event => { if (busy) {event.preventDefault();errorText('Use Cancel current operation, then wait for its safe checkpoint. Approved restore cannot be interrupted.');} });
    dialog.addEventListener('close', () => { clearInterval(timer); clearPreview(); });
    find('#local-backup-save').addEventListener('click', saveLocal);
    find('#local-backup-open').addEventListener('click', openLocal);
    find('#local-backup-save-typed').addEventListener('click', () => saveLocal(find('#local-backup-save-path').value));
    find('#local-backup-open-typed').addEventListener('click', () => openLocal(find('#local-backup-open-path').value));
    find('#local-backup-cancel').addEventListener('click', async () => {
      if (!activeJob?.cancellable) return;
      try {const response = await hooks.request('/local-backup/cancel', {job_id:activeJob.job_id});find('#local-backup-job-status').textContent = response.notice;find('#local-backup-cancel').disabled = true;}
      catch (error) {errorText(error.message);}
    });
    find('#local-backup-resume').addEventListener('click', () => perform(async () => {
      if (!activeJob) return;
      const job = await hooks.request('/local-backup/jobs?job_id=' + encodeURIComponent(activeJob.job_id));
      const result = await waitForJob(job);
      if (job.operation.startsWith('preview')) renderPreview(result);
      else if (job.operation === 'backup') find('#local-backup-job-status').textContent = 'Saved and validated local ZIP: ' + result.path + ' · ' + result.bytes + ' bytes. Revision history included.';
      else await refreshSets();
    }));
    find('#auto-backup-choose-folder').addEventListener('click', () => perform(async () => {const selected=await hooks.request('/local-dialog',{kind:'folder'});if(!selected.cancelled)find('#auto-backup-destination').value=selected.path;}));
    find('#auto-backup-save').addEventListener('click', () => perform(async () => {
      const enabled = find('#auto-backup-enabled').checked;
      if (enabled && !await hooks.flushEdits()) throw new Error('Resolve pending edits before enabling backups. Preferences were not changed.');
      const status = await hooks.request('/auto-backup', {enabled, destination: find('#auto-backup-destination').value.trim(), interval_minutes: Number(find('#auto-backup-interval').value)});
      renderStatus(status);
      find('#auto-backup-destination').value = status.destination;
      clearPreview();
      await refreshSets();
    }));
    find('#auto-backup-run').addEventListener('click', () => perform(async () => {
      if (!statusView?.enabled) throw new Error('Enable automatic backups and save your chosen folder first.');
      if (!await hooks.flushEdits()) throw new Error('Resolve pending edits before backing up saved work.');
      renderPending();
      find('#auto-backup-status').textContent = 'Backing up saved work…';
      await runJob({operation:'automatic'});
      await refreshStatus();
      await refreshSets();
    }));
    find('#auto-backup-refresh-sets').addEventListener('click', () => perform(refreshSets));
    find('#auto-backup-set').addEventListener('change', renderWorkspaces);
    find('#auto-backup-workspace').addEventListener('change', clearPreview);
    find('#auto-backup-preview').addEventListener('click', () => perform(async () => {
      renderPreview(await runJob({operation:'preview-set',set_id:find('#auto-backup-set').value,workspace_id:find('#auto-backup-workspace').value}));
    }));
    find('#auto-backup-approve').addEventListener('change', () => { find('#auto-backup-restore').disabled = busy || !preview || !find('#auto-backup-approve').checked; });
    find('#auto-backup-restore').addEventListener('click', () => perform(async () => {
      if (!preview || !find('#auto-backup-approve').checked) return;
      if (!await hooks.flushEdits()) throw new Error('Resolve pending edits before restoring into a separate workspace.');
      const previewId = preview.preview_id;
      clearPreview();
      find('#local-backup-job-status').textContent='Applying approved restore into a separate workspace. Cancellation is unavailable until this finishes.';
      const result = await hooks.request('/local-backup/restore', {preview_id: previewId, approve: true});
      await hooks.onRestored(result);
      dialog.close();
    }));
  }
  return {mount, open, saveLocal, openLocal};
})();
