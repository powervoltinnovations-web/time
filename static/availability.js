'use strict';
function combinedOption(c,e){const g=c.groups.find(g=>g.id===e.group_id),s=c.subjects.find(s=>s.id===e.subject_id);return e.kind==='lecture'&&g?.semester===7&&['A','B'].includes(g.division.toUpperCase())&&Boolean(c.settings.combined_elective_students?.[s?.code]);}
function uniquePhysicalSessions(c,entries){const seen=new Set();return entries.filter(e=>{if(!combinedOption(c,e))return true;const key=[e.subject_id,e.teacher_id,e.day,e.slot,e.duration,e.room_id].join('|');if(seen.has(key))return false;seen.add(key);return true;});}
function freeSlotButton(day,slot){return `<button class="button small free-slot" data-action="free-resources" data-day="${day}" data-slot="${slot}">Free faculty & rooms</button>`;}
const actionBeforeAvailability=action;
action=async function(name,node){if(name==='free-resources'){await showAvailability(Number(node.dataset.day),Number(node.dataset.slot),1);return;}return actionBeforeAvailability(name,node);};
async function showAvailability(day,slot,duration){
 const g=state.generation;if(!g)return;
 let a;try{a=await api(`/api/generations/${g.id}/availability?day=${day}&slot=${slot}&duration=${duration}`);}catch(e){toast(e.message);return;}
 const rooms=items=>items.length?items.map(r=>`<li>${esc(r.name)} · ${r.capacity} seats${r.eligible_years?.length?' · Years '+r.eligible_years.join(', '):''}</li>`).join(''):'<li>None available</li>';
 openModal('Free faculty, classrooms and labs','Resources in the selected saved timetable',`<div class="modal-body"><p><strong>${esc(a.day)} · ${esc(a.start)}–${esc(a.end)}</strong></p><label for="availability-duration">Check complete session</label><select id="availability-duration">${[1,2,4].map(n=>`<option value="${n}" ${duration===n?'selected':''}>${n} period(s) · ${n*g.meta.period_minutes/60} hour(s)</option>`).join('')}</select><p class="inline-help">${esc(a.note)}</p><h3>Free faculty (${a.teachers.length})</h3><ul>${a.teachers.length?a.teachers.map(t=>`<li>${esc(t.name)} · ${t.remaining_daily_periods} periods remaining today / ${t.remaining_weekly_hours} hours this week${t.lab_eligible?'':' · Not lab eligible'}</li>`).join(''):'<li>None available</li>'}</ul><h3>Free classrooms (${a.classrooms.length})</h3><ul>${rooms(a.classrooms)}</ul><h3>Free labs (${a.labs.length})</h3><ul>${rooms(a.labs)}</ul><p>Use “Edit timetable manually” to move existing sessions. This list does not change assignments or required hours.</p></div>`);
 document.getElementById('availability-duration').addEventListener('change',e=>showAvailability(day,slot,Number(e.target.value)));
}
