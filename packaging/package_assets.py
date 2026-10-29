"""Standard ZIP parts plus a Windows extractor; every asset stays below 2 GiB."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import zipfile


def create_assets(folder,destination):
    folder=folder.resolve();destination=destination.resolve()
    destination.mkdir(parents=True,exist_ok=False)
    limit=1750*1024**2
    groups=[];current=[];size=0
    for file in sorted(folder.rglob('*')):
        if not file.is_file():continue
        length=file.stat().st_size
        if length>limit:raise ValueError('An individual runtime file exceeds the part limit.')
        if current and size+length>limit:groups.append(current);current=[];size=0
        current.append(file);size+=length
    if current:groups.append(current)
    def write_part(item):
        index,files=item
        target=destination/(folder.name+'-part'+str(index)+'.zip')
        with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3,allowZip64=True) as archive:
            for file in files:archive.write(file,folder.name+'/'+file.relative_to(folder).as_posix())
        with target.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        assert target.stat().st_size<2*1024**3
        print('Created',target.name,target.stat().st_size,flush=True)
        return {'name':target.name,'bytes':target.stat().st_size,'sha256':digest}
    with ThreadPoolExecutor(max_workers=3) as pool:parts=list(pool.map(write_part,enumerate(groups,1)))
    checks=';'.join("'"+p['name']+"'='"+p['sha256']+"'" for p in parts)
    script="$ErrorActionPreference='Stop'; try { $root=$env:MOACUT_PACKAGE_DIR; $expected=@{"+checks+"}; "+\
        "$target=Join-Path $root '"+folder.name+"'; if(Test-Path -LiteralPath $target){throw 'Target folder already exists. Extract into a new folder.'}; "+\
        "foreach($name in $expected.Keys){$file=Join-Path $root $name; if(!(Test-Path -LiteralPath $file)){throw ('Missing ZIP: '+$name)}; "+\
        "if((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLower() -ne $expected[$name]){throw ('Download hash mismatch: '+$name)}}; "+\
        "foreach($name in ($expected.Keys|Sort-Object)){Write-Host ('Extracting '+$name); Expand-Archive -LiteralPath (Join-Path $root $name) -DestinationPath $root}; "+\
        "Write-Host 'MOACUT ready.' } catch { Write-Host $_.Exception.Message; exit 1 }"
    installer='@echo off\r\nchcp 65001 >nul\r\nset "MOACUT_PACKAGE_DIR=%~dp0"\r\n'+\
        'powershell.exe -NoProfile -Command "'+script+'"\r\nif errorlevel 1 (\r\n  pause\r\n  exit /b 1\r\n)\r\n'+\
        'if "%~1"=="--no-launch" exit /b 0\r\nstart "" "%~dp0'+folder.name+'\\MOACUT.exe"\r\n'
    (destination/'Install-MOACUT.cmd').write_text(installer,encoding='utf-8')
    notes='''모아컷 Windows 설치

1. 이 Release의 모든 part ZIP과 Install-MOACUT.cmd를 같은 폴더에 받습니다.
2. Install-MOACUT.cmd를 실행합니다. 다운로드 해시를 확인한 뒤 모든 ZIP을 자동으로 풉니다.
3. 열린 모아컷에서 새 작업을 시작합니다. 이후에는 생성된 폴더의 MOACUT.exe를 실행합니다.

직접 풀 경우에도 모든 ZIP을 같은 폴더에 압축 해제해야 합니다. part ZIP은 각각 표준 ZIP이며 내용을 합치거나 ZIP 하나만 실행하지 마세요.
이전 설치 폴더가 있으면 다른 폴더에서 진행하세요. 기존 설치/사진/작업 데이터를 덮어쓰지 않습니다.
사진은 %LOCALAPPDATA%\\MOACUT\\captures에 보관합니다. 종료는 작업 표시줄의 모아컷 아이콘을 사용합니다.
GPU가 없으면 CPU로 자동 전환합니다. CPU는 촬영 간 대기시간이 길 수 있습니다. 자세한 내용은 설치 폴더의 사용안내.md를 참고하세요.
'''
    (destination/'INSTALL.txt').write_text(notes,encoding='utf-8')
    assets=parts+[{'name':p.name,'bytes':p.stat().st_size,'sha256':hashlib.file_digest(p.open('rb'),'sha256').hexdigest()}
        for p in [destination/'Install-MOACUT.cmd',destination/'INSTALL.txt']]
    (destination/'SHA256SUMS.txt').write_text(''.join(a['sha256']+'  '+a['name']+'\n' for a in assets),encoding='utf-8')
    (destination/'assets.json').write_text(json.dumps(assets,indent=2),encoding='utf-8')
    return assets


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);parser.add_argument('destination',type=Path)
    args=parser.parse_args();create_assets(args.folder,args.destination)
