"""Build a relocatable Windows release from the verified local environment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
from importlib.metadata import distribution

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.deps-camera'))
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

VERSION='0.1.0'
APP_FILES=['server.py','detector.py','product_detector.py','folder_picker.py','voice_guidance.py','work_sessions.py']
REQUIRED=['torch','torchvision','transformers','opencv-python-headless','scipy','pillow','numpy']


def dependencies():
    result={};queue=list(REQUIRED)
    while queue:
        name=queue.pop();key=canonicalize_name(name)
        if key in result:continue
        dist=distribution(name);result[key]=dist
        for item in dist.requires or []:
            requirement=Requirement(item)
            if requirement.marker is None or requirement.marker.evaluate({'extra':''}):queue.append(requirement.name)
    return result


def copy_file(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)


def build(output):
    output=output.resolve()
    if output.exists():raise ValueError('Output must be a new directory; existing builds are never overwritten.')
    output.mkdir(parents=True)
    runtime=output/'runtime';runtime.mkdir()
    base=Path(sys.base_prefix)
    for name in ['python.exe','pythonw.exe','python3.dll','python312.dll','vcruntime140.dll','vcruntime140_1.dll','LICENSE.txt']:
        copy_file(base/name,runtime/name)
    for folder in ['Lib','DLLs']:
        shutil.copytree(base/folder,runtime/folder,ignore=shutil.ignore_patterns('site-packages','__pycache__','*.pyc','*.pdb','*.lib','idlelib','tkinter','ensurepip','venv','test'))
    (runtime/'python312._pth').write_text('.\nDLLs\nLib\nLib/site-packages\n../app\nimport site\n',encoding='utf-8')
    records=[];skipped=0
    for name,dist in sorted(dependencies().items()):
        copied=0
        for path in dist.files or []:
            source=Path(dist.locate_file(path))
            if '..' in path.parts or '__pycache__' in path.parts or path.name=='direct_url.json' or source.suffix.lower() in ('.pyc','.pyo','.pdb','.lib','.h','.hpp','.cuh') or not source.is_file():
                if source.is_file():skipped+=source.stat().st_size
                continue
            copy_file(source,runtime/'Lib/site-packages'/path);copied+=source.stat().st_size
        records.append({'name':name,'version':dist.version,'bytes':copied})
        print('Bundled',name,dist.version,flush=True)
    for name in APP_FILES:copy_file(ROOT/'camera-test'/name,output/'app'/name)
    copy_file(ROOT/'packaging/diagnose.py',output/'app/diagnose.py')
    shutil.copytree(ROOT/'camera-test/web',output/'app/web')
    shutil.copytree(ROOT/'models/owlv2',output/'models/owlv2')
    copy_file(ROOT/'packaging/USER-GUIDE.md',output/'사용안내.md')
    copy_file(ROOT/'packaging/THIRD-PARTY-NOTICES.md',output/'THIRD-PARTY-NOTICES.md')
    licenses=output/'licenses';licenses.mkdir()
    copy_file(base/'LICENSE.txt',licenses/'Python-LICENSE.txt')
    for name,dist in sorted(dependencies().items()):
        for path in dist.files or []:
            if '.dist-info' in str(path) and any(word in path.name.lower() for word in ['license','copying','notice','copyright']):
                source=Path(dist.locate_file(path))
                if source.is_file():copy_file(source,licenses/name/Path(*path.parts[1:]))
    apache=next(p for p in (licenses/'transformers').rglob('*') if p.is_file() and p.name.lower()=='license')
    copy_file(apache,licenses/'OWLv2-Apache-2.0.txt')
    compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    subprocess.run([str(compiler),'/nologo','/codepage:65001','/target:winexe','/platform:x64','/optimize+',
        '/reference:System.Windows.Forms.dll','/reference:System.Drawing.dll',
        '/out:'+str(output/'MOACUT.exe'),str(ROOT/'packaging/Launcher.cs')],check=True)
    (output/'환경점검.cmd').write_text('@echo off\r\nchcp 65001 >nul\r\n"%~dp0runtime\\python.exe" -B -X utf8 "%~dp0app\\diagnose.py"\r\npause\r\n',encoding='utf-8')
    (output/'build-info.json').write_text(json.dumps({'application':'MOACUT','version':VERSION,'platform':'Windows-x64',
        'python':sys.version.split()[0],'packages':records,'excluded_build_bytes':skipped},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Release ready:',output,flush=True)


def archive(folder,target):
    with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as bundle:
        for file in sorted(folder.rglob('*')):
            if file.is_file():bundle.write(file,folder.name+'/'+file.relative_to(folder).as_posix())
    return hashlib.file_digest(target.open('rb'),'sha256').hexdigest()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--zip',type=Path);parser.add_argument('--assets',type=Path);args=parser.parse_args()
    build(args.output)
    if args.zip:print('ZIP SHA256:',archive(args.output,args.zip),flush=True)
    if args.assets:
        from package_assets import create_assets
        create_assets(args.output,args.assets)
