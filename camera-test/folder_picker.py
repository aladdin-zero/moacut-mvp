"""Local folder names for the in-page destination picker; never lists files."""
import os
from pathlib import Path


def local_folder(path):
    if not isinstance(path,str) or not path.strip() or len(path)>1024 or any(ord(c)<32 for c in path):
        raise ValueError('이 PC의 저장 폴더 경로를 입력해 주세요.')
    path=path.strip()
    if path.startswith(('\\\\','//')) or not Path(path).is_absolute():
        raise ValueError('이 PC 드라이브의 전체 경로를 선택해 주세요. 네트워크 폴더는 지원하지 않습니다.')
    candidate=Path(path).resolve()
    if str(candidate).startswith('\\\\'):
        raise ValueError('네트워크 폴더는 지원하지 않습니다.')
    if os.name=='nt':
        import ctypes
        function=ctypes.windll.kernel32.GetDriveTypeW
        function.argtypes=[ctypes.c_wchar_p];function.restype=ctypes.c_uint
        if function(candidate.anchor)==4:
            raise ValueError('네트워크 드라이브 대신 이 PC의 폴더를 선택해 주세요.')
    if not candidate.is_dir():
        raise ValueError('해당 폴더가 없습니다. 폴더를 만든 뒤 다시 선택해 주세요.')
    return candidate


def list_folders(path=None):
    if os.name=='nt':
        import ctypes
        drives=[];mask=ctypes.windll.kernel32.GetLogicalDrives()
        for index,letter in enumerate('ABCDEFGHIJKLMNOPQRSTUVWXYZ'):
            if not mask & (1<<index):continue
            drive=Path(letter+':/')
            if ctypes.windll.kernel32.GetDriveTypeW(str(drive)) not in (2,3,6):continue
            try:local_folder(str(drive));drives.append(str(drive))
            except (ValueError,OSError):pass
    else:drives=['/']
    if not path:return {'path':None,'parent':None,'drives':drives,'folders':[],'truncated':False}
    directory=local_folder(path)
    folders=[];truncated=False
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.name.startswith(('.', '$')):continue
                try:
                    if entry.is_dir(follow_symlinks=False):folders.append({'name':entry.name,'path':str(directory/entry.name)})
                except OSError:continue
                if len(folders)>=1000:truncated=True;break
    except OSError as exc:
        raise ValueError('이 폴더의 목록을 읽을 수 없습니다. 다른 폴더를 선택해 주세요.') from exc
    return {'path':str(directory),'parent':str(directory.parent) if directory.parent!=directory else None,
        'drives':drives,'folders':sorted(folders,key=lambda f:f['name'].casefold()),'truncated':truncated}
