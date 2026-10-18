"""Exercise real website flows in Chromium against a disposable SQLite database."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'artifacts'
ARTIFACTS.mkdir(exist_ok=True)

def run():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='unisched-ui-') as folder:
        environment = {**os.environ,'UNISCHED_DB':str(Path(folder)/'browser.db')}
        with open(ARTIFACTS/'browser-server.log','w') as log:
            server = subprocess.Popen([sys.executable,'run.py','--port',str(port)],cwd=ROOT,env=environment,stdout=log,stderr=log)
            try:
                base = f'http://127.0.0.1:{port}'
                for _ in range(100):
                    try:
                        with urlopen(base+'/api/health',timeout=1) as response:
                            assert response.status == 200
                        break
                    except OSError:
                        if server.poll() is not None:
                            raise RuntimeError('Browser test server exited. See artifacts/browser-server.log.')
                        time.sleep(.1)
                else:
                    raise RuntimeError('Browser test server did not become ready.')
                with sync_playwright() as p:
                    executable = os.environ.get('CHROMIUM_PATH') or shutil.which('chromium')
                    browser = p.chromium.launch(headless=True,executable_path=executable)
                    page = browser.new_page(viewport={'width':1440,'height':1050},device_scale_factor=1)
                    page.set_default_timeout(10000)
                    errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(base)
                    expect(page.get_by_role('heading',name='A better week starts here.')).to_be_visible()
                    expect(page.locator('.stat-number').first).to_have_text('33')
                    page.screenshot(path=str(ARTIFACTS/'overview-desktop.png'),full_page=True)

                    original_config = page.request.get(base+'/api/config').json()
                    expect(page.get_by_role('link',name='Open AI chat assistant')).to_be_visible()
                    page.get_by_role('link',name='Open AI chat assistant').click()
                    expect(page.get_by_role('heading',name='Ask about your timetable.')).to_be_visible()
                    expect(page.locator('#assistant-status')).to_contain_text('Local checks ready')
                    page.get_by_role('link',name='Mini projects',exact=True).click()
                    expect(page.locator('#main')).to_contain_text('No mini projects added')
                    assert page.request.get(base+'/api/config').json() == original_config
                    page.screenshot(path=str(ARTIFACTS/'mini-projects-empty.png'),full_page=True)

                    # New workspace controls, exercised through actual forms and buttons.
                    page.goto(base+'/#departments')
                    page.get_by_role('button',name='Add department',exact=True).click()
                    page.get_by_label('Department name',exact=True).fill('Electronics Engineering')
                    page.get_by_label('Department code',exact=True).fill('EXTC')
                    page.get_by_role('button',name='Save department',exact=True).click()
                    expect(page.locator('#setup-table')).to_contain_text('Electronics Engineering')
                    department_id=page.locator('#department-switch option').filter(has_text='EXTC').get_attribute('value')
                    page.locator('#department-switch').select_option(department_id)
                    page.goto(base+'/#subjects')
                    page.get_by_role('button',name='Add subject',exact=True).click()
                    page.get_by_label('Subject name',exact=True).fill('Digital Communication')
                    page.get_by_label('Subject code',exact=True).fill('EXTC501')
                    page.get_by_label('Academic year',exact=True).select_option('3')
                    expect(page.get_by_label('Academic semester',exact=True)).to_have_value('5')
                    page.get_by_role('button',name='Save subject',exact=True).click()
                    expect(page.locator('#setup-table')).to_contain_text('Third Year')
                    page.get_by_role('button',name='Delete subject',exact=True).click()
                    page.locator('#modal').get_by_role('button',name='Delete subject',exact=True).click()
                    expect(page.locator('#modal')).not_to_be_visible()
                    page.goto(base+'/#departments')
                    page.locator('#setup-table tr').filter(has_text='Electronics Engineering').get_by_role('button',name='Delete department',exact=True).click()
                    page.locator('#modal').get_by_role('button',name='Delete department',exact=True).click()
                    expect(page.locator('#modal')).not_to_be_visible()
                    page.locator('#department-switch').select_option('it')
                    page.goto(base+'/#generate')
                    page.locator('#scope-semester').select_option('3')
                    expect(page.locator('.scope-card')).to_have_count(4)
                    page.get_by_role('button',name='Generate Division A',exact=False).click()
                    expect(page.get_by_label('Classroom continuity preference',exact=True)).to_have_value('3')
                    page.locator('#modal').get_by_role('button',name='Generate timetable',exact=True).click()
                    expect(page.locator('.timetable')).to_be_visible(timeout=35000)
                    expect(page.locator('#main')).to_contain_text('1 scheduled divisions · 8 remaining')
                    expect(page.locator('.lesson')).to_have_count(44)
                    page.locator('#batch-select').select_option('it3A1')
                    expect(page.locator('.lesson')).to_have_count(32)
                    page.locator('#batch-select').select_option('')
                    page.screenshot(path=str(ARTIFACTS/'it-division-desktop.png'),full_page=True)
                    assert page.locator('.session-stack').evaluate_all("""stacks => stacks.every(s => {
                        const cards=[...s.querySelectorAll('.lesson')];
                        const box=s.closest('td').getBoundingClientRect();
                        return cards.every((c,i) => {const r=c.getBoundingClientRect();
                          return r.top>=box.top && r.bottom<=box.bottom+1 && (!i || r.top>=cards[i-1].getBoundingClientRect().bottom);
                        });
                    })""")
                    page.goto(base+'/#assistant')
                    page.get_by_label('Timetable scope').select_option(index=1)
                    expect(page.locator('#assistant-session')).to_be_enabled()
                    page.get_by_label('Session for a room check').select_option(index=1)
                    page.get_by_label('Your question').fill('Is there a replacement classroom for this session?')
                    page.get_by_role('button',name='Ask assistant',exact=True).click()
                    expect(page.locator('.assistant-message.assistant')).to_contain_text('Local timetable checks')
                    page.screenshot(path=str(ARTIFACTS/'assistant-desktop.png'),full_page=True)

                    page.goto(base+'/#generate')
                    page.get_by_role('button',name='Generate Division B',exact=False).click()
                    page.locator('#modal').get_by_role('button',name='Generate timetable',exact=True).click()
                    expect(page.locator('.timetable')).to_be_visible(timeout=35000)
                    expect(page.locator('#main')).to_contain_text('2 scheduled divisions · 7 remaining')
                    # Approval and lock controls persist and gate manual edits.
                    page.get_by_role('button',name='Approve timetable',exact=True).click()
                    expect(page.get_by_role('button',name='Delete timetable',exact=True)).to_be_disabled()
                    expect(page.get_by_role('button',name='Edit timetable manually',exact=True)).to_be_disabled()
                    page.get_by_role('button',name='Lock timetable',exact=True).click()
                    expect(page.get_by_role('button',name='Mark Draft',exact=True)).to_be_disabled()
                    page.reload()
                    expect(page.get_by_role('button',name='Unlock timetable',exact=True)).to_be_visible()
                    page.get_by_role('button',name='Unlock timetable',exact=True).click()
                    page.get_by_role('button',name='Mark Draft',exact=True).click()
                    expect(page.get_by_role('button',name='Delete timetable',exact=True)).to_be_enabled()
                    page.get_by_role('button',name='Edit entire plan',exact=True).click()
                    # Swapping every Monday/Tuesday placement together is a conflict-free manual edit.
                    page.locator('.manual-editor .edit-day').evaluate_all("nodes => nodes.forEach(n => {if(n.value==='0')n.value='1';else if(n.value==='1')n.value='0';})")
                    page.get_by_role('button',name='Validate & save new Draft',exact=True).click()
                    expect(page.locator('#modal')).not_to_be_visible()
                    expect(page.locator('.workflow-panel')).to_contain_text('Edited from #')
                    expect(page.locator('.workflow-panel')).to_contain_text('Draft')
                    page.get_by_role('button',name='Edit timetable manually',exact=True).click()
                    first_lab=page.locator('.manual-editor tbody tr').filter(has_text='lab · 2 period(s)').first
                    first_lab.locator('.edit-slot').select_option('7')
                    page.get_by_role('button',name='Validate & save new Draft',exact=True).click()
                    expect(page.locator('#form-error')).to_contain_text('must fit')
                    page.get_by_role('button',name='Cancel',exact=True).click()
                    page.goto(base+'/#analytics')
                    expect(page.locator('#analytics-content')).to_contain_text('0 internal gaps')
                    page.screenshot(path=str(ARTIFACTS/'analytics-desktop.png'),full_page=True)
                    page.goto(base+'/#performance')
                    expect(page.locator('#performance-content')).to_contain_text('Python')
                    expect(page.locator('#performance-content')).to_contain_text('100%')
                    page.goto(base+'/#history')
                    expect(page.locator('#main .data-table tbody tr')).to_have_count(3)
                    page.goto(base+'/#workload')
                    expect(page.locator('#main .data-table tbody tr')).to_have_count(33)
                    page.get_by_role('button',name='Edit limits',exact=True).first.click()
                    expect(page.get_by_label('Maximum teaching periods per day',exact=True)).to_have_value('5')
                    page.get_by_role('button',name='Cancel',exact=True).click()
                    page.goto(base+'/#timings')
                    page.get_by_label('College end',exact=True).fill('16:45')
                    page.get_by_role('button',name='Preview periods',exact=True).click()
                    expect(page.locator('#calendar-preview')).to_contain_text('7 teaching periods')
                    page.get_by_role('button',name='Save college timings',exact=True).click()
                    expect(page.get_by_label('College end',exact=True)).to_have_value('16:45')
                    # Reload proves persistence; saved generation still uses its eight-period calendar.
                    page.reload()
                    expect(page.get_by_label('College end',exact=True)).to_have_value('16:45')
                    page.goto(base+'/#timetables')
                    expect(page.locator('.timetable')).to_contain_text('16:45–17:45')
                    page.goto(base+'/#timings')
                    page.get_by_label('College end',exact=True).fill('17:45')
                    page.get_by_role('button',name='Save college timings',exact=True).click()
                    expect(page.locator('#toast')).to_contain_text('College timings saved')

                    page.get_by_role('link',name='Academic setup',exact=True).click()
                    page.get_by_role('tab',name='Teachers').click()
                    page.get_by_role('button',name='Add teacher',exact=True).click()
                    page.get_by_label('Teacher name',exact=True).fill('Prof. Browser Test')
                    page.get_by_label('Teaching hours per week (maximum)',exact=True).fill('16')
                    page.get_by_role('button',name='Save teacher',exact=True).click()
                    expect(page.locator('#modal')).not_to_be_visible()
                    page.get_by_label('Search teachers',exact=True).fill('Browser Test')
                    expect(page.locator('#setup-table tbody tr')).to_have_count(1)
                    page.get_by_role('button',name='Edit teacher',exact=True).click()
                    page.get_by_label('Leaving / departure time',exact=True).fill('16:45')
                    page.get_by_role('button',name='Save teacher',exact=True).click()
                    expect(page.locator('#setup-table')).to_contain_text('16:45')
                    page.get_by_role('button',name='Delete teacher',exact=True).click()
                    page.locator('#modal').get_by_role('button',name='Delete teacher',exact=True).click()
                    expect(page.locator('#setup-table')).to_contain_text('No matching teachers')

                    # Project records are created only by this explicit user form action.
                    page.goto(base+'/#projects')
                    page.get_by_role('button',name='Add mini project',exact=True).click()
                    page.get_by_label('Project name',exact=True).fill('Browser project')
                    page.get_by_label('Project subject code',exact=True).fill('TESTPROJ')
                    page.get_by_label('Hours per session',exact=True).fill('2')
                    page.get_by_role('button',name='Save mini project',exact=True).click()
                    expect(page.locator('#modal')).not_to_be_visible()
                    expect(page.locator('#main')).to_contain_text('Browser project')
                    page.reload()
                    expect(page.locator('#main')).to_contain_text('Browser project')
                    page.get_by_role('button',name='Edit project',exact=True).click()
                    expect(page.get_by_label('Hours per session',exact=True)).to_have_value('2')
                    page.get_by_role('button',name='Cancel',exact=True).click()
                    page.get_by_role('button',name='Remove project',exact=True).click()
                    page.get_by_role('button',name='Remove project sessions',exact=True).click()
                    expect(page.locator('#main')).to_contain_text('No mini projects added')

                    page.get_by_role('link',name='Import data',exact=True).click()
                    page.locator('#csv-file').set_input_files(str(ROOT/'sample_data'/'unisched_semesters_3_5_7.csv'))
                    expect(page.locator('#import-result')).to_contain_text('54 Assignments')
                    page.screenshot(path=str(ARTIFACTS/'import-desktop.png'),full_page=True)
                    page.get_by_role('button',name='Replace academic data',exact=True).click()
                    expect(page.get_by_role('heading',name='Academic setup',exact=True)).to_be_visible()
                    page.get_by_role('button',name='Check requirements',exact=True).click()
                    expect(page.locator('#validation-result')).to_contain_text('Basic workload and capacity checks passed')

                    page.get_by_role('link',name='Timetables',exact=False).first.click()
                    page.get_by_role('link',name='Generate timetable',exact=True).last.click()
                    page.get_by_role('button',name='Generate all selected divisions',exact=False).click()
                    page.get_by_label('Timetable name',exact=True).fill('Browser verified semester')
                    page.locator('#modal').get_by_role('button',name='Generate timetable',exact=True).click()
                    expect(page.locator('.timetable')).to_be_visible(timeout=35000)
                    expect(page.locator('.diagnostics')).to_contain_text('All constraints satisfied')
                    expect(page.locator('.lesson')).to_have_count(22)
                    page.screenshot(path=str(ARTIFACTS/'timetable-desktop.png'),full_page=True)

                    page.get_by_role('button',name='By professor',exact=True).click()
                    expect(page.locator('.timetable-label')).to_have_text('Dr. Anjali Deshmukh')
                    expect(page.locator('.lesson')).to_have_count(9)
                    expect(page.locator('.timetable td.empty')).to_have_count(31)
                    for text in page.locator('.lesson').all_text_contents():
                        assert 'CSC301' in text
                        assert 'Div ' in text
                    page.screenshot(path=str(ARTIFACTS/'professor-desktop.png'),full_page=True)
                    for name,filename in [('PDF','professor.pdf'),('Excel','professor.xlsx')]:
                        with page.expect_download() as download:
                            page.get_by_role('link',name=name,exact=True).click()
                        download.value.save_as(ARTIFACTS/filename)
                        assert (ARTIFACTS/filename).stat().st_size > 1000

                    page.get_by_role('link',name='Academic setup',exact=True).click()
                    page.get_by_role('tab',name='Teachers').click()
                    page.get_by_label('Search teachers',exact=True).fill('Anjali')
                    page.get_by_role('button',name='Edit teacher',exact=True).click()
                    page.get_by_label('Teaching hours per week (maximum)',exact=True).fill('1')
                    page.get_by_role('button',name='Save teacher',exact=True).click()
                    expect(page.locator('#modal')).not_to_be_visible()
                    page.get_by_role('link',name='Timetables',exact=False).first.click()
                    expect(page.locator('.info-banner.warning')).to_contain_text('Academic changes affect future generations')
                    page.get_by_role('link',name='Generate timetable',exact=True).last.click()
                    page.get_by_role('button',name='Generate all selected divisions',exact=False).click()
                    page.locator('#modal').get_by_role('button',name='Generate timetable',exact=True).click()
                    expect(page.locator('.diagnostics')).to_contain_text('Generation not possible')
                    expect(page.locator('.diagnostics')).to_contain_text('9 assigned hours')
                    expect(page.locator('.diagnostics')).to_contain_text('Reassign at least 8 hours')
                    page.screenshot(path=str(ARTIFACTS/'conflict-desktop.png'),full_page=True)

                    page.emulate_media(reduced_motion='reduce')
                    page.set_viewport_size({'width':390,'height':844})
                    page.goto(base+'/#overview')
                    expect(page.get_by_role('heading',name='A better week starts here.')).to_be_visible()
                    expect(page.get_by_role('link',name='Open AI chat assistant')).to_be_visible()
                    page.wait_for_function("document.querySelector('#sidebar').getBoundingClientRect().right <= 0")
                    page.evaluate("document.querySelector('#toast').classList.remove('visible')")
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    page.screenshot(path=str(ARTIFACTS/'overview-mobile.png'),full_page=True)
                    page.get_by_role('button',name='Toggle navigation',exact=True).click()
                    page.get_by_role('link',name='Import data',exact=True).click()
                    expect(page.get_by_role('heading',name='Bring your semester into focus.')).to_be_visible()
                    expect(page.locator('#sidebar')).not_to_have_class('sidebar open')
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    page.get_by_role('button',name='Toggle navigation',exact=True).click()
                    page.get_by_role('link',name='Timetables',exact=False).first.click()
                    page.locator('#generation-select').select_option(index=1)
                    expect(page.locator('.timetable')).to_be_visible()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    page.screenshot(path=str(ARTIFACTS/'timetable-mobile.png'),full_page=True)
                    page.get_by_role('button',name='Toggle navigation',exact=True).click()
                    page.get_by_role('link',name='Import data',exact=True).click()
                    page.locator('#csv-file').set_input_files({'name':'invalid.csv','mimeType':'text/csv','buffer':b'bad,headers\n1,2'})
                    expect(page.locator('#import-result')).to_contain_text('headers must match')
                    # Delete failed reports and saved versions through the actual controls.
                    page.set_viewport_size({'width':1440,'height':1050})
                    before_delete=page.request.get(base+'/api/config').json()
                    page.goto(base+'/#timetables')
                    history=page.request.get(base+'/api/generations').json()
                    failure=next(h for h in history if h['status']!='feasible')
                    page.locator('#generation-select').select_option(str(failure['id']))
                    page.get_by_role('button',name='Delete timetable',exact=True).click()
                    page.get_by_role('button',name='Cancel',exact=True).click()
                    assert page.request.get(base+'/api/generations').json()==history
                    page.get_by_role('button',name='Delete timetable',exact=True).click()
                    page.get_by_role('button',name='Permanently delete',exact=True).click()
                    expect(page.locator('#modal')).not_to_be_visible()
                    assert page.request.get(base+f"/api/generations/{failure['id']}").status==404
                    page.goto(base+'/#history')
                    while page.get_by_role('button',name='Delete timetable',exact=True).count():
                        page.get_by_role('button',name='Delete timetable',exact=True).first.click()
                        page.get_by_role('button',name='Permanently delete',exact=True).click()
                        expect(page.locator('#modal')).not_to_be_visible()
                    page.goto(base+'/#timetables')
                    expect(page.locator('#main')).to_contain_text('No timetable yet')
                    assert page.request.get(base+'/api/generations').json()==[]
                    assert page.request.get(base+'/api/config').json()==before_delete
                    assert errors == [], errors
                    browser.close()
                    print('Browser smoke passed: desktop/mobile navigation, academic CRUD, batch filtering, scoped generation, manual swaps/rejected edits, approval/lock/draft persistence, imports, professor exports, immutable versions, and actionable infeasibility. No JavaScript errors.')
            finally:
                server.terminate()
                server.wait(timeout=10)

if __name__ == '__main__':
    run()
