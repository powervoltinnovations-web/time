'use strict';
/* Optional project assignments; opening the page never creates or edits academic data. */
function projectsPage(){
 const m=maps(),groupIds=new Set(scopedGroups().map(g=>g.id));
 const projects=state.config.offerings.filter(o=>o.projects>0&&groupIds.has(o.group_id));
 return pageHeading('OPTIONAL SESSIONS','Mini projects','Add project sessions only when required. Your existing subjects, lab assignments, and timetable rules stay as configured.',btn('Add mini project','project-add','plus','primary'))+
 `<section class="panel">${projects.length?table(['Project / division','Supervisor','Sessions / week','Hours / session','Room',''],projects.map(o=>cells([`<strong>${esc(m.subjects[o.subject_id].name)}</strong><small>${esc(m.subjects[o.subject_id].code)} · ${esc(groupName(m.groups[o.group_id]))}${o.batch_id?' · '+esc(m.batches[o.batch_id].name):''}</small>`,esc(m.teachers[o.teacher_id]?.name||'Independent project · no teacher'),o.projects,o.project_hours??state.config.settings.project_slots*state.config.settings.period_minutes/60,esc(m.rooms[o.project_room_id||o.lab_room_id]?.name||'No room booked'),`<button class="button small" data-action="project-edit" data-id="${esc(o.id)}">Edit project</button> <button class="button small" data-action="project-remove" data-id="${esc(o.id)}">Remove project</button>`]))):empty('No mini projects added','No sample projects have been created. Use Add mini project when you want to schedule one.')}</section>`;
}
function projectModal(id=null){
 const c=state.config,o=c.offerings.find(o=>o.id===id),m=maps(),subject=o?m.subjects[o.subject_id]:null;
 const groups=o?[m.groups[o.group_id]]:scopedGroups();
 if(!groups.length){toast('Add a division before creating a mini project.');return;}
 const mixed=o&&(o.lectures||o.labs);
 const fields=selectField('group_id','Year / division',groups.map(g=>[g.id,groupName(g)]),o?.group_id||groups[0].id)+
 inputField('name','Project name',subject?.name||'','text',`required maxlength="120" ${o?'readonly':''}`)+
 inputField('code','Project subject code',subject?.code||'','text',`required maxlength="30" ${o?'readonly':''}`,'Use an existing project code or enter your own new code.')+
 selectField('teacher_id','Project supervisor',[['','No supervisor · independent project'],...(mixed?c.teachers.filter(t=>t.id===o.teacher_id):c.teachers.filter(t=>t.lab_eligible)).map(t=>[t.id,t.name])],o?.teacher_id||'')+
 inputField('projects','Sessions per week',o?.projects??1,'number','required min="1" max="20"')+
 inputField('project_hours','Hours per session',o?.project_hours??c.settings.project_slots*c.settings.period_minutes/60,'number','required min="0.5" max="8" step="0.5"','Must fit complete periods without crossing recess.')+
 selectField('project_room_id','Project room',[['','No room · independent project'],...c.rooms.map(r=>[r.id,`${r.name} · ${r.kind} · ${r.capacity} seats`])],o?.project_room_id||o?.lab_room_id||'');
 openModal(o?'Edit mini project':'Add mini project','Select a classroom or lab with enough seats. No room or teacher is added automatically.',`<form id="modal-form"><div class="form-grid">${fields}</div>${o?.batch_id?`<p class="inline-help">Existing scope: Batch ${esc(m.batches[o.batch_id].name)}.</p>`:'<p class="inline-help">Scope: whole division. Projects occupy every batch in this division.</p>'}${mixed?'<p class="inline-help">This assignment also has lectures/labs; their supervisor and session counts are preserved.</p>':''}<div class="form-error" id="form-error" role="alert"></div><div class="form-actions">${btn('Cancel','close-modal')}<button type="submit" class="button primary">Save mini project</button></div></form>`,async form=>{
  const v=Object.fromEntries(new FormData(form)),next=structuredClone(c),g=m.groups[v.group_id],hours=Number(v.project_hours),count=Number(v.projects),room=m.rooms[v.project_room_id];
  const size=o?.batch_id?m.batches[o.batch_id].strength:g.strength;
  if(v.teacher_id&&(!room||room.capacity<size))throw Error(`Choose a room with at least ${size} seats. No room capacity is changed automatically.`);
  if(v.teacher_id&&room&&(room.department_id&&room.department_id!==g.department_id||room.eligible_years.length&&!room.eligible_years.includes(Math.ceil(g.semester/2))))throw Error('Choose a room eligible for this department and year.');
  let s=subject||next.subjects.find(s=>s.department_id===g.department_id&&s.code.toLowerCase()===v.code.trim().toLowerCase());
  if(!o&&s&&(s.semester!==g.semester||s.course_type!=='project'))throw Error('This code belongs to another course or semester. Enter a new project code.');
  if(!o&&s&&next.offerings.some(a=>a.group_id===g.id&&a.subject_id===s.id&&!a.batch_id))throw Error('This division already has that project. Edit its existing assignment.');
  if(!s){s={id:'project_'+crypto.randomUUID(),name:v.name,code:v.code,semester:g.semester,department_id:g.department_id,course_type:'project',weekly_hours:Math.ceil(count*hours),elective:false,elective_set_id:null};next.subjects.push(s);}
  const values={projects:count,project_hours:hours,project_room_id:v.teacher_id?room.id:null,teacher_id:v.teacher_id||null};
  if(o)Object.assign(next.offerings.find(a=>a.id===o.id),values);
  else next.offerings.push({id:'project_'+crypto.randomUUID(),group_id:g.id,subject_id:s.id,lectures:0,labs:0,lab_room_id:null,batch_id:null,...values});
  await saveConfig(next);closeModal();render();toast('Mini project saved. Generate again to include it.');
 });
 $('#f-teacher_id').required=false;$('#f-project_room_id').required=false;
}
const actionBeforeProjects=action;
action=async function(name,node){
 if(name==='project-add'){projectModal();return;}
 if(name==='project-edit'){projectModal(node.dataset.id);return;}
 if(name==='project-remove'){
  const o=state.config.offerings.find(o=>o.id===node.dataset.id);
  openModal('Remove mini project','Remove only these project sessions. Subject, teacher, room, lecture/lab records, and saved timetable versions remain.',`<form id="modal-form"><div class="form-error" id="form-error" role="alert"></div><div class="form-actions">${btn('Cancel','close-modal')}<button type="submit" class="button danger">Remove project sessions</button></div></form>`,async()=>{
   const next=structuredClone(state.config),i=next.offerings.findIndex(x=>x.id===o.id);
   if(o.lectures||o.labs)Object.assign(next.offerings[i],{projects:0,project_hours:null,project_room_id:null});else next.offerings.splice(i,1);
   await saveConfig(next);closeModal();render();toast('Project sessions removed. Existing saved timetables are unchanged.');
  });return;
 }
 return actionBeforeProjects(name,node);
};
