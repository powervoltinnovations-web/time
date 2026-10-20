'use strict';
/* Read-only advice; all actionable room alternatives originate in the local audit. */
const assistantState={generation:'',entry:'',mode:'local',messages:[],record:null,status:null,busy:false};
function assistantPage(){
 const a=assistantState;
 return pageHeading('TIMETABLE ASSISTANT','Ask about your timetable.','Check room alternatives, constraints, classroom continuity, and teaching loads.')+`<section class="panel panel-body"><div class="form-grid"><div class="field"><label for="assistant-plan">Timetable scope</label><select id="assistant-plan">${optionsHTML([['','All saved timetables (latest 100)'],...state.history.map(g=>[g.id,`#${g.id} · ${g.name} · ${g.status}`])],a.generation)}</select></div><div class="field"><label for="assistant-session">Session for a room check</label><select id="assistant-session" ${a.generation?'':'disabled'}><option value="">Choose a timetable first</option></select></div><div class="field"><label for="assistant-mode">Assistant mode</label><select id="assistant-mode">${optionsHTML([['local','Local checks · no API key'],['openai','OpenAI explanation + local checks']],a.mode)}</select></div></div><p id="assistant-status" class="inline-help">Loading assistant status…</p><p class="inline-help" id="assistant-online-note" ${a.mode==='openai'?'':'hidden'}>OpenAI mode sends your question and the selected plans’ audit facts and the session list for a single selected plan (including faculty and room names) to OpenAI. The API key stays on your server. No timetable is changed.</p><div class="button-row"><button class="button small" data-action="assistant-example" data-question="Is there a replacement classroom for this session?">Find another room</button><button class="button small" data-action="assistant-example" data-question="Explain conflicts and gaps in these timetables.">Explain conflicts</button><button class="button small" data-action="assistant-example" data-question="How can I reduce classroom changes?">Classroom continuity</button><button class="button small" data-action="assistant-example" data-question="Explain the faculty workload.">Faculty workload</button></div></section><section class="panel panel-body section-spacer"><div id="assistant-messages" class="assistant-messages" aria-live="polite">${a.messages.map(assistantMessage).join('')||'<p class="inline-help">Select a timetable and session for a precise room check. All saved versions are reviewed separately.</p>'}</div><form id="assistant-form"><div class="field"><label for="assistant-question">Your question</label><textarea id="assistant-question" rows="3" maxlength="1500" required placeholder="Is there a replacement classroom for this lecture?"></textarea></div><div class="form-error" id="assistant-error" role="alert"></div><div class="button-row section-spacer"><button class="button primary" type="submit" ${a.busy?'disabled':''}>${a.busy?'Checking…':'Ask assistant'}</button><button class="button" type="button" data-action="assistant-clear">Clear conversation</button></div></form></section>`;
}
function assistantMessage(m){
 return `<article class="assistant-message ${m.role}"><strong>${m.role==='user'?'You':m.mode==='openai'?'OpenAI explanation':'Local timetable checks'}</strong>${m.scope?`<small>${esc(m.scope)}</small>`:''}<div class="assistant-answer">${esc(m.text)}</div>${m.error?`<p class="form-error">${esc(m.error)}</p>`:''}${m.local?`<details><summary>Verified local checks</summary><div class="assistant-answer">${esc(m.local)}</div></details>`:''}</article>`;
}
async function loadAssistant(){
 try{
  assistantState.status=await api('/api/assistant/status');
  if(state.page!=='assistant')return;
  const s=assistantState.status;
  $('#assistant-status').textContent=s.online_available?`Local checks ready. Optional OpenAI model: ${s.model}.`:'Local checks ready. For OpenAI, set UNISCHED_OPENAI_API_KEY on the server and restart; setup instructions are in README.';
  await loadAssistantSessions();
 }catch(e){if($('#assistant-status'))$('#assistant-status').textContent=e.message;}
}
async function loadAssistantSessions(){
 const a=assistantState,id=a.generation;
 a.record=null;
 const select=$('#assistant-session');if(!select)return;
 select.disabled=true;
 if(!id){select.innerHTML='<option value="">Select one timetable for a session check</option>';return;}
 select.innerHTML='<option value="">Loading sessions…</option>';
 const record=await api('/api/generations/'+id);
 if(state.page!=='assistant'||a.generation!==id)return;
 a.record=record;const m=maps(record.config),meta=record.meta;
 select.innerHTML=optionsHTML([['','Whole timetable summary'],...record.result.entries.map((e,i)=>[i,`${meta.days[e.day]} ${meta.periods[e.slot][0]} · ${groupName(m.groups[e.group_id],record.config)} · ${m.subjects[e.subject_id].code}${e.batch_id?' · '+m.batches[e.batch_id].name:''} · ${m.rooms[e.room_id]?.name||'Independent project'}`])],a.entry);
 select.disabled=record.result.status!=='feasible';
}
const actionBeforeAssistant=action;
action=async function(name,node){
 if(name==='assistant-example'){$('#assistant-question').value=node.dataset.question;$('#assistant-question').focus();return;}
 if(name==='assistant-clear'){assistantState.messages=[];render();return;}
 return actionBeforeAssistant(name,node);
};
document.addEventListener('change',async event=>{
 try{
  if(event.target.id==='assistant-plan'){assistantState.generation=event.target.value;assistantState.entry='';await loadAssistantSessions();}
  if(event.target.id==='assistant-session')assistantState.entry=event.target.value;
  if(event.target.id==='assistant-mode'){assistantState.mode=event.target.value;$('#assistant-online-note').hidden=event.target.value!=='openai';}
 }catch(e){if($('#assistant-error'))$('#assistant-error').textContent=e.message;}
});
document.addEventListener('submit',async event=>{
 if(event.target.id!=='assistant-form')return;
 event.preventDefault();const a=assistantState;if(a.busy)return;
 const question=$('#assistant-question').value.trim();if(!question)return;
 const payload={question,mode:a.mode,generation_id:a.generation?Number(a.generation):null,entry_index:a.entry!==''?Number(a.entry):null};
 const scope=a.generation?`Timetable #${a.generation}`:'All saved timetables';
 a.messages.push({role:'user',text:question,scope});a.busy=true;
 const button=event.target.querySelector('[type="submit"]');button.disabled=true;button.textContent='Checking…';$('#assistant-error').textContent='';
 try{
  const response=await api('/api/assistant/ask',jsonOptions('POST',payload));
  a.messages.push({role:'assistant',scope,mode:response.mode,text:response.answer,error:response.online_error,local:response.mode==='openai'?response.local_answer:null});
 }catch(e){a.messages.push({role:'assistant',scope,mode:'local',text:'The request could not be completed.',error:e.message});}
 finally{a.busy=false;if(state.page==='assistant')render();}
});
