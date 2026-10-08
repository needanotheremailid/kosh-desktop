'use strict';

// Exact saved writing only. No restoration, manuscript assignment or HTML preview.
const KoshRevisions=(()=>{
 const PAGE_ROWS=200,CELL_LIMIT=1_000_000;
 const model={epoch:0,comparisonSeq:0,target:null,records:new Map(),bodies:new Map(),cursor:null,listBusy:false,comparison:null,page:0,change:-1,trigger:null};
 const q=id=>document.querySelector('#'+id);
 const node=(tag,className='',text)=>{const element=document.createElement(tag);if(className)element.className=className;if(text!==undefined)element.textContent=String(text);return element;};
 const lines=text=>text.match(/[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+$/g)||[];
 function lineEnding(text){return text.endsWith('\r\n')?'CRLF':text.endsWith('\n')?'LF':text.endsWith('\r')?'CR':'No newline';}

 function diff(leftText,rightText,{maxCells=CELL_LIMIT}={}){
  const a=lines(leftText),b=lines(rightText),rows=[],blocks=[];let prefix=0,suffix=0,removed=0,added=0;
  while(prefix<a.length&&prefix<b.length&&a[prefix]===b[prefix])prefix++;
  while(suffix<a.length-prefix&&suffix<b.length-prefix&&a[a.length-1-suffix]===b[b.length-1-suffix])suffix++;
  for(let index=0;index<prefix;index++)rows.push({kind:'same',left:{number:index+1,text:a[index]},right:{number:index+1,text:b[index]}});
  const n=a.length-prefix-suffix,m=b.length-prefix-suffix,coarse=!!(n&&m&&(n+1)*(m+1)>maxCells);
  let deletions=[],insertions=[];
  function flush(){if(!deletions.length&&!insertions.length)return;const start=rows.length;removed+=deletions.length;added+=insertions.length;for(let index=0;index<Math.max(deletions.length,insertions.length);index++)rows.push({kind:deletions[index]&&insertions[index]?'change':deletions[index]?'delete':'add',left:deletions[index]||null,right:insertions[index]||null});blocks.push({start,end:rows.length-1,removed:deletions.length,added:insertions.length,coarse});deletions=[];insertions=[];}
  if(coarse){for(let index=0;index<n;index++)deletions.push({number:prefix+index+1,text:a[prefix+index]});for(let index=0;index<m;index++)insertions.push({number:prefix+index+1,text:b[prefix+index]});flush();}
  else{
   const width=m+1,table=new Uint32Array((n+1)*width);
   for(let i=n-1;i>=0;i--)for(let j=m-1;j>=0;j--)table[i*width+j]=a[prefix+i]===b[prefix+j]?1+table[(i+1)*width+j+1]:Math.max(table[(i+1)*width+j],table[i*width+j+1]);
   let i=0,j=0;
   while(i<n||j<m){if(i<n&&j<m&&a[prefix+i]===b[prefix+j]){flush();rows.push({kind:'same',left:{number:prefix+i+1,text:a[prefix+i]},right:{number:prefix+j+1,text:b[prefix+j]}});i++;j++;}else if(i<n&&(j===m||table[(i+1)*width+j]>=table[i*width+j+1])){deletions.push({number:prefix+i+1,text:a[prefix+i++]});}else{insertions.push({number:prefix+j+1,text:b[prefix+j++]});}}
   flush();
  }
  for(let index=suffix;index>0;index--)rows.push({kind:'same',left:{number:a.length-index+1,text:a[a.length-index]},right:{number:b.length-index+1,text:b[b.length-index]}});
  return {rows,blocks,removed,added,coarse};
 }
 function compare(left,right){const body=diff(left.body,right.body),titleChanged=left.title!==right.title,blocks=titleChanged?[{id:'revision-title-block',title:true}]:[];for(const block of body.blocks)blocks.push({...block,id:'revision-block-'+block.start,title:false});return {left,right,body,titleChanged,blocks};}
 function current(target=model.target){if(typeof state==='undefined'||typeof activeEditor!=='function'||!target)return false;const editor=activeEditor();return state.workspace===target.workspace&&state.note===target.id&&editor?.id===target.id&&editor.workspace_id===target.workspace&&!editor.dirty&&!editor.conflict&&editor.version===target.version&&editor.revision===target.revision&&editor.title===target.title&&editor.body===target.body;}
 function assertCurrent(){if(!current())throw new Error('The draft or workspace changed. Pending edits remain in writing recovery. Save or reload the current draft, then reopen comparison.');}
 function status(message,error=false){q('revision-status').textContent=message;q('revision-status').classList.toggle('error-text',error);}
 function clearComparison(){model.comparison=null;model.change=-1;q('revision-title-block').replaceChildren();q('revision-rows').replaceChildren();q('revision-summary').textContent='';q('revision-warning').textContent='';q('revision-page-status').textContent='';q('revision-navigation-status').textContent='';for(const id of ['revision-prev-change','revision-next-change','revision-prev-page','revision-next-page','revision-pages'])q(id).disabled=true;}
 function showError(error){clearComparison();status(error.message||String(error),true);q('revision-status').focus();}
 function button(id,text,action){const element=node('button','button',text);element.id=id;element.type='button';element.addEventListener('click',action);return element;}
 function label(text,element){const wrapper=node('label','',text);wrapper.htmlFor=element.id;wrapper.append(element);return wrapper;}
 function close(){model.epoch++;q('revision-compare-dialog').close();}
 function mount(){
  if(q('revision-compare-dialog'))return;
  const dialog=node('dialog','revision-compare-dialog');dialog.id='revision-compare-dialog';dialog.setAttribute('aria-labelledby','revision-heading');
  const header=node('header','revision-heading'),heading=node('h2','','Compare saved revisions');heading.id='revision-heading';header.append(heading,button('revision-close','Close',close));dialog.append(header);
  const scope=node('p','muted small');scope.id='revision-scope';dialog.append(scope);
  const live=node('p','muted small');live.id='revision-status';live.setAttribute('role','status');live.tabIndex=-1;dialog.append(live);
  const controls=node('div','revision-controls'),from=node('select'),to=node('select');from.id='revision-from';to.id='revision-to';from.disabled=true;to.disabled=true;from.addEventListener('change',()=>loadComparison());to.addEventListener('change',()=>loadComparison());
  controls.append(label('Compare from',from),label('Compare to',to),button('revision-refresh','Save & refresh',()=>open()),button('revision-load-earlier','Load earlier versions',()=>loadEarlier()));dialog.append(controls);
  const navigation=node('div','revision-navigation');navigation.append(button('revision-prev-change','Previous change',()=>navigate(-1)),button('revision-next-change','Next change',()=>navigate(1)));const position=node('span','muted small');position.id='revision-navigation-status';position.setAttribute('role','status');navigation.append(position);dialog.append(navigation);
  const summary=node('p','small');summary.id='revision-summary';dialog.append(summary);const warning=node('p','revision-warning small');warning.id='revision-warning';dialog.append(warning);
  const title=node('section','revision-title-block');title.id='revision-title-block';title.tabIndex=-1;title.setAttribute('aria-label','Saved titles');dialog.append(title);
  const columns=node('div','revision-column-headings');const left=node('h3'),right=node('h3');left.id='revision-left-heading';right.id='revision-right-heading';columns.append(left,right);dialog.append(columns);
  const scroll=node('div','revision-scroll'),rows=node('div','revision-rows');rows.id='revision-rows';scroll.append(rows);dialog.append(scroll);
  const pages=node('div','revision-pagination');pages.append(button('revision-prev-page','Previous rows',()=>pageBy(-1)));const pageSelect=node('select');pageSelect.id='revision-pages';pageSelect.setAttribute('aria-label','Displayed rows');pageSelect.addEventListener('change',()=>renderPage(Number(pageSelect.value)));pages.append(pageSelect,button('revision-next-page','Next rows',()=>pageBy(1)));const pageStatus=node('span','muted small');pageStatus.id='revision-page-status';pages.append(pageStatus);dialog.append(pages);
  dialog.append(node('p','muted small','Saved title and Markdown text only. Unsaved alternatives are excluded. This comparison has no restore or overwrite action.'));
  dialog.addEventListener('cancel',()=>{model.epoch++;});dialog.addEventListener('close',()=>{model.epoch++;model.target=null;const trigger=model.trigger?.isConnected!==false?model.trigger:null;(trigger||document.querySelector('[data-action="note-compare"]'))?.focus();});document.body.append(dialog);clearComparison();
 }
 function envelope(result,target,withBody=false,version=null){
  if(!result||result.note_id!==target.id||result.workspace_id!==target.workspace||result.current_version!==target.version||!Array.isArray(result.revisions)||result.revisions.length>100)throw new Error('Saved revision response does not match this draft and version. Reopen comparison.');
  if(withBody&&(result.revisions.length!==1||result.revisions[0].version!==version))throw new Error('The requested saved revision was not returned.');
  const seen=new Set();for(const row of result.revisions){if(row.id!==target.id||!Number.isInteger(row.version)||row.version<1||row.version>target.version||seen.has(row.version)||typeof row.title!=='string'||typeof row.created_at!=='string'||withBody&&typeof row.body!=='string')throw new Error('Saved revision metadata is invalid. No comparison was rendered.');seen.add(row.version);}
  if(result.next_before!==null&&(!Number.isInteger(result.next_before)||result.next_before<1))throw new Error('Saved revision paging cursor is invalid.');return result;
 }
 function historyPath(target,suffix){return '/notes/history?id='+encodeURIComponent(target.id)+'&workspace_id='+encodeURIComponent(target.workspace)+'&expected_version='+target.version+'&'+suffix;}
 function fillSelectors(preserve=false){const oldFrom=q('revision-from').value,oldTo=q('revision-to').value,records=[...model.records.values()].sort((a,b)=>b.version-a.version);for(const id of ['revision-from','revision-to']){q(id).replaceChildren();for(const row of records){const option=node('option','', 'Version '+row.version+(row.version===model.target.version?' · Saved current':' · Past save')+' · '+row.created_at);option.value=String(row.version);q(id).append(option);}q(id).disabled=!records.length;}
  q('revision-from').value=preserve&&model.records.has(Number(oldFrom))?oldFrom:String(records[1]?.version??records[0]?.version??'');q('revision-to').value=preserve&&model.records.has(Number(oldTo))?oldTo:String(records[0]?.version??'');q('revision-load-earlier').hidden=model.cursor===null;q('revision-load-earlier').disabled=model.listBusy||model.cursor===null;
 }
 async function open(){
  mount();const dialog=q('revision-compare-dialog');if(!dialog.open){model.trigger=document.activeElement;dialog.showModal();}const epoch=++model.epoch;model.target=null;model.records.clear();model.bodies.clear();model.cursor=null;model.listBusy=false;clearComparison();q('revision-from').disabled=true;q('revision-to').disabled=true;q('revision-load-earlier').hidden=true;q('revision-refresh').disabled=true;q('revision-scope').textContent='Selected draft · saved versions only';status('Saving ordinary pending edits before loading saved versions…');
  try{
   const editor=typeof activeEditor==='function'?activeEditor():null;if(typeof state==='undefined'||!editor||editor.workspace_id!==state.workspace)throw new Error('Open a saved draft in Write before comparing revisions.');if(editor.conflict)throw new Error('Resolve this draft conflict first. Its unsaved alternative remains in writing recovery.');const id=editor.id,workspace=state.workspace;
   if(typeof flushEdits!=='function'||!await flushEdits())throw new Error('Draft edits could not be saved. They remain in writing recovery; comparison was not loaded.');if(epoch!==model.epoch||!dialog.open)return;
   const saved=activeEditor();if(state.workspace!==workspace||state.note!==id||saved?.id!==id||saved.dirty||saved.conflict)throw new Error('The selected draft changed or still has pending edits. Reopen its saved comparison.');model.target={id,workspace,version:saved.version,title:saved.title,body:saved.body,revision:saved.revision};const target=model.target;
   const result=envelope(await request(historyPath(target,'metadata_only=1')),target);if(epoch!==model.epoch||!dialog.open)return;assertCurrent();for(const row of result.revisions)model.records.set(row.version,row);model.cursor=result.next_before;fillSelectors();q('revision-scope').textContent=(target.title||'Untitled draft')+' · compared saved versions; unsaved alternatives excluded';
   if(!model.records.size){status('No saved versions returned. Save the draft and refresh.');return;}await loadComparison();if(epoch===model.epoch&&dialog.open&&model.comparison)q('revision-from').focus();
  }catch(error){if(epoch===model.epoch&&dialog.open)showError(error);}finally{if(epoch===model.epoch)q('revision-refresh').disabled=false;}
 }
 async function loadEarlier(){if(model.listBusy||model.cursor===null)return;const epoch=model.epoch,target=model.target,before=model.cursor;try{assertCurrent();model.listBusy=true;q('revision-load-earlier').disabled=true;status('Loading earlier saved-version labels…');const result=envelope(await request(historyPath(target,'metadata_only=1&before='+before)),target);if(epoch!==model.epoch||!q('revision-compare-dialog').open)return;assertCurrent();if(result.revisions.some(row=>row.version>=before)||result.next_before!==null&&result.next_before>=before)throw new Error('Earlier revision page did not advance. No duplicate metadata was added.');for(const row of result.revisions)model.records.set(row.version,row);model.cursor=result.next_before;fillSelectors(true);status(model.records.size+' saved-version labels loaded. Selected comparison is unchanged.');}catch(error){if(epoch===model.epoch&&q('revision-compare-dialog').open)showError(error);}finally{if(epoch===model.epoch){model.listBusy=false;q('revision-load-earlier').disabled=model.cursor===null;q('revision-load-earlier').hidden=model.cursor===null;if(q('revision-load-earlier').hidden)q('revision-from').focus();else q('revision-load-earlier').focus();}}}
 async function body(target,version){if(model.bodies.has(version))return model.bodies.get(version);const result=envelope(await request(historyPath(target,'version='+version)),target,true,version),record=result.revisions[0];if(record.title!==model.records.get(version)?.title)throw new Error('Saved revision title changed between requests. Reopen comparison.');return record;}
 async function loadComparison(){
  const epoch=model.epoch,sequence=++model.comparisonSeq,target=model.target,leftVersion=Number(q('revision-from').value),rightVersion=Number(q('revision-to').value);
  clearComparison();status('Loading the two selected saved versions…');
  try{
   assertCurrent();
   if(!model.records.has(leftVersion)||!model.records.has(rightVersion))throw new Error('Choose two loaded saved-version labels.');
   let values;
   if(leftVersion===rightVersion){const selected=await body(target,leftVersion);values=[selected,selected];}
   else values=await Promise.all([body(target,leftVersion),body(target,rightVersion)]);
   if(epoch!==model.epoch||sequence!==model.comparisonSeq||!q('revision-compare-dialog').open)return;
   assertCurrent();
   if(values.some(row=>row.version===target.version&&(row.body!==target.body||row.title!==target.title)))throw new Error('The current saved text differs from this editor snapshot. Reload the saved draft before comparing.');
   model.bodies=new Map(values.map(row=>[row.version,row]));model.comparison=compare(values[0],values[1]);model.page=0;model.change=-1;renderComparison();
   status(leftVersion===rightVersion?(model.records.size===1?'Only Saved current is available. Another saved revision is needed to compare changes.':'Same saved version selected. Choose two different versions to compare changes.'):'Compared exact saved versions '+leftVersion+' and '+rightVersion+'.');
  }catch(error){if(epoch===model.epoch&&sequence===model.comparisonSeq&&q('revision-compare-dialog').open)showError(error);}
 }
 function textCell(line,side,changed){const cell=node('div','revision-cell'+(changed?' revision-cell-'+(side==='left'?'removed':'added'):''));if(!line){cell.append(node('span','muted small','No corresponding line'));return cell;}cell.append(node('div','revision-line-label small',(changed?(side==='left'?'− Removed':'＋ Added'):'Unchanged')+' · line '+line.number+' · '+lineEnding(line.text)));cell.append(node('pre','revision-text',line.text));return cell;}
 function renderComparison(){const comparison=model.comparison,{left,right,body}=comparison;q('revision-left-heading').textContent='From version '+left.version+(left.version===model.target.version?' · Saved current':' · Past save');q('revision-right-heading').textContent='To version '+right.version+(right.version===model.target.version?' · Saved current':' · Past save');q('revision-summary').textContent=body.removed+' body lines removed · '+body.added+' body lines added · '+comparison.blocks.length+' changed blocks'+(comparison.titleChanged?' · title changed':' · title unchanged');q('revision-warning').textContent=body.coarse?'Coarse alignment for a large replacement block: lines are paired by position inside that block. Full text is retained across the row pages below.':'Line endings are compared exactly. LF, CRLF and a missing final newline remain visible changes.';
  const title=q('revision-title-block');title.replaceChildren(node('h3','','Saved titles'));const titleColumns=node('div','revision-title-columns');titleColumns.append(textCell({number:1,text:left.title},'left',comparison.titleChanged),textCell({number:1,text:right.title},'right',comparison.titleChanged));title.append(titleColumns);title.classList.toggle('revision-changed-title',comparison.titleChanged);
  const pages=q('revision-pages');pages.replaceChildren();for(let index=0;index<Math.max(1,Math.ceil(body.rows.length/PAGE_ROWS));index++){const option=node('option','',body.rows.length?'Rows '+(index*PAGE_ROWS+1)+'–'+Math.min(body.rows.length,(index+1)*PAGE_ROWS):'No body rows');option.value=String(index);pages.append(option);}pages.disabled=body.rows.length<=PAGE_ROWS;q('revision-prev-change').disabled=!comparison.blocks.length;q('revision-next-change').disabled=!comparison.blocks.length;renderPage(0);
 }
 function renderPage(page){try{assertCurrent();if(!model.comparison)return;const body=model.comparison.body,count=Math.max(1,Math.ceil(body.rows.length/PAGE_ROWS));if(!Number.isInteger(page)||page<0||page>=count)return;model.page=page;const rows=q('revision-rows');rows.replaceChildren();const start=page*PAGE_ROWS,end=Math.min(body.rows.length,start+PAGE_ROWS),starts=new Map(body.blocks.map(block=>[block.start,block]));
   for(let index=start;index<end;index++){const row=body.rows[index],element=node('div','revision-row'+(row.kind==='same'?'':' revision-row-changed'));if(starts.has(index)){element.id='revision-block-'+index;element.tabIndex=-1;}element.append(textCell(row.left,'left',row.kind!=='same'),textCell(row.right,'right',row.kind!=='same'));rows.append(element);}if(!body.rows.length)rows.append(node('p','muted','Both saved bodies are empty.'));q('revision-pages').value=String(page);q('revision-prev-page').disabled=page===0;q('revision-next-page').disabled=page===count-1;q('revision-page-status').textContent=body.rows.length?'Rows '+(start+1)+'–'+end+' of '+body.rows.length+'. Full text is available across all row pages.':'No body rows. Saved titles are shown above.';
  }catch(error){showError(error);}}
 function pageBy(direction){renderPage(model.page+direction);}
 function navigate(direction){try{assertCurrent();const blocks=model.comparison?.blocks||[];if(!blocks.length)return;model.change=model.change<0?(direction>0?0:blocks.length-1):(model.change+direction+blocks.length)%blocks.length;const block=blocks[model.change];if(!block.title)renderPage(Math.floor(block.start/PAGE_ROWS));const target=q(block.id);target?.scrollIntoView({block:'nearest'});target?.focus();q('revision-navigation-status').textContent='Change '+(model.change+1)+' of '+blocks.length+(block.title?' · saved title':' · body lines')+'.';}catch(error){showError(error);}}
 return {open,mount,diff,compare,lineEnding,current};
})();
