"""Compile the verified offline app into one per-user Windows installer."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def build(source,compiler,output):
    source=source.resolve();compiler=compiler.resolve();output=output.resolve()
    if not (source/'MOACUT.exe').is_file() or not (source/'FILES-SHA256.json').is_file():
        raise ValueError('Use the verified portable build as SourceRoot.')
    output.mkdir(parents=True,exist_ok=False)
    script=Path(__file__).with_name('MOACUT.iss')
    subprocess.run([str(compiler),'/DSourceRoot='+str(source),'/DReleaseOutput='+str(output),str(script)],check=True)
    installer=output/'MOACUT-Setup-0.1.1-Windows-x64.exe'
    size=installer.stat().st_size
    if size>=2*1024**3:raise ValueError('Installer exceeds the GitHub 2 GiB asset limit.')
    with installer.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    result={'name':installer.name,'bytes':size,'sha256':digest,'installer_version':'0.1.1',
        'application_version':json.loads((source/'build-info.json').read_text(encoding='utf-8'))['version']}
    (output/'setup-info.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (output/'SHA256SUMS.txt').write_text(digest+'  '+installer.name+'\n',encoding='utf-8')
    print('Single installer ready:',json.dumps(result),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--compiler',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();build(args.source,args.compiler,args.output)
