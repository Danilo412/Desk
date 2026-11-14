from pathlib import Path
import subprocess,os,tempfile,json
root=Path(__file__).resolve().parents[1];package=root/'dist/Desk'
assert (package/'Desk.exe').is_file() and not (package/'internet.json').exists()
assert not any(p.name=='identity.dat' for p in package.rglob('*'))
with tempfile.TemporaryDirectory(prefix='desk-public-validation-') as tmp:
    folder=Path(tmp);env=os.environ.copy();env.update(NOVOACESSO_OFFLINE='1',DESK_AUTOREADY='0',QT_QPA_PLATFORM='offscreen',NOVOACESSO_STATE_DIR=str(folder/'state'))
    env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None)
    env['PATH']=str(Path(os.environ['SystemRoot'])/'System32')+os.pathsep+os.environ['SystemRoot']
    result_path=folder/'self-test.json'
    result=subprocess.run([str(package/'Desk.exe'),'--self-test','--result',str(result_path)],cwd=tmp,env=env,timeout=90)
    assert result.returncode==0 and result_path.exists(),'Packaged application failed'
    report=json.loads(result_path.read_text(encoding='utf-8'));assert report['passed'],report
    print(json.dumps(dict(packaged_self_test_passed=True,checks=report['checks'],live_credentials_included=False)))
