"""Optional projects preserve existing data and share real room capacity."""
from copy import deepcopy
import pytest
from app.domain import Configuration, parse_csv
from app.demo import presentation_config
from app.exchange import configuration_csv_v2
from app.resources import session_specs, eligible_rooms
from app.scheduler import generate
from app.analytics import analyze
from app.classrooms import optimize_classrooms
from test_scheduler import small_config


def project_config():
    data=small_config().model_dump()
    data['settings']['classroom_run_length']=3
    data['groups'][0]['room_id']=None
    data['rooms'].append({**data['rooms'][0],'id':'r2','name':'302'})
    data['subjects'].append({**data['subjects'][0],'id':'p','code':'PRJ','name':'User project','course_type':'project'})
    data['offerings'].append({'id':'p','group_id':'g','subject_id':'p','teacher_id':'t','projects':1,
        'lectures':0,'labs':0,'project_hours':3,'project_room_id':'r'})
    return Configuration(**data)


def test_original_presentation_data_has_no_added_projects():
    config=presentation_config()
    assert [len(getattr(config,k)) for k in ('subjects','teachers','groups','rooms','offerings','batches')]==[24,33,9,13,153,27]
    assert all(o.projects==0 and o.project_hours is None and o.project_room_id is None for o in config.offerings)
    assert all(s.course_type!='project' for s in config.subjects)
    assert sum(o.labs for o in config.offerings)==81


def test_user_project_hours_room_and_csv_round_trip():
    config=project_config();original=config.model_dump()
    result=generate(config,20)
    assert result['status']=='feasible',result
    projects=[e for e in result['entries'] if e['kind']=='project']
    assert len(projects)==1 and projects[0]['duration']==3 and projects[0]['room_id']=='r'
    assert analyze({'config':config.model_dump(),'result':result})['hard_conflicts']==0
    restored=parse_csv(configuration_csv_v2(config).encode())
    offering=next(o for o in restored.offerings if o.projects)
    assert offering.project_hours==3
    assert next(r.name for r in restored.rooms if r.id==offering.project_room_id)=='301'
    assert config.model_dump()==original
    assert len(restored.rooms)==len(config.rooms)
    invalid=deepcopy(original);invalid['offerings'][-1]['project_hours']=1.5
    with pytest.raises(ValueError,match='whole number'):
        Configuration(**invalid)


def test_room_optimizer_respects_classroom_project_reservations():
    data=project_config().model_dump()
    data['groups'].append({**data['groups'][0],'id':'g2','division':'B'})
    data['teachers'].append({**data['teachers'][0],'id':'t2','name':'Project teacher'})
    data['offerings'][-1].update(group_id='g2',teacher_id='t2')
    config=Configuration(**data)
    entries=[{'offering_id':'o','group_id':'g','subject_id':'s','teacher_id':'t','kind':'lecture',
              'batch_id':None,'day':0,'slot':p,'duration':1,'room_id':'r2'} for p in range(3)]
    project={'offering_id':'p','group_id':'g2','subject_id':'p','teacher_id':'t2','kind':'project',
             'batch_id':None,'day':0,'slot':0,'duration':3,'room_id':'r'}
    entries.append(project)
    updated,_=optimize_classrooms(config,entries,[],5)
    assert updated[-1]==project
    assert all(e['room_id']=='r2' for e in updated[:-1])
    assert entries[-1]==project


def test_legacy_projects_keep_original_lab_and_global_duration():
    data=small_config().model_dump();data['offerings'][0]['projects']=1
    config=Configuration(**data);offering=config.offerings[0]
    assert session_specs(config,offering)[-1]==('project',1,config.settings.project_slots)
    assert [r.id for r in eligible_rooms(config,offering,'project')]==['l']
