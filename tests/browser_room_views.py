"""Real-browser regression for classroom and lab timetable views."""
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

ROOT=Path(__file__).resolve().parents[1]


def run():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='timetable-rooms-') as folder:
        environment={**os.environ,'UNISCHED_DB':str(Path(folder)/'browser.db')}
        with open(Path(folder)/'server.log','w') as log:
            server=subprocess.Popen([sys.executable,'run.py','--port',str(port)],cwd=ROOT,env=environment,stdout=log,stderr=log)
            try:
                base=f'http://127.0.0.1:{port}'
                for _ in range(100):
                    try:
                        with urlopen(base+'/api/health',timeout=1) as response: assert response.status==200
                        break
                    except OSError:
                        if server.poll() is not None: raise RuntimeError('Server exited during startup.')
                        time.sleep(.1)
                else: raise RuntimeError('Server did not become ready.')
                with sync_playwright() as p:
                    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'))
                    page=browser.new_page(viewport={'width':1440,'height':1000})
                    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(base)
                    before=page.request.get(base+'/api/config').json()
                    response=page.request.post(base+'/api/generations',data={'name':'Room views','group_ids':['it3A'],'time_limit':20},timeout=60000)
                    assert response.ok,response.text()
                    record=response.json();assert record['result']['status']=='feasible',record
                    page.reload();page.goto(base+'/#timetables')
                    for kind in ('classroom','lab'):
                        page.get_by_role('button',name='By '+kind,exact=True).click()
                        rooms=[r for r in record['config']['rooms'] if r['kind']==kind]
                        assert set(page.locator('#target-select option').evaluate_all('(options)=>options.map(o=>o.value)'))=={r['id'] for r in rooms}
                        room=next(r for r in rooms if any(e['room_id']==r['id'] for e in record['result']['entries']))
                        page.get_by_label(kind.capitalize(),exact=True).select_option(room['id'])
                        expect(page.locator('.timetable-label')).to_have_text(room['name'])
                        entries=[e for e in record['result']['entries'] if e['room_id']==room['id']]
                        expect(page.locator('.timetable .lesson')).to_have_count(sum(e['duration'] for e in entries))
                        for entry in entries:
                            teacher=next(t for t in record['config']['teachers'] if t['id']==entry['teacher_id'])
                            expect(page.locator('.timetable')).to_contain_text(teacher['name'])
                        page.get_by_role('button',name='Edit timetable manually',exact=True).click()
                        expect(page.locator('[data-entry-index]')).to_have_count(len(entries))
                        page.get_by_role('button',name='Cancel',exact=True).click()
                        for label in ('PDF','Excel'):
                            with page.expect_download() as downloaded:
                                page.get_by_role('link',name=label,exact=True).click()
                            assert downloaded.value.failure() is None
                        # All room bookings remain visible at a narrow viewport too.
                        page.set_viewport_size({'width':390,'height':844})
                        expect(page.get_by_role('button',name='By classroom',exact=True)).to_be_visible()
                        expect(page.get_by_role('button',name='By lab',exact=True)).to_be_visible()
                        assert page.locator('.view-toggle button').evaluate_all('(buttons)=>buttons.every(b=>b.getBoundingClientRect().right<=window.innerWidth)')
                        page.set_viewport_size({'width':1440,'height':1000})
                    page.get_by_role('button',name='By professor',exact=True).click()
                    expect(page.get_by_label('Professor',exact=True)).to_be_visible()
                    page.get_by_role('button',name='By division',exact=True).click()
                    expect(page.get_by_label('Division',exact=True)).to_be_visible()
                    assert page.request.get(base+'/api/config').json()==before
                    assert page.request.get(f"{base}/api/generations/{record['id']}").json()==record
                    assert not errors,errors
                    browser.close()
                    print('PASS: classroom/lab filtering, professor labels, manual editor scope, PDF/Excel downloads, mobile buttons, existing views, unchanged data.')
            finally:
                server.terminate();server.wait(timeout=10)


if __name__=='__main__': run()
