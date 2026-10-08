/* Integrations that depend on the app and optional workflow modules. */
document.querySelector('#help-dialog .help-grid').insertAdjacentHTML('beforeend','<section><h3>Project review &amp; reviewer responses</h3><p>Open More → Project review to save and inspect every draft in the selected workspace. Counts come from recorded claim reviews and saved reference checks. Unknown means a check failed; zero recorded reviews does not mean the claims were checked.</p><p>More → Reviewer responses links a comment to an exact saved passage. Keep planned wording, revised wording and your response separately. Save manuscript changes in Write; this record never edits the draft. Changed passages show a stale link. Relink explicitly and export a response letter after reviewing its saved records.</p></section><section><h3>Automatic backups &amp; updates</h3><p>Settings → Automatic local backups lets you choose an existing folder and interval. Runs include every workspace and history, only while Kosh is open, with catch-up at next launch. Earlier backups are retained. Browser-only unsaved recovery is separate. Validate a restore preview before restoring into a new workspace.</p><p>Settings → Kosh updates contacts the public release source only when you choose Check. Download and installation are separate actions. The checksum checks transfer integrity; the installer remains unsigned. Installation waits for this window to close, preserves the old installation/data, checks the new startup, then updates shortcuts. Later edits in the new copy are not copied back to the previous installation.</p></section>');
Object.assign(explanations,{
 'note-compare':'Compare two saved manuscript versions side by side. Pending edits are saved first; comparison never changes your manuscript.',
 'open-project-review':'Check saved drafts and recorded claim reviews across this workspace. Failed checks stay unknown; this is not a submission verdict.',
 'open-reviewer-responses':'Link reviewer comments to saved passages, retain responses and changes, then export a response letter. Manuscripts are never changed here.',
 'auto-backup-enabled':'Opt in to backups while Kosh is running. Previous backups are retained; browser-only unsaved drafts are separate.',
 'auto-backup-preview':'Validate the chosen saved ZIP and review its contents before creating a separate restored workspace.',
});
document.querySelector('#help-dialog .help-grid').insertAdjacentHTML('beforeend','<section><h3>Compare saved revisions</h3><p>In Write, choose Compare revisions. Pending edits are saved first. Pick two saved versions to see aligned additions, deletions and unchanged text. Load earlier versions when needed; previous and next change controls move between changed passages. Long comparisons use labelled coarse alignment and pages so the app stays responsive. Comparison is read-only. Use the separate Revision history control when you deliberately want to restore an earlier body as a new save.</p></section>');
KoshAutoBackup.mount({request,flushEdits,pendingSummary:()=>({
 conflicts:conflictedEditors().length,
 evidence:state.matrixReview&&state.matrixDirty?1:0,
 reviewer:typeof KoshReviewer.pendingCount==='function'?KoshReviewer.pendingCount():0,
}),onRestored:async result=>{
 await refresh();state.workspace=result.workspace_id;state.note=null;state.doc=null;state.matrixEdit=null;state.view='library';render();
 notify('Restored into a separate workspace: '+result.title+(result.unverified_citations?' · Earlier unverified citations need review.':''),!!result.unverified_citations,true);
}});
const healthSummary=document.createElement('p');healthSummary.className='small muted';healthSummary.setAttribute('role','status');
document.querySelector('#settings-dialog').append(healthSummary);
document.querySelector('#settings-dialog').addEventListener('toggle',async()=>{
 if(!document.querySelector('#settings-dialog').open)return;
 healthSummary.textContent='Reading local backup status…';
 try{const backup=await request('/auto-backup');healthSummary.textContent=(backup.enabled?'Automatic backups on. ':'Automatic backups off. ')+(backup.last_error?'Last attempt needs attention: '+backup.last_error:backup.last_success?'Last successful set: '+new Date(backup.last_success*1000).toLocaleString()+'.':'No successful automatic backup recorded.')+' Open Project review from More for manuscript checks.';}
 catch(error){healthSummary.textContent='Backup status unavailable: '+error.message;}
 applyHints();KoshUpdater.refresh();
});
const updateHost=document.createElement('div');
document.querySelector('#settings-dialog').append(updateHost);
KoshUpdater.mount(updateHost,{request,beforeInstall:async()=>{
 if(state.loading||state.askBusy||assistState.busy||discovery.busy||folderState.busy){notify('Wait for the active import, search or agent request before installing.',true);return false;}
 if(state.matrixReview&&state.matrixDirty){notify('Save the reviewed evidence row before installing.',true,true);return false;}
 if(!await flushEdits())return false;
 if(conflictedEditors().length){notify('Resolve draft conflicts before installing. Your alternatives remain in browser recovery.',true,true);return false;}
 return true;
},afterInstall:async()=>{
 document.querySelector('#workspace-status').textContent='Update prepared · close this Kosh window';
 notify('Saved work is ready. Close this Kosh window now so the update can copy its browser recovery and check the new version.',false,true);
}});
applyHints();
