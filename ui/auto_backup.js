'use strict';
window.KoshAutoBackup = (() => {
  let hooks, dialog, statusView, busy = false, preview = null, savedSets = [], timer;
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
    find('#auto-backup-empty').textContent = !savedSets.length ? 'No completed automatic backup sets in the selected folder.' : '';
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
    dialog.innerHTML = '<div class="dialog-heading"><h2 id="auto-backup-title">Automatic local backups</h2><button class="icon-button" data-auto-close aria-label="Close backup preferences">×</button></div>' +
      '<p>Choose a local folder outside Kosh’s application and data folders. A separate drive provides better protection against loss of this computer.</p>' +
      '<label class="backup-history"><input id="auto-backup-enabled" type="checkbox"> Enable automatic local backups</label>' +
      '<label for="auto-backup-destination">Existing local backup folder · absolute path</label><input id="auto-backup-destination" autocomplete="off" placeholder="Paste the folder path you choose">' +
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
    const tools = document.querySelector('#tools-dialog .backup-actions');
    if (tools) {
      const button = element('button', 'Automatic backup preferences & restore', 'button');
      button.addEventListener('click', open);
      tools.append(button);
    }
    find('[data-auto-close]').addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', () => { clearInterval(timer); clearPreview(); });
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
      const result = await hooks.request('/auto-backup/run', {});
      await refreshStatus();
      await refreshSets();
      if (!result.ok) throw new Error(result.error);
    }));
    find('#auto-backup-refresh-sets').addEventListener('click', () => perform(refreshSets));
    find('#auto-backup-set').addEventListener('change', renderWorkspaces);
    find('#auto-backup-workspace').addEventListener('change', clearPreview);
    find('#auto-backup-preview').addEventListener('click', () => perform(async () => {
      clearPreview();
      preview = await hooks.request('/auto-backup/preview', {set_id: find('#auto-backup-set').value, workspace_id: find('#auto-backup-workspace').value});
      const details = find('#auto-backup-preview-details');
      details.append(element('h4', preview.title));
      details.append(element('p', preview.documents + ' source(s) · ' + preview.notes + ' note(s) · ' + preview.revisions + ' earlier revision(s)'));
      details.append(element('p', preview.history_included ? 'Revision history included.' : 'Revision history excluded.'));
      details.append(element('p', preview.notice, 'muted small'));
      details.append(element('p', 'SHA-256: ' + preview.sha256, 'auto-backup-path'));
      if (preview.unverified_citations) details.append(element('p', preview.unverified_citations + ' earlier citation(s) remain unverified. Review their retained originals after restoring.', 'transformation-warning'));
      find('#auto-backup-approval').hidden = false;
    }));
    find('#auto-backup-approve').addEventListener('change', () => { find('#auto-backup-restore').disabled = busy || !preview || !find('#auto-backup-approve').checked; });
    find('#auto-backup-restore').addEventListener('click', () => perform(async () => {
      if (!preview || !find('#auto-backup-approve').checked) return;
      if (!await hooks.flushEdits()) throw new Error('Resolve pending edits before restoring into a separate workspace.');
      const previewId = preview.preview_id;
      clearPreview();
      const result = await hooks.request('/auto-backup/restore', {preview_id: previewId, approve: true});
      await hooks.onRestored(result);
      dialog.close();
    }));
  }
  return {mount, open};
})();
