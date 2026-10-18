'use strict';
/* Versioned manual placement and coordinator workflow controls. */
const timetableBeforeEditing=timetablePage;
const historyBeforeEditing=historyPage;
const actionBeforeEditing=action;
function workflowBadge(g){const w=g.workflow||{state:'draft',locked:false};return tag(w.state==='approved'?'Approved':'Draft',w.state==='approved'?'green':'orange')+' '+(w.locked?tag('Locked','purple'):'');}
timetablePage=function(){
 const html=timetableBeforeEditing(),g=state.generation;
 if(!g)return html;
 if(g.result.status!=='feasible')return html+`<section class="panel panel-body">${deleteTimetableButton(g)}</section>`;
 const w=g.workflow||{state:'draft',locked:false,revision:0},editable=!w.locked&&w.state==='draft';
 const controls=`<section class="panel workflow-panel"><div class="panel-header"><div><h2>Timetable status ${workflowBadge(g)}</h2><p>Version #${g.id}${g.result.parent_generation_id?' · Edited from #'+g.result.parent_generation_id:''} · Approval is a coordinator status in this local workspace.</p></div><div class="button-row"><button class="button small" data-action="workflow-draft" ${w.locked||w.state==='draft'?'disabled':''}>Mark Draft</button><button class="button small" data-action="workflow-approve" ${w.locked||w.state==='approved'?'disabled':''}>Approve timetable</button><button class="button small" data-action="workflow-${w.locked?'unlock':'lock'}">${w.locked?'Unlock':'Lock'} timetable</button>${deleteTimetableButton(g)}</div></div><div class="panel-body"><div class="button-row"><button class="button primary" data-action="manual-edit" ${editable?'':'disabled'}>Edit timetable manually</button><button class="button" data-action="manual-edit-all" ${editable?'':'disabled'}>Edit entire plan</button></div><p class="inline-help">${w.locked?'This saved version is locked. Unlock it before changing its status or editing.':w.state==='approved'?'This version is approved. Mark it Draft before editing.':'Change session days, starting periods, or eligible rooms. Save several moves together to swap sessions. Every saved edit creates a new Draft; earlier timetable content stays intact.'} New generation always creates a separate draft.</p></div></section>`;
 return html.replace('<section class="panel">',controls+'<section class="panel">');
};
historyPage=function(){return pageHeading('VERSION HISTORY','Every generation, preserved.','Timetable content is immutable. Workflow status and locks apply to each version.')+`<section class="panel">${table(['Timetable','Created','Data revision','Generation','Workflow',''],state.history.map(h=>cells([esc(h.name),when(h.created_at),h.config_revision,statusTag(h.status),h.status==='feasible'?workflowBadge(h):'—',`<button class="button small" data-action="open-generation" data-id="${h.id}">Open version #${h.id}</button> ${deleteTimetableButton(h)}`])))}</section>`;};
function deleteTimetableButton(g){return `<button class="button small danger" data-action="delete-timetable" data-id="${g.id}" ${g.workflow?.locked?'disabled title="Unlock this timetable before deleting it"':''}>${icon('trash')} Delete timetable</button>`;}
async function deleteTimetableModal(identifier){
 if(state.generating){toast('Wait for timetable generation to finish before deleting.');return;}
 const g=await api(`/api/generations/${identifier}`);
 if(g.workflow.locked){toast('Unlock this timetable before deleting it.');return;}
 openModal('Delete timetable?',`Version #${g.id} · ${esc(g.name)}`,`<form id="modal-form"><p>Permanently delete this saved timetable? This cannot be undone. Academic data and other saved timetables will stay unchanged.</p><div class="form-error" id="form-error" role="alert"></div><div class="form-actions">${btn('Cancel','close-modal')}<button class="button danger" type="submit">Delete timetable permanently</button></div></form>`,async()=>{
  await api(`/api/generations/${g.id}?revision=${g.workflow.revision}`,{method:'DELETE'});
  state.history=await api('/api/generations');
  if(state.generation?.id===g.id){state.generation=state.history.length?await api(`/api/generations/${state.history[0].id}`):null;state.target='';state.batch='';}
  state.analyticsCache={};
  if(typeof assistantState!=='undefined'&&Number(assistantState.generation)===g.id){assistantState.generation='';assistantState.entry='';assistantState.record=null;}
  closeModal();render();toast('Timetable deleted.');
 });
}
function manualRoomChoices(entry,c){const g=c.groups.find(g=>g.id===entry.group_id),batch=c.batches.find(b=>b.id===entry.batch_id),o=c.offerings.find(o=>o.id===entry.offering_id),fixed=entry.kind==='lecture'?g.room_id:entry.kind==='project'?(o.project_room_id||o.lab_room_id):o.lab_room_id,kind=entry.kind==='project'&&o.project_room_id?c.rooms.find(r=>r.id===o.project_room_id).kind:entry.kind==='lecture'?'classroom':'lab';return c.rooms.filter(r=>r.kind===kind&&(!fixed||r.id===fixed)&&r.capacity>=(batch?.strength||g.strength)&&(!r.department_id||r.department_id===g.department_id)&&(!r.eligible_years.length||r.eligible_years.includes(Math.ceil(g.semester/2)))).map(r=>[r.id,r.name]);}
function manualEditor(all=false){
 const g=state.generation,w=g.workflow;if(w.locked||w.state!=='draft'){toast('Choose an unlocked Draft before editing.');return;}
 const c=g.config,m=maps(c),meta=g.meta,entries=g.result.entries;
 const selected=entries.map((e,index)=>({e,index})).filter(({e})=>all||e[state.view+'_id']===state.target);
 if(!selected.length){toast('There are no sessions to edit in this view. Use Edit entire plan.');return;}
 const rows=selected.map(({e,index})=>{const subject=m.subjects[e.subject_id];return `<tr data-entry-index="${index}"><td><strong>${esc(subject.code)} · ${esc(subject.name)}</strong><small>${esc(groupName(m.groups[e.group_id],c))}${e.batch_id?' · '+esc(m.batches[e.batch_id].name):''}</small><small>${esc(m.teachers[e.teacher_id].name)} · ${esc(e.kind)} · ${e.duration} period(s)</small><small>Currently ${meta.days[e.day]} ${meta.periods[e.slot][0]}</small></td><td><select class="edit-day" aria-label="Day for session ${index+1}">${optionsHTML(meta.days.map((d,i)=>[i,d]),e.day)}</select></td><td><select class="edit-slot" aria-label="Starting period for session ${index+1}">${optionsHTML(meta.periods.map(([a,b],i)=>[i,`P${i+1} · ${a}`]),e.slot)}</select></td><td><select class="edit-room" aria-label="Room for session ${index+1}">${optionsHTML(manualRoomChoices(e,c),e.room_id)}</select></td></tr>`;});
 openModal('Edit timetable manually',`Version #${g.id} · ${all?'Complete saved plan':'Current '+(state.view==='group'?'division':'professor')} · ${selected.length} sessions`,
 `<form id="modal-form" class="manual-editor"><div class="info-banner"><span>To swap two lectures, exchange their day and starting period in both rows before saving. Labs/projects move as whole sessions. Teacher, subject, and duration stay tied to their assignment. All divisions are checked, including those outside this view.</span></div><div class="table-scroll"><table class="data-table"><thead><tr><th>Session</th><th>Day</th><th>Starting period</th><th>Room</th></tr></thead><tbody>${rows.join('')}</tbody></table></div><div class="form-error" id="form-error" role="alert"></div><div class="form-actions">${btn('Cancel','close-modal')}<button class="button primary" type="submit">Validate & save new Draft</button></div></form>`,async form=>{
  const changes=[...form.querySelectorAll('[data-entry-index]')].map(row=>({entry_index:Number(row.dataset.entryIndex),day:Number(row.querySelector('.edit-day').value),slot:Number(row.querySelector('.edit-slot').value),room_id:row.querySelector('.edit-room').value})).filter(change=>{const old=entries[change.entry_index];return old.day!==change.day||old.slot!==change.slot||old.room_id!==change.room_id;});
  if(!changes.length)throw Error('No placements changed yet. Change a day, starting period, or eligible room.');
  const updated=await api(`/api/generations/${g.id}/edits`,jsonOptions('POST',{revision:w.revision,changes}));
  state.generation=updated;state.history=await api('/api/generations');state.analyticsCache={};closeModal();render();toast('Validated and saved as a new Draft. The previous version remains in history.');
 });
}
action=async function(name,node){
 if(name==='create-three-batches'){const group=state.config.groups.find(g=>g.id===node.dataset.id);if(group.strength<3)throw Error('At least three students are needed for three batches.');const next=structuredClone(state.config);for(let i=1;i<=3;i++)next.batches.push({id:'batch_'+crypto.randomUUID(),group_id:group.id,name:group.division+i,strength:Math.floor(group.strength/3)+(i<=group.strength%3?1:0)});await saveConfig(next);render();toast('Three batches created. Add separate lab assignments with teachers and rooms for each batch.');return;}
 if(name==='delete-timetable'){await deleteTimetableModal(Number(node.dataset.id));return;}
 if(name==='manual-edit'||name==='manual-edit-all'){manualEditor(name==='manual-edit-all');return;}
 if(name.startsWith('workflow-')){const g=state.generation;node.disabled=true;try{state.generation=await api(`/api/generations/${g.id}/workflow`,jsonOptions('PATCH',{revision:g.workflow.revision,action:name.slice(9)}));state.history=await api('/api/generations');render();toast('Timetable status saved.');}finally{node.disabled=false;}return;}
 return actionBeforeEditing(name,node);
};
if(state.config)render();
