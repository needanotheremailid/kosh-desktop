"""Exercise actual native-choice/job UI handlers with an isolated DOM stub."""
from pathlib import Path
import shutil
import subprocess
import unittest


class LocalBackupUI(unittest.TestCase):
    def test_native_selection_cancel_save_preview_and_job_cancel(self):
        root = Path(__file__).resolve().parents[1]
        bundled = root / 'tools/node/node.exe'
        node = str(bundled) if bundled.is_file() else shutil.which('node')
        if not node:
            self.skipTest('Node runtime is required for UI logic checks')
        script = r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const nodes=new Map();
class Element {
 constructor(){this.events={};this.children=[];this.open=false;this.value='';this.checked=false;this.hidden=false;this.textContent='';}
 set innerHTML(value){for(const match of value.matchAll(/id="([^"]+)"/g))nodes.set(match[1],new Element());nodes.set('close',new Element());}
 setAttribute(){} querySelector(selector){return nodes.get(selector==='[data-auto-close]'?'close':selector.slice(1));} querySelectorAll(){return [];}
 append(...items){this.children.push(...items);} replaceChildren(...items){this.children=items;} addEventListener(name,callback){this.events[name]=callback;}
 showModal(){this.open=true;} close(){this.open=false;this.events.close?.();}
}
const context={window:{},document:{createElement:()=>new Element(),querySelector:()=>null,body:{append(){}}},Date,Number,String,Error,setTimeout:callback=>setImmediate(callback),setInterval:()=>1,clearInterval(){}};
vm.createContext(context);vm.runInContext(fs.readFileSync('ui/auto_backup.js','utf8'),context);
let picked={cancelled:true,path:null},starts=0,lastBody,restored=0,previewSlow=false,cancelled=false,pollFailures=0;
const complete=(operation,result)=>({job_id:'a'.repeat(32),operation,state:'complete',phase:'complete',cancellable:false,result,bytes_done:0,bytes_total:null});
context.window.KoshAutoBackup.mount({workspace:()=> 'b'.repeat(32),pendingSummary:()=>({conflicts:1,evidence:0,reviewer:1}),flushEdits:async()=>true,onRestored:async()=>{restored++;},request:async(path,body)=>{
 if(path==='/auto-backup')return {enabled:false,scheduler_alive:true,last_success:null,last_failure:null,last_error:'',clock_warning:'',destination:'',interval_minutes:60,notice:'Saved only',next_due:0};
 if(path==='/auto-backup/sets')return {sets:[],issues:[]};
 if(path==='/local-dialog')return picked;
 if(path==='/local-backup/jobs'){starts++;lastBody=body;if(body.operation==='backup')return complete('backup',{path:'Chosen backup.zip',bytes:99,counts:{revisions:1}});if(previewSlow)return {job_id:'a'.repeat(32),operation:'preview',state:'running',phase:'staging_archive',cancellable:true,bytes_done:10,bytes_total:100};return complete('preview',{preview_id:'c'.repeat(32),title:'Invented restored draft',documents:1,notes:1,revisions:1,history_included:true,sha256:'d'.repeat(64),notice:'Preview only',path:'Chosen backup.zip'});}
 if(path==='/local-backup/cancel'){cancelled=true;return {accepted:true,notice:'Cancellation requested.'};}
 if(path.startsWith('/local-backup/jobs?')){if(pollFailures>0){pollFailures--;throw new Error('Synthetic transient poll failure');}if(!cancelled)return complete('preview',{preview_id:'c'.repeat(32),title:'Invented recovered preview',documents:1,notes:1,revisions:1,history_included:true,sha256:'d'.repeat(64),notice:'Preview only',path:'Chosen backup.zip'});return {job_id:'a'.repeat(32),operation:'preview',state:'cancelled',phase:'cancelled',cancellable:false,error:'Cancelled; existing work retained.',result:null,bytes_done:10,bytes_total:100};}
 if(path==='/local-backup/restore'){assert.equal(body.approve,true);return {workspace_id:'e'.repeat(32)};}
 throw new Error('Unexpected request '+path);
}});
(async()=>{
 await context.window.KoshAutoBackup.saveLocal();assert.equal(starts,0,'Native selection cancellation must do nothing.');
 await context.window.KoshAutoBackup.saveLocal('Typed backup.zip');assert.equal(lastBody.path,'Typed backup.zip');
 picked={cancelled:false,path:'Chosen backup.zip'};
 await context.window.KoshAutoBackup.saveLocal();assert.equal(starts,2);assert.equal(lastBody.operation,'backup');assert.equal(lastBody.include_history,true);assert.match(nodes.get('local-backup-job-status').textContent,/Saved and validated/);assert.match(nodes.get('auto-backup-pending').textContent,/conflicted draft/);
 await context.window.KoshAutoBackup.openLocal();assert.equal(lastBody.operation,'preview');assert.equal(nodes.get('auto-backup-approval').hidden,false);assert.equal(restored,0);
 previewSlow=true;pollFailures=1;const beforeRetry=starts;await context.window.KoshAutoBackup.openLocal();assert.equal(starts,beforeRetry+1,'Polling retries must never repeat the job start.');assert.equal(nodes.get('auto-backup-approval').hidden,false,'A transient failed poll must recover its exact preview.');
 pollFailures=3;await context.window.KoshAutoBackup.openLocal();assert.equal(nodes.get('auto-backup-approval').hidden,true);const beforeResume=starts;assert.equal(nodes.get('local-backup-resume').disabled,false);await nodes.get('local-backup-resume').events.click();assert.equal(starts,beforeResume,'Resume must read the known job, never repeat a write.');assert.equal(nodes.get('auto-backup-approval').hidden,false);
 nodes.get('auto-backup-approve').checked=true;await nodes.get('auto-backup-restore').events.click();assert.equal(restored,1);
 previewSlow=true;const opening=context.window.KoshAutoBackup.openLocal();
 while(nodes.get('local-backup-cancel').disabled)await new Promise(resolve=>setImmediate(resolve));
 await nodes.get('local-backup-cancel').events.click();await opening;assert.equal(cancelled,true);assert.equal(nodes.get('auto-backup-approval').hidden,true);assert.match(nodes.get('auto-backup-error').textContent,/Cancelled/);
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
        result = subprocess.run([node, '-e', script], cwd=root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
