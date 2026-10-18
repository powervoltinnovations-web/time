"""Real-browser regression for timetable deletion using a disposable database."""
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
    with tempfile.TemporaryDirectory(prefix='timetable-delete-') as folder:
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
                    page.goto(base+'/#teachers')
                    expect(page.locator('#setup-table')).to_contain_text('Dr.Vidya Kubde')
                    expect(page.locator('#setup-table')).to_contain_text('Sample Professor 10')
                    before=page.request.get(base+'/api/config').json()
                    versions=[]
                    for name in ('First version','Second version'):
                        response=page.request.post(base+'/api/generations',data={'name':name,'group_ids':['it3A'],'time_limit':20},timeout=60000)
                        assert response.ok,response.text()
                        record=response.json();assert record['result']['status']=='feasible',record
                        versions.append(record['id'])
                    page.reload();page.goto(base+'/#history')
                    expect(page.locator('[data-action="delete-timetable"]')).to_have_count(2)
                    first=page.locator(f'[data-action="delete-timetable"][data-id="{versions[0]}"]')
                    first.click()
                    expect(page.get_by_role('heading',name='Delete timetable?',exact=True)).to_be_visible()
                    page.get_by_role('button',name='Cancel',exact=True).click()
                    assert len(page.request.get(base+'/api/generations').json())==2
                    first.click()
                    page.get_by_role('button',name='Delete timetable permanently',exact=True).click()
                    expect(page.locator('[data-action="delete-timetable"]')).to_have_count(1)
                    assert page.request.get(f'{base}/api/generations/{versions[0]}').status==404
                    assert page.request.get(f'{base}/api/generations/{versions[1]}').ok
                    page.get_by_role('button',name=f'Open version #{versions[1]}',exact=True).click()
                    page.get_by_role('button',name='Lock timetable',exact=True).click()
                    expect(page.get_by_role('button',name='Delete timetable',exact=True)).to_be_disabled()
                    page.get_by_role('button',name='Unlock timetable',exact=True).click()
                    expect(page.get_by_role('button',name='Delete timetable',exact=True)).to_be_enabled()
                    page.get_by_role('button',name='Delete timetable',exact=True).click()
                    page.get_by_role('button',name='Delete timetable permanently',exact=True).click()
                    expect(page.locator('[data-action="delete-timetable"]')).to_have_count(0)
                    assert page.request.get(base+'/api/generations').json()==[]
                    assert page.request.get(base+'/api/config').json()==before
                    page.reload()
                    expect(page.locator('#schedule-count')).to_have_text('0')
                    assert not errors,errors
                    browser.close()
                    print('PASS: teacher names, cancel, history deletion, lock/unlock, current/last deletion, reload, unchanged academic data.')
            finally:
                server.terminate();server.wait(timeout=10)


if __name__=='__main__': run()
