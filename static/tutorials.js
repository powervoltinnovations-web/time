'use strict';
function tutorialsPage(){
 const m=maps(),ids=new Set(scopedGroups().map(g=>g.id)),rows=state.config.offerings.filter(o=>o.tutorials&&ids.has(o.group_id));
 return pageHeading('CURRICULUM','Tutorials','Separate tutorial assignments, with the supplied faculty, batches, and classroom. Changes happen only when you save.',btn('Add tutorial','tutorial-add','plus','primary'))+`<section class="panel">${rows.length?table(['Subject / division','Batch','Teacher','Sessions / week','Hours / session','Classroom',''],rows.map(o=>cells([`<strong>${esc(m.subjects[o.subject_id].name)}</strong><small>${esc(m.subjects[o.subject_id].code)} · ${esc(groupName(m.groups[o.group_id]))}</small>`,esc(m.batches[o.batch_id]?.name||'Whole division'),esc(m.teachers[o.teacher_id]?.name),o.tutorials,o.tutorial_hours??state.config.settings.lecture_slots*state.config.settings.period_minutes/60,esc(m.rooms[o.tutorial_room_id]?.name||'Auto classroom'),`<button class="button small" data-action="tutorial-edit" data-id="${esc(o.id)}">Edit tutorial</button> <button class="button small" data-action="tutorial-remove" data-id="${esc(o.id)}">Remove</button>`]))):empty('No tutorials in this scope','Add one only when required.')}</section>`;
}
function tutorialModal(id=null){
 const c=state.config,m=maps(),o=c.offerings.find(x=>x.id===id),s=o?m.subjects[o.subject_id]:null,groups=o?[m.groups[o.group_id]]:scopedGroups();
 if(!groups.length){toast('Add a division first.');return;}
 const fields=selectField('group_id','Year / division',groups.map(g=>[g.id,groupName(g)]),o?.group_id||groups[0].id)+selectField('batch_id','Student scope',[['','Whole division'],...c.batches.filter(b=>b.group_id===(o?.group_id||groups[0].id)).map(b=>[b.id,b.name])],o?.batch_id||'')+
 inputField('name','Tutorial subject name',s?.name||'','text',`required maxlength="120" ${o?'readonly':''}`)+inputField('code','Subject code',s?.code||'','text',`required maxlength="30" ${o?'readonly':''}`)+selectField('teacher_id','Teacher',[['','Choose the assigned teacher'],...c.teachers.map(t=>[t.id,t.name])],o?.teacher_id||'')+
 inputField('tutorials','Sessions per week',o?.tutorials??1,'number','required min="1" max="40"')+inputField('tutorial_hours','Hours per session',o?.tutorial_hours??c.settings.lecture_slots*c.settings.period_minutes/60,'number','required min="0.5" max="4" step="0.5"')+selectField('tutorial_room_id','Tutorial classroom',[['','Choose classroom'],...c.rooms.filter(r=>r.kind==='classroom').map(r=>[r.id,`${r.name} · ${r.capacity} seats`])],o?.tutorial_room_id||'');
 openModal(o?'Edit tutorial':'Add tutorial','Tutorials use their own classroom and student scope. Lectures remain whole-division sessions.',`<form id="modal-form"><div class="form-grid">${fields}</div><div class="form-error" id="form-error" role="alert"></div><div class="form-actions">${btn('Cancel','close-modal')}<button class="button primary" type="submit">Save tutorial</button></div></form>`,async form=>{
  const v=Object.fromEntries(new FormData(form)),next=structuredClone(c),g=m.groups[v.group_id],count=Number(v.tutorials),hours=Number(v.tutorial_hours);
  let subject=s||next.subjects.find(x=>x.department_id===g.department_id&&x.code.toLowerCase()===v.code.trim().toLowerCase());
  if(subject&&(subject.semester!==g.semester||subject.course_type!=='tutorial'))throw Error('Choose a tutorial code for this semester.');
  if(!subject){subject={id:'tutorial_'+crypto.randomUUID(),name:v.name,code:v.code,semester:g.semester,department_id:g.department_id,course_type:'tutorial',weekly_hours:Math.ceil(count*hours),elective:false,elective_set_id:null};next.subjects.push(subject);}
  const values={teacher_id:v.teacher_id,tutorials:count,tutorial_hours:hours,tutorial_room_id:v.tutorial_room_id,batch_id:v.batch_id||null};
  if(o)Object.assign(next.offerings.find(x=>x.id===id),values);
  else next.offerings.push({id:'tutorial_'+crypto.randomUUID(),group_id:g.id,subject_id:subject.id,lectures:0,labs:0,projects:0,...values});
  await saveConfig(next);closeModal();render();toast('Tutorial saved for future generations.');
 });
 $('#f-batch_id').required=false;
 $('#f-group_id').addEventListener('change',()=>{$('#f-batch_id').innerHTML=optionsHTML([['','Whole division'],...c.batches.filter(b=>b.group_id===$('#f-group_id').value).map(b=>[b.id,b.name])],'');});
}
const actionBeforeTutorials=action;
action=async function(name,node){
 if(name==='tutorial-add'){tutorialModal();return;}
 if(name==='tutorial-edit'){tutorialModal(node.dataset.id);return;}
 if(name==='tutorial-remove'){
  openModal('Remove tutorial sessions','Only these tutorial sessions will be removed; saved timetables and other academic records remain.',`<form id="modal-form"><div class="form-error" id="form-error" role="alert"></div><div class="form-actions">${btn('Cancel','close-modal')}<button class="button danger" type="submit">Remove tutorial</button></div></form>`,async()=>{
   const next=structuredClone(state.config),i=next.offerings.findIndex(o=>o.id===node.dataset.id),o=next.offerings[i];
   if(o.lectures||o.labs||o.projects)Object.assign(o,{tutorials:0,tutorial_room_id:null,tutorial_hours:null});else next.offerings.splice(i,1);
   await saveConfig(next);closeModal();render();toast('Tutorial sessions removed.');
  });return;
 }
 return actionBeforeTutorials(name,node);
};
