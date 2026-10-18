'use strict';

const icons = {
 dashboard:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
 calendar:'<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 3v4m10-4v4M3 11h18m-13 4h2m4 0h2m-8 3h2"/>',
 sliders:'<path d="M4 7h6m4 0h6M4 17h10m4 0h2"/><circle cx="12" cy="7" r="2"/><circle cx="16" cy="17" r="2"/>',
 upload:'<path d="M12 16V3m-5 5 5-5 5 5M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5"/>',
 download:'<path d="M12 3v13m-5-5 5 5 5-5M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
 users:'<circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3m1-17a3 3 0 0 1 0 6m2 4a5 5 0 0 1 3 4v3"/>',
 book:'<path d="M12 5v16M3 4c3-1 6-1 9 1 3-2 6-2 9-1v15c-3-1-6-1-9 2-3-3-6-3-9-2z"/>',
 building:'<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 7h1m4 0h1m-6 4h1m4 0h1m-6 4h1m4 0h1m-4 6v-3h2v3"/>',
 clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
 check:'<path d="m5 12 4 4L19 6"/>',
 shield:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z"/><path d="m8 12 3 3 5-6"/>',
 spark:'<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5zM20 2v4m-2-2h4"/>',
 arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',
 plus:'<path d="M12 5v14M5 12h14"/>',
 edit:'<path d="m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-4-4L5 15z"/>',
 trash:'<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
 close:'<path d="m6 6 12 12M6 18 18 6"/>',
 info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10h.01"/>',
 alert:'<path d="m12 3 10 18H2zM12 9v5m0 3h.01"/>',
 file:'<path d="M14 3H5v18h14V8zM14 3v5h5M8 12h8m-8 4h6"/>',
 menu:'<path d="M4 6h16M4 12h16M4 18h16"/>'
};
const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.calendar}</svg>`;
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const $ = selector => document.querySelector(selector);
const years = {3:'Second Year',5:'Third Year',7:'Final Year'};
const state = {config:null, revision:0, history:[], generation:null, page:'overview', tab:'offerings', search:'', view:'group', semester:3, target:'', generating:false, preview:null};
const categories = {offerings:'Assignments',teachers:'Teachers',subjects:'Subjects',groups:'Divisions',rooms:'Rooms & labs'};
const singular = {offerings:'assignment',teachers:'teacher',subjects:'subject',groups:'division',rooms:'room'};
let toastTimer;
let modalSubmit;

function hydrateIcons(){document.querySelectorAll('[data-icon]').forEach(node => {node.innerHTML=icon(node.dataset.icon);});}
function toast(message){$('#toast').textContent=message;$('#toast').classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.remove('visible'),4500);}
async function api(url, options={}){
 const response=await fetch(url,options);
 if(!response.ok){let detail;try{detail=(await response.json()).detail;}catch{detail='The server could not complete this request.';}
  if(Array.isArray(detail)) detail=detail.map(e=>`${e.loc.slice(1).join(' → ')}: ${e.msg}`).join('\n');
  throw new Error(typeof detail==='string'?detail:`Request failed (${response.status}).`);
 }
 return response.json();
}
const jsonOptions = (method, data) => ({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
const btn = (label,action,iconName='',style='') => `<button class="button ${style}" data-action="${action}" ${action==='generate'&&state.generating?'disabled':''}>${iconName?icon(iconName):''}${label}</button>`;
const tag = (label,style='') => `<span class="tag ${style}">${esc(label)}</span>`;
function maps(config=state.config){return Object.fromEntries(['teachers','subjects','groups','rooms'].map(key=>[key,Object.fromEntries(config[key].map(item=>[item.id,item]))]));}
function pageHeading(eyebrow,title,subtitle,actions=''){return `<div class="page-heading"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p>${subtitle}</p></div>${actions}</div>`;}
function statusTag(status){return tag(status==='feasible'?'Generated':status==='infeasible'?'Not possible':'Search limit',status==='feasible'?'green':status==='infeasible'?'red':'orange');}
function when(value){return new Date(value).toLocaleString(undefined,{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});}
function groupLabel(group){return `${years[group.semester]} · Semester ${group.semester} · Div ${group.division}`;}
function empty(title,description,action=''){return `<div class="empty-state"><div class="empty-icon">${icon('calendar')}</div><h2>${title}</h2><p>${description}</p>${action}</div>`;}
function formError(error){const node=$('#form-error');if(node)node.textContent=error.message;else toast(error.message);}

async function boot(){
 try{
  const [config,meta,history]=await Promise.all([api('/api/config'),api('/api/meta'),api('/api/generations')]);
  state.config=config.configuration;state.revision=config.revision;state.meta=meta;state.history=history;
  if(history.length)state.generation=await api(`/api/generations/${history[0].id}`);
  $('#system-status').innerHTML='<span class="status-dot"></span>Workspace connected';
  render();
 }catch(error){$('#system-status').textContent='Connection unavailable';$('#main').innerHTML=`<div class="panel retry-box"><h2>Couldn’t open your workspace</h2><p>${esc(error.message)}</p>${btn('Try again','reload','arrow','primary')}</div>`;}
 hydrateIcons();
}
function render(){
 if(!state.config)return;
 const hash=location.hash.slice(1)||'overview';state.page=['overview','timetables','setup','import'].includes(hash)?hash:'overview';
 document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('active',a.dataset.page===state.page));
 document.querySelectorAll('nav a').forEach(a=>{if(a.dataset.page===state.page)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
 $('#schedule-count').textContent=state.history.filter(h=>h.status==='feasible').length;
 $('#main').innerHTML=({overview:overviewPage,timetables:timetablePage,setup:setupPage,import:importPage})[state.page]();
 document.title=`${{overview:'Overview',timetables:'Timetables',setup:'Academic setup',import:'Import data'}[state.page]} · UniSched`;
 hydrateIcons();
}

function overviewPage(){
 const c=state.config;const hours=c.offerings.reduce((n,o)=>n+o.lectures+o.labs*2,0);
 const stats=[['Teaching faculty',c.teachers.length,'Across all three years','users',''],['Academic divisions',c.groups.length,'Semesters 3, 5 & 7','building','blue'],['Subjects to schedule',c.subjects.length,`${c.subjects.filter(s=>s.elective).length} electives included`,'book','orange'],['Weekly teaching hours',hours,'1 lab session = 2 hours','clock','green']];
 const constraints=[['clock','A structured campus day','09:00–17:45 · Recess 13:00–13:45'],['users','Faculty, without conflicts','Availability & weekly limits respected'],['calendar','No gaps between classes','Consecutive periods from 09:00'],['book','Every elective has its space','Separate slots within each semester'],['building','The right room, every time','No classroom or laboratory overlaps']];
 const latest=state.history[0];
 return pageHeading('YOUR ACADEMIC WORKSPACE','A better week starts here.','Plan with clarity. Schedule with confidence.',btn(state.generating?'Generating…':'Generate timetable','generate','spark','primary'))+
 `<div class="stats-grid">${stats.map(([label,count,foot,ic,color])=>`<div class="stat-card"><div class="stat-top">${label}<span class="stat-icon ${color}">${icon(ic)}</span></div><div class="stat-number">${count}</div><div class="stat-foot">${foot}</div></div>`).join('')}</div>
 <div class="dashboard-columns"><section class="panel"><div class="hero-panel"><div class="hero-copy"><div class="eyebrow">LESS ADMIN. MORE POSSIBILITY.</div><h2>Your campus.<br>One harmonious timetable.</h2><p>Turn complex academic requirements into<br>a clear, conflict-free week.</p></div><div class="hero-art" aria-hidden="true"><div class="art-calendar"><div class="art-top"><span></span><span></span><span></span></div><div class="art-grid">${'<span></span>'.repeat(25)}</div></div><div class="art-check">${icon('check')}</div></div></div>
 <div class="workflow-row"><span class="step-number ${c.offerings.length?'done':''}">${c.offerings.length?icon('check'):'01'}</span><div><strong>Bring your academic data together</strong><p>${c.offerings.length?`${c.offerings.length} assignments are saved. Review them before generating.`:'Start with the included CSV or add your own academic data.'}</p></div><a class="button small" href="#setup">Review data ${icon('arrow')}</a></div>
 <div class="workflow-row"><span class="step-number ${latest?.status==='feasible'?'done':''}">${latest?.status==='feasible'?icon('check'):'02'}</span><div><strong>Let the constraints do the work</strong><p>Schedule all divisions together, with real conflict checks.</p></div>${btn('Generate','generate','spark','small soft')}</div>
 <div class="workflow-row"><span class="step-number">03</span><div><strong>A timetable for everyone</strong><p>View by class or professor. Export a college-branded copy.</p></div><a class="button small" href="#timetables">View ${icon('arrow')}</a></div></section>
 <section class="panel"><div class="panel-header"><h2>Your scheduling rules</h2>${tag('5 hard rules','green')}</div><div class="constraint-list">${constraints.map(([ic,title,desc])=>`<div class="constraint-item"><i>${icon(ic)}</i><div><strong>${title}</strong><p>${desc}</p></div></div>`).join('')}</div><div class="mini-note">Powered by constraint solving. Requirements are never silently relaxed.</div></section></div>
 <div class="overview-bottom"><section class="panel"><div class="panel-header"><div><h2>Academic overview</h2><p>Three years. One coordinated schedule.</p></div><a class="button text" href="#setup">Manage ${icon('arrow')}</a></div><div class="table-scroll"><table class="data-table"><thead><tr><th>Year / semester</th><th>Divisions</th><th>Subjects</th><th>Weekly hours</th></tr></thead><tbody>${[3,5,7].map(sem=>`<tr><td><strong><span class="semester-chip">0${sem}</span>${years[sem]}</strong></td><td>${esc(c.groups.filter(g=>g.semester===sem).map(g=>g.division).join(', ')||'—')}</td><td>${c.subjects.filter(s=>s.semester===sem).length}</td><td>${c.offerings.filter(o=>c.groups.find(g=>g.id===o.group_id)?.semester===sem).reduce((n,o)=>n+o.lectures+2*o.labs,0)} hrs</td></tr>`).join('')}</tbody></table></div></section>
 <section class="panel next-card"><div class="eyebrow">${latest?'YOUR LATEST GENERATION':'START WITH A REALISTIC EXAMPLE'}</div><h3>${latest?esc(latest.name):'A head start for<br>the semester.'}</h3><p>${latest?`${when(latest.created_at)} · ${latest.status==='feasible'?'Your saved timetable is ready to explore.':'Review the generation report for next steps.'}`:'Sample data for 18 teachers, 9 divisions, and semesters 3, 5, and 7 is included in your workspace.'}</p>${latest?`<a class="button soft" href="#timetables">Open timetable ${icon('arrow')}</a>`:'<a class="button soft" href="/api/sample.csv">Download sample CSV '+icon('download')+'</a>'}</section></div>`;
}

function diagnostics(record){
 const r=record.result;const success=r.status==='feasible';
 const title=success?'All constraints satisfied':r.status==='infeasible'?'Generation not possible with these requirements':'More search time is needed';
 const subtitle=success?`${r.summary.sessions} sessions · ${r.summary.teaching_hours} teaching hours · ${r.elapsed_seconds}s · ${r.summary.balance_optimal?'Best daily balance proven':'Valid schedule found; daily balance may improve with more search time'}`:r.status==='infeasible'?'No timetable was saved as valid. Review the problems and suggested changes below.':'No complete timetable was found within the search limit. This is not proof of impossibility.';
 const list=success?r.solutions.map(s=>`<li>${icon('check')} ${esc(s)}</li>`):r.issues.map(i=>`<li><span class="problem">${esc(i.problem)}</span><span class="suggestion"><strong>Suggested change:</strong> ${esc(i.suggestion)}</span></li>`);
 return `<section class="panel diagnostics"><div class="diagnostic-summary ${success?'':'error'}"><i>${icon(success?'shield':'alert')}</i><div><h3>${title}</h3><p>${subtitle}</p></div>${statusTag(r.status)}</div><ul class="diagnostic-list ${success?'success':''}">${list.slice(0,6).join('')}${list.length>6?`<li><details><summary>View ${list.length-6} more ${success?'satisfied rules':'conflicting requirements'}</summary><ul class="diagnostic-list">${list.slice(6).join('')}</ul></details></li>`:''}</ul>${r.explanation?`<div class="mini-note">${esc(r.explanation)}</div>`:''}</section>`;
}
function timetablePage(){
 const heading=pageHeading('YOUR WEEK, AT A GLANCE','Timetables','Every class and every professor, in the right place.',btn(state.generating?'Generating…':'Generate timetable','generate','spark','primary'));
 if(!state.generation)return heading+`<section class="panel">${empty('Your first timetable is one click away.','Review your academic data, then generate a coordinated schedule for all three years.',btn('Generate timetable','generate','spark','primary'))}</section>`;
 const g=state.generation,c=g.config,m=maps(c),r=g.result;
 const saved=`<div class="schedule-topline"><div class="field"><label for="generation-select">Saved generation</label><select id="generation-select">${state.history.map(h=>`<option value="${h.id}" ${h.id===g.id?'selected':''}>${esc(h.name)} · ${h.status==='feasible'?'Generated':h.status==='infeasible'?'Not possible':'Search limit'} · ${when(h.created_at)}</option>`).join('')}</select></div><span class="save-note">Snapshot saved ${when(g.created_at)}</span></div>`;
 const stale=g.config_revision!==state.revision?`<div class="info-banner warning">${icon('info')}<span>Academic data has changed since this generation. This view and its exports use the saved snapshot. Generate again to include your changes.</span></div>`:'';
 if(r.status!=='feasible')return heading+saved+stale+diagnostics(g);
 const semesterGroups=c.groups.filter(x=>x.semester===Number(state.semester));
 if(state.view==='group'&&!semesterGroups.length){state.semester=c.groups[0].semester;}
 const choices=state.view==='group'?c.groups.filter(x=>x.semester===Number(state.semester)):c.teachers;
 if(!choices.some(x=>x.id===state.target))state.target=choices[0]?.id||'';
 const record=choices.find(x=>x.id===state.target);
 const entries=r.entries.filter(e=>e[`${state.view}_id`]===state.target);
 const title=state.view==='group'?groupLabel(record):record.name;
 const total=entries.reduce((n,e)=>n+e.duration,0);
 const exportUrl=format=>`/api/generations/${g.id}/export/${format}?view=${state.view}&target=${encodeURIComponent(state.target)}`;
 return heading+saved+stale+`<section class="panel"><div class="toolbar"><div class="view-toggle" role="group" aria-label="Timetable view"><button data-action="view-group" class="${state.view==='group'?'active':''}">By division</button><button data-action="view-teacher" class="${state.view==='teacher'?'active':''}">By professor</button></div>
 ${state.view==='group'?`<div class="field"><label for="semester-select">Academic year</label><select id="semester-select">${[...new Set(c.groups.map(x=>x.semester))].sort().map(sem=>`<option value="${sem}" ${Number(state.semester)===sem?'selected':''}>${years[sem]} · Sem ${sem}</option>`).join('')}</select></div>`:''}
 <div class="field"><label for="target-select">${state.view==='group'?'Division':'Professor'}</label><select id="target-select">${choices.map(x=>`<option value="${esc(x.id)}" ${x.id===state.target?'selected':''}>${esc(state.view==='group'?`Division ${x.division}`:x.name)}</option>`).join('')}</select></div><div class="spacer"></div><div class="button-row"><a class="button small" href="${exportUrl('pdf')}">${icon('download')} PDF</a><a class="button small" href="${exportUrl('xlsx')}">${icon('download')} Excel</a></div></div>
 <div class="timetable-header"><h2 class="college-full">${esc(state.meta.college)}</h2><p>DEPARTMENT TIMETABLE · MONDAY–FRIDAY</p><div class="timetable-label">${esc(title)}</div><p>${total} teaching hours per week ${state.view==='teacher'?`· Weekly limit: ${record.max_hours} hours`:''}</p></div><div class="timetable-wrap"><table class="timetable" aria-label="${esc(title)} weekly timetable"><thead><tr><th>Time</th>${state.meta.days.map(day=>`<th scope="col">${day}</th>`).join('')}</tr></thead><tbody>${state.meta.periods.map(([start,end],slot)=>{
  let html=slot===4?'<tr class="recess"><th scope="row">13:00–13:45</th><td colspan="5">R E C E S S · 45 MINUTES</td></tr>':'';
  html+=`<tr><th scope="row">${start}–${end}<small>PERIOD ${slot+1}</small></th>`;
  for(let day=0;day<5;day++){
   if(entries.some(e=>e.day===day&&e.slot<slot&&e.slot+e.duration>slot))continue;
   const e=entries.find(e=>e.day===day&&e.slot===slot);
   if(!e){html+='<td class="empty"></td>';continue;}
   const s=m.subjects[e.subject_id],t=m.teachers[e.teacher_id],gr=m.groups[e.group_id];
   html+=`<td rowspan="${e.duration}"><div class="lesson ${e.kind==='lab'?'lab':''} ${s.elective?'elective':''}"><div class="lesson-code">${esc(s.code)}<span>${e.kind==='lab'?'LAB':s.elective?'ELECTIVE':'LEC'}</span></div><strong>${esc(s.name)}</strong><small>${esc(state.view==='group'?t.name:`Sem ${gr.semester} · Div ${gr.division}`)}</small><small>${esc(m.rooms[e.room_id].name)}${e.kind==='lab'?' · 2 hours':''}${s.elective&&e.kind==='lab'?' · Elective':''}</small></div></td>`;
  }
  return html+'</tr>';
 }).join('')}</tbody></table></div><div class="legend"><div class="legend-items"><span class="legend-item"><span class="legend-dot"></span>Lecture</span><span class="legend-item"><span class="legend-dot green"></span>Practical / lab</span><span class="legend-item"><span class="legend-dot orange"></span>Elective</span></div><span>${state.view==='teacher'?'Blank cells = no teaching assigned to this professor':'Teaching days may finish early · No filler sessions'}</span></div></section>
 <div class="button-row section-spacer"><span class="save-note">Need every division?</span><a class="button small" href="/api/generations/${g.id}/export/pdf">All divisions · PDF</a><a class="button small" href="/api/generations/${g.id}/export/xlsx">All divisions · Excel</a><a class="button small" href="/api/generations/${g.id}/export/xlsx?view=teacher">All professors · Excel</a></div>`+diagnostics(g);
}

function setupPage(){
 const c=state.config;
 return pageHeading('THE FOUNDATION OF YOUR SCHEDULE','Academic setup','Manage faculty, courses, spaces, and weekly teaching requirements.',`<a class="button" href="/api/config.csv">${icon('download')} Export data CSV</a>`)+
 `<div class="tabs" role="tablist" aria-label="Academic data">${Object.entries(categories).map(([key,label])=>`<button role="tab" aria-selected="${state.tab===key}" data-action="tab" data-tab="${key}" class="${state.tab===key?'active':''}">${label}<span class="tab-count">${c[key].length}</span></button>`).join('')}</div>
 <div class="table-title-row"><div><h2 class="section-heading">${categories[state.tab]}</h2><p class="inline-help" style="margin:8px 0 0">${{offerings:'One teacher per subject and division. Each lab session occupies two consecutive periods.',teachers:'Working hours are the maximum teaching hours per week. Availability applies Monday–Friday.',subjects:'Semesters 3, 5, and 7 correspond to Second, Third, and Final Year.',groups:'Each division has a home classroom for lectures. Labs use their assigned laboratory.',rooms:'Give every physical classroom and laboratory a unique name.'}[state.tab]}</p></div>${btn('Add '+singular[state.tab],'add','plus','primary')}</div>
 <section class="panel"><div class="toolbar"><span class="save-note">Changes are saved to SQLite</span><div class="spacer"></div>${btn('Check requirements','validate','shield','small')}<div class="field search"><label for="table-search" class="sr-only">Search ${categories[state.tab].toLowerCase()}</label><input id="table-search" type="search" placeholder="Search ${categories[state.tab].toLowerCase()}…" value="${esc(state.search)}"></div></div><div class="table-scroll" id="setup-table">${setupTable()}</div></section>
 ${state.tab==='teachers'?facultyLoad():''}<div id="validation-result"></div>`;
}
function setupTable(){
 const m=maps();let headers,rows=[];
 const actions=item=>`<td class="actions"><button class="icon-button" data-action="edit" data-id="${esc(item.id)}" aria-label="Edit ${esc(singular[state.tab])}">${icon('edit')}</button><button class="icon-button" data-action="delete" data-id="${esc(item.id)}" aria-label="Delete ${esc(singular[state.tab])}">${icon('trash')}</button></td>`;
 for(const item of state.config[state.tab]){
  let cells,search;
  if(state.tab==='teachers'){headers=['Teacher','Weekly limit','Arrival','Departure',''];cells=[`<strong>${esc(item.name)}</strong>`,`${item.max_hours} hours`,item.arrival,item.departure];search=item.name;}
  if(state.tab==='subjects'){headers=['Subject','Code','Semester','Type',''];cells=[`<strong>${esc(item.name)}</strong>`,esc(item.code),`${item.semester} · ${years[item.semester]}`,tag(item.elective?'Elective':'Core',item.elective?'orange':'purple')];search=item.name+' '+item.code+' '+item.semester;}
  if(state.tab==='groups'){headers=['Academic year','Division','Classroom',''];cells=[`<strong>${years[item.semester]}</strong><small>Semester ${item.semester}</small>`,esc(item.division),esc(m.rooms[item.room_id].name)];search=groupLabel(item);}
  if(state.tab==='rooms'){headers=['Room name','Type',''];cells=[`<strong>${esc(item.name)}</strong>`,tag(item.kind==='lab'?'Laboratory':'Classroom',item.kind==='lab'?'green':'blue')];search=item.name+' '+item.kind;}
  if(state.tab==='offerings'){
   headers=['Subject / division','Assigned teacher','Lectures / week','Labs / week','Lab room',''];
   const subject=m.subjects[item.subject_id],group=m.groups[item.group_id],teacher=m.teachers[item.teacher_id];
   cells=[`<strong>${esc(subject.name)}</strong><small>${esc(subject.code)} · Sem ${group.semester} · Div ${esc(group.division)} ${subject.elective?'· Elective':''}</small>`,esc(teacher.name),String(item.lectures),`${item.labs}${item.labs?' × 2 hrs':''}`,item.lab_room_id?esc(m.rooms[item.lab_room_id].name):'—'];
   search=[subject.name,subject.code,group.semester,group.division,teacher.name].join(' ');
  }
  if(!state.search||search.toLowerCase().includes(state.search.toLowerCase()))rows.push(`<tr>${cells.map(c=>`<td>${c}</td>`).join('')}${actions(item)}</tr>`);
 }
 if(!rows.length)return empty('No matching '+categories[state.tab].toLowerCase(),state.config[state.tab].length?'Try a different search term.':'Add your first '+singular[state.tab]+' to get started.');
 return `<table class="data-table wide"><thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table>`;
}
function facultyLoad(){
 return `<section class="panel section-spacer"><div class="panel-header"><div><h2>Faculty workload</h2><p>Assigned hours compared with weekly teaching limits</p></div></div><div class="panel-body load-list">${state.config.teachers.map(t=>{const load=state.config.offerings.filter(o=>o.teacher_id===t.id).reduce((n,o)=>n+o.lectures+2*o.labs,0);return `<div class="load-item"><div><strong>${esc(t.name)}</strong><span>${load} / ${t.max_hours}h</span></div><div class="load-bar"><span class="${load>t.max_hours?'over':''}" style="width:${Math.min(100,load/t.max_hours*100)}%"></span></div></div>`;}).join('')}</div></section>`;
}

function importPage(){
 return pageHeading('A SMOOTHER START','Bring your semester into focus.','One CSV for teachers, subjects, rooms, and all three years.',`<a class="button" href="/api/sample.csv">${icon('download')} Download sample CSV</a>`)+
 `<div class="import-grid"><section class="panel"><div class="panel-header"><div><h2>Import academic data</h2><p>Preview and validate your file before applying it.</p></div>${tag('CSV · UTF-8','purple')}</div><div class="dropzone" id="dropzone"><div class="upload-icon">${icon('upload')}</div><h3>Drop your semester file here</h3><p>or choose a CSV from your computer<br>Up to 1 MB · Same headers as the sample</p><span class="button primary">Choose CSV file</span><input type="file" id="csv-file" accept=".csv,text/csv" aria-label="Choose academic data CSV file"></div><div class="import-instructions"><strong>One row = one subject assigned to one division.</strong><br>Repeat the teacher’s details consistently across their rows. The importer combines matching teacher names, subject codes, room names, and divisions.</div><div id="import-result">${state.preview?importPreview():''}</div></section>
 <div><section class="panel"><div class="panel-header"><h2>What goes in your CSV?</h2>${icon('file')}</div><div class="panel-body"><ul class="schema-list"><li><span>01</span><div><strong>The class</strong><small>Semester (3, 5, or 7), division, and classroom number.</small></div></li><li><span>02</span><div><strong>The teacher</strong><small>Name, weekly hour limit, arrival and departure in 24-hour HH:MM format.</small></div></li><li><span>03</span><div><strong>The subject</strong><small>Name, unique code, and elective status (true / false).</small></div></li><li><span>04</span><div><strong>The weekly requirement</strong><small>Lectures per week, two-hour labs per week, and laboratory number.</small></div></li></ul></div><div class="mini-note">Imports replace the current academic data. Existing timetable snapshots remain available.</div></section>
 <section class="panel next-card section-spacer"><div class="eyebrow">INCLUDED WITH UNISCHED</div><h3>Realistic data.<br>Ready for a trial run.</h3><p>54 assignments · 18 teachers · 9 divisions<br>Semesters 3, 5 & 7 · Divisions A, B & C<br>Illustrative Computer Engineering data, not an official DMCE curriculum.</p>${btn('Preview sample data','sample','arrow','soft')}</section></div></div>`;
}
function importPreview(){
 const p=state.preview;
 return `<div class="import-preview"><div class="info-banner success">${icon('check')}<span>CSV structure validated. Review the summary before replacing your academic data.</span></div><h3>${esc(p.filename)}</h3><div class="preview-counts">${Object.entries(p.counts).map(([k,v])=>tag(`${v} ${categories[k].toLowerCase()}`,'purple')).join('')}</div>${p.issues.length?`<div class="info-banner warning">${icon('alert')}<span>${p.issues.length} scheduling issue(s) found. You may import and correct them in Academic setup.</span></div><ul class="diagnostic-list">${p.issues.map(i=>`<li>${esc(i.problem)}<br>${esc(i.suggestion)}</li>`).join('')}</ul>`:'<p class="inline-help">Basic capacity checks passed. Full collision and gap checks run during timetable generation.</p>'}<p class="inline-help">Applying this file replaces teachers, subjects, rooms, divisions, and assignments. Download your existing data first if you need a copy.</p><div class="button-row">${btn('Replace academic data','apply-import','check','primary')}<a class="button small" href="/api/config.csv">Back up current CSV</a></div></div>`;
}

function openModal(title,subtitle,body,submit){
 modalSubmit=submit;
 $('#modal-content').innerHTML=`<div class="modal-header"><div><h2>${title}</h2><p>${subtitle}</p></div><button class="icon-button" data-action="close-modal" aria-label="Close dialog">${icon('close')}</button></div><div class="modal-body">${body}</div>`;
 if(!$('#modal').open)$('#modal').showModal();
}
function closeModal(){if(state.generating)return;$('#modal').close();modalSubmit=null;}
function inputField(name,label,value='',type='text',attrs='',help=''){
 return `<div class="field"><label for="f-${name}">${label}</label><input id="f-${name}" name="${name}" type="${type}" value="${esc(value)}" ${attrs}>${help?`<small>${help}</small>`:''}</div>`;
}
function selectField(name,label,options,value){return `<div class="field"><label for="f-${name}">${label}</label><select id="f-${name}" name="${name}" required>${options.map(([id,text])=>`<option value="${esc(id)}" ${String(id)===String(value)?'selected':''}>${esc(text)}</option>`).join('')}</select></div>`;}
function editModal(identifier){
 const category=state.tab;const item=state.config[category].find(i=>i.id===identifier)||{};let fields='';
 if(category==='teachers')fields=inputField('name','Teacher name',item.name,'text','required maxlength="100"')+inputField('max_hours','Teaching hours per week (maximum)',item.max_hours??18,'number','required min="1" max="40" step="1"')+inputField('arrival','Coming / arrival time',item.arrival||'09:00','time','required min="09:00" max="17:45"')+inputField('departure','Leaving / departure time',item.departure||'17:45','time','required min="09:00" max="17:45"');
 if(category==='subjects')fields=inputField('name','Subject name',item.name,'text','required maxlength="120"')+inputField('code','Subject code',item.code,'text','required maxlength="30"')+selectField('semester','Year / semester',Object.entries(years).map(([id,name])=>[id,`${name} · Semester ${id}`]),item.semester||3)+`<label class="checkbox-field"><input type="checkbox" name="elective" ${item.elective?'checked':''}> Elective subject (separate slots)</label>`;
 if(category==='rooms')fields=inputField('name','Classroom / lab number or name',item.name,'text','required maxlength="50"')+selectField('kind','Room type',[['classroom','Classroom'],['lab','Laboratory']],item.kind||'classroom');
 if(category==='groups')fields=selectField('semester','Year / semester',Object.entries(years).map(([id,name])=>[id,`${name} · Semester ${id}`]),item.semester||3)+inputField('division','Division',item.division,'text','required maxlength="12" placeholder="A, B, C…"')+selectField('room_id','Home classroom',state.config.rooms.filter(r=>r.kind==='classroom').map(r=>[r.id,r.name]),item.room_id);
 if(category==='offerings')fields=selectField('group_id','Year / division',state.config.groups.map(g=>[g.id,groupLabel(g)]),item.group_id)+selectField('subject_id','Subject',state.config.subjects.map(s=>[s.id,`${s.code} · ${s.name} (Sem ${s.semester})`]),item.subject_id)+selectField('teacher_id','Assigned teacher',state.config.teachers.map(t=>[t.id,t.name]),item.teacher_id)+selectField('lab_room_id','Laboratory (required for labs)',[['','No lab'],...state.config.rooms.filter(r=>r.kind==='lab').map(r=>[r.id,r.name])],item.lab_room_id||'')+inputField('lectures','Lectures per week',item.lectures??3,'number','required min="0" max="40" step="1"','Each lecture takes one hour.')+inputField('labs','Lab sessions per week',item.labs??0,'number','required min="0" max="20" step="1"','Each session takes two consecutive hours.');
 openModal(`${identifier?'Edit':'Add'} ${singular[category]}`,'Changes apply to future generations. Saved timetable snapshots stay available.',`<form id="modal-form"><div class="form-grid">${fields}</div><div class="form-error" id="form-error" role="alert"></div><div class="form-actions">${btn('Cancel','close-modal')}<button class="button primary" type="submit">${icon('check')} Save ${singular[category]}</button></div></form>`,async form=>{
  const values=Object.fromEntries(new FormData(form));
  for(const name of ['semester','max_hours','lectures','labs'])if(name in values)values[name]=Number(values[name]);
  if(category==='subjects')values.elective=form.elements.elective.checked;
  if(category==='groups')values.division=values.division.trim().toUpperCase();
  if(category==='offerings')values.lab_room_id=values.lab_room_id||null;
  values.id=identifier||category[0]+'_'+crypto.randomUUID();
  const next=structuredClone(state.config);const idx=next[category].findIndex(i=>i.id===identifier);
  if(idx>=0)next[category][idx]=values;else next[category].push(values);
  await saveConfig(next);closeModal();render();toast('Academic data saved. Generate a new timetable to apply your changes.');
 });
 if(category==='offerings'){
  $('#f-lab_room_id').required=false;
  const filterSubjects=()=>{
   const group=state.config.groups.find(g=>g.id===$('#f-group_id').value);const previous=$('#f-subject_id').value;
   $('#f-subject_id').innerHTML=state.config.subjects.filter(s=>s.semester===group?.semester).map(s=>`<option value="${esc(s.id)}" ${s.id===previous?'selected':''}>${esc(s.code+' · '+s.name)}</option>`).join('');
  };
  $('#f-group_id').addEventListener('change',filterSubjects);filterSubjects();
 }
}
async function saveConfig(next,revision=state.revision){
 const result=await api('/api/config',jsonOptions('PUT',{revision,configuration:next}));state.config=result.configuration;state.revision=result.revision;
}
function deleteModal(identifier){
 const category=state.tab;const item=state.config[category].find(i=>i.id===identifier);if(!item)return;
 const title=item.name||item.code|| (category==='groups'?groupLabel(item):'this teaching assignment');
 openModal('Delete '+singular[category],esc(title),`<p class="inline-help">Linked records must be reassigned or removed first. Saved timetables keep their original data.</p><form id="modal-form"><div class="form-error" id="form-error" role="alert"></div><div class="form-actions">${btn('Cancel','close-modal')}<button class="button danger" type="submit">Delete ${singular[category]}</button></div></form>`,async()=>{
  const next=structuredClone(state.config);next[category]=next[category].filter(i=>i.id!==identifier);await saveConfig(next);closeModal();render();toast('Record deleted.');
 });
}

function generationModal(){
 if(state.generating)return;
 openModal('Build a better week','All divisions are scheduled together to prevent shared-resource conflicts.',`<div class="info-banner">${icon('shield')}<span>09:00–17:45 · Recess 13:00–13:45<br>Gap-free division days, two-hour labs, and separate elective slots.</span></div><form id="modal-form"><div class="form-grid">${inputField('name','Timetable name','Odd semester timetable','text','required maxlength="80"')}${selectField('time_limit','Maximum search time',[[20,'20 seconds'],[60,'60 seconds'],[120,'120 seconds']],20)}</div><p class="inline-help" style="margin-top:18px">${state.config.groups.length} divisions · ${state.config.teachers.length} teachers · ${state.config.offerings.length} assignments. No requirements will be relaxed. A shorter week finishes earlier; free time is never filled with invented sessions.</p><div class="form-error" id="form-error" role="alert"></div><div class="form-actions">${btn('Cancel','close-modal')}<button class="button primary" type="submit">${icon('spark')} Generate timetable</button></div></form>`,async form=>{
  const payload={name:form.elements.name.value.trim(),time_limit:Number(form.elements.time_limit.value)};
  state.generating=true;
  $('#modal-content').innerHTML=`<div class="modal-body generation-progress"><span class="spinner"></span><h3>Finding a place for every class…</h3><p>Checking teachers, rooms, electives, and continuous teaching days.<br>This search can take up to ${payload.time_limit} seconds.</p><span class="tag purple">OR-Tools CP-SAT constraint solver</span></div>`;
  try{
   state.generation=await api('/api/generations',jsonOptions('POST',payload));state.history=await api('/api/generations');state.target='';state.generating=false;closeModal();location.hash='timetables';render();toast(state.generation.result.status==='feasible'?'Your timetable is ready.':'Generation report is ready. Review the explanation below.');
  }catch(error){state.generating=false;closeModal();toast(error.message);render();}
 });
}

async function previewFile(file){
 if(file.size>1_000_000){toast('Please choose a CSV smaller than 1 MB.');return;}
 state.preview=null;const revision=state.revision;
 const container=$('#import-result');if(container)container.innerHTML='<div class="initial-loading" style="min-height:90px"><span class="spinner"></span>Validating CSV…</div>';
 try{const form=new FormData();form.append('file',file);const result=await api('/api/import/preview',{method:'POST',body:form});state.preview={...result,filename:file.name,revision};if(state.page==='import')$('#import-result').innerHTML=importPreview();}
 catch(error){if($('#import-result'))$('#import-result').innerHTML=`<div class="form-error import-error" role="alert">${esc(error.message)}</div>`;else toast(error.message);}
}
async function action(name,node){
 if(name==='reload'){await boot();return;}
 if(name==='close-modal'){closeModal();return;}
 if(name==='generate'){generationModal();return;}
 if(name==='tab'){state.tab=node.dataset.tab;state.search='';render();return;}
 if(name==='add'||name==='edit'){editModal(node.dataset.id);return;}
 if(name==='delete'){deleteModal(node.dataset.id);return;}
 if(['view-group','view-teacher','view-classroom','view-lab'].includes(name)){state.view=name.slice(5);state.target='';state.batch='';render();return;}
 if(name==='sample'){
  const response=await fetch('/api/sample.csv');if(!response.ok)throw new Error('Could not load sample data.');
  await previewFile(new File([await response.blob()],'unisched_semesters_3_5_7.csv',{type:'text/csv'}));return;
 }
 if(name==='apply-import'){
  if(!state.preview)return;node.disabled=true;
  try{await saveConfig(state.preview.configuration,state.preview.revision);state.preview=null;location.hash='setup';state.tab='offerings';state.search='';render();toast('CSV imported. Academic data has been replaced successfully.');}finally{node.disabled=false;}return;
 }
 if(name==='validate'){
  node.disabled=true;
  try{const result=await api('/api/validate');$('#validation-result').innerHTML=result.issues.length?diagnostics({result:{status:'infeasible',issues:result.issues}}):`<div class="info-banner success section-spacer">${icon('check')}<span>Basic workload and capacity checks passed. Generate a timetable to verify all room, teacher, elective, and no-gap constraints.</span></div>`;$('#validation-result').scrollIntoView({behavior:'smooth',block:'nearest'});}finally{node.disabled=false;}
 }
}
document.addEventListener('click',event=>{
 const button=event.target.closest('[data-action]');if(button){event.preventDefault();Promise.resolve(action(button.dataset.action,button)).catch(error=>toast(error.message));}
 if(event.target.closest('nav a'))$('#sidebar').classList.remove('open');
 if($('#sidebar').classList.contains('open')&&!event.target.closest('#sidebar')&&!event.target.closest('#menu-toggle'))$('#sidebar').classList.remove('open');
});
$('#menu-toggle').addEventListener('click',()=>$('#sidebar').classList.toggle('open'));
document.addEventListener('submit',async event=>{
 if(event.target.id!=='modal-form')return;event.preventDefault();if(!modalSubmit)return;
 const submit=event.target.querySelector('[type="submit"]');submit.disabled=true;
 if($('#form-error'))$('#form-error').textContent='';
 try{await modalSubmit(event.target);}catch(error){formError(error);}finally{submit.disabled=false;}
});
document.addEventListener('change',async event=>{
 try{
  if(event.target.id==='csv-file'&&event.target.files[0])await previewFile(event.target.files[0]);
  if(event.target.id==='semester-select'){state.semester=Number(event.target.value);state.target='';render();}
  if(event.target.id==='target-select'){state.target=event.target.value;render();}
  if(event.target.id==='generation-select'){state.generation=await api(`/api/generations/${event.target.value}`);state.target='';render();}
 }catch(error){toast(error.message);}
});
document.addEventListener('input',event=>{if(event.target.id==='table-search'){state.search=event.target.value;$('#setup-table').innerHTML=setupTable();}});
for(const type of ['dragover','dragleave','drop'])document.addEventListener(type,event=>{
 const zone=event.target.closest('#dropzone');if(!zone)return;event.preventDefault();zone.classList.toggle('dragging',type==='dragover');
 if(type==='drop'&&event.dataTransfer.files[0])previewFile(event.dataTransfer.files[0]);
});
$('#modal').addEventListener('cancel',event=>{if(state.generating)event.preventDefault();});
window.addEventListener('hashchange',()=>{render();window.scrollTo(0,0);});
hydrateIcons();boot();
