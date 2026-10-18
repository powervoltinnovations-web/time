"""Reproducible IT presentation data; never overwrites an existing database."""
from .domain import Configuration

CATALOG = {
3: [('Engineering Mathematics III','IT301','Dr.Vidya Kubde'),('Data Structures','IT302','Dr.R. V. Bhaskarwar'),
    ('Database Management Systems','IT303','Mrs. G.M.Arwindekar'),('Digital Logic & Architecture','IT304','Dr. R.A.Jolhe'),
    ('Object-Oriented Programming','IT305','Ms. D. P. Kadam'),('Discrete Mathematics','IT306','Mrs. K. P. Rane'),
    ('Web Technology','ITE301','Mrs. H. A.Khot'),('Human Computer Interaction','ITE302','Mrs. A. R. Rahude')],
5: [('Operating Systems','IT501','Mrs. N.Y. Moharkar'),('Computer Networks','IT502','Mrs. J. S. Phonde'),
    ('Software Engineering','IT503','Mrs. Angel Bency'),('Automata & Compiler Design','IT504','Mrs. Vaishali Korade'),
    ('Advanced Database Systems','IT505','Pallavi M.N.'),('Information Security','IT506','Priya Jadhav'),
    ('Artificial Intelligence','ITE501','Pankaj Rathod'),('Cloud Fundamentals','ITE502','Harshali Vihire')],
7: [('Machine Learning','IT701','Reshma'),('Big Data Analytics','IT702','Sample Professor 01'),
    ('Cloud Computing','IT703','Sample Professor 03'),('Distributed Systems','IT704','Sample Professor 05'),
    ('Cyber Security','IT705','Sample Professor 06'),('DevOps & Software Architecture','IT706','Sample Professor 08'),
    ('Internet of Things','ITE701','Sample Professor 09'),('Blockchain Technology','ITE702','Sample Professor 10')]
}

def presentation_config():
    data={'departments':[{'id':'it','name':'Information Technology','code':'IT'}],
          'teachers':[],'subjects':[],'rooms':[],'groups':[],'offerings':[], 'elective_sets':[],
          'batches':[], 'settings':{'start':'09:00','end':'17:45','spread_lectures':True}}
    for i in range(7):
        data['rooms'].append({'id':f'cr{i+1}','name':f'IT-{301+i}','kind':'classroom','capacity':70,
                             'department_id':'it','eligible_years':[]})
    for i in range(6):
        data['rooms'].append({'id':f'lab{i+1}','name':f'IT Shared Lab {i+1}','kind':'lab','capacity':20,
                             'department_id':'it','eligible_years':[]})
    for sem,subjects in CATALOG.items():
        data['elective_sets'].append({'id':f'es{sem}','name':f'Professional Electives – Semester {sem}',
                                      'code':f'PE-{sem}','department_id':'it','semester':sem})
        for index,(name,code,teacher) in enumerate(subjects):
            tid=f't{sem}_{index}'
            elective=index>=6
            lectures=4 if index<4 else 3 if index<6 else 2
            labs=1 if index in (1,2,4) else 0
            data['teachers'].append({'id':tid,'name':teacher,'department_id':'it','max_hours':20,
                'max_daily_slots':5,'arrival':'09:00','departure':'17:45','lab_eligible':True,
                'email':f'faculty{sem}{index}@example.edu','short_code':f'F{sem}{index}'})
            data['subjects'].append({'id':code,'name':name,'code':code,'department_id':'it','semester':sem,
                'elective':elective,'elective_set_id':f'es{sem}' if elective else None,
                'course_type':'mixed' if labs else 'theory','weekly_hours':lectures+labs*2})
            if labs:
                lab_teacher=f'lt{sem}_{index}'
                data['teachers'].append({'id':lab_teacher,'name':{3: {1: 'Mrs. A. D. Mhatre', 2: 'Mr.J. R. Gaidhane', 4: 'Mr. S. U. Kumane'}, 5: {1: 'Mr. Krushna Jadhav', 2: 'Mrs. Karishma Shelar', 4: 'Bipasha'}, 7: {1: 'Sample Professor 02', 2: 'Sample Professor 04', 4: 'Sample Professor 07'}}[sem][index],
                    'department_id':'it','max_hours':20,'max_daily_slots':6,'arrival':'09:00','departure':'17:45',
                    'lab_eligible':True,'email':f'lab{sem}{index}@example.edu','short_code':f'L{sem}{index}'})
            for div_index,div in enumerate('ABC'):
                data['offerings'].append({'id':f'{code}_{div}','group_id':f'it{sem}{div}','subject_id':code,
                    'teacher_id':tid,'lectures':lectures,'labs':0,'lab_room_id':None})
                if labs:
                    for batch in range(1,4):
                        data['offerings'].append({'id':f'{code}_{div}_b{batch}','group_id':f'it{sem}{div}',
                            'subject_id':code,'teacher_id':lab_teacher,'lectures':0,'labs':1,
                            'batch_id':f'it{sem}{div}{batch}','lab_room_id':f'lab{((sem//2+div_index)%2)*3+batch}'})
        for div in 'ABC':
            data['groups'].append({'id':f'it{sem}{div}','department_id':'it','semester':sem,'division':div,
                                   'strength':60,'room_id':None})
            for batch in range(1,4):
                data['batches'].append({'id':f'it{sem}{div}{batch}','group_id':f'it{sem}{div}',
                                        'name':f'{div}{batch}','strength':20})
    return Configuration(**data)
