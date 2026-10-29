# 모아컷 · MOACUT 1차 MVP

Windows 10/11 64비트에서 USB 카메라로 상품을 촬영하고, 4컷씩 묶어 검토한 사진을 로컬 폴더로 정리합니다. 유료 API와 사진 외부 전송을 사용하지 않습니다.

## 클라이언트 실행
[Windows 설치 파일 v0.1.1](https://github.com/aladdin-zero/moacut-mvp/releases/tag/v0.1.1)에서 **MOACUT-Setup-0.1.1-Windows-x64.exe 하나만 다운로드**하고 실행합니다. 설치 후 **바탕화면 또는 시작 메뉴의 ‘모아컷’**을 누르면 촬영 화면이 열립니다. Python 설치, ZIP 압축 해제, 설치 명령파일 실행은 필요하지 않습니다. 종료는 작업 표시줄의 모아컷 아이콘을 사용합니다. 자세한 내용은 [사용 안내](packaging/USER-GUIDE.md)를 참조하세요.

사진·작업 기록은 `%LOCALAPPDATA%\MOACUT\captures`에 보관하며 배포 ZIP에는 테스트 사진이나 기존 작업이 없습니다. 오늘 새 작업/이어하기, 사용자 촬영 항목 추가·삭제·선택, 사진 휴지통/복원, 검토 완료 후 브랜드·상품별 폴더 저장을 지원합니다. 고정 4컷은 작업 구분 규칙이며 사진 종류/동일 상품을 AI가 확정하는 것은 아닙니다.

## 하드웨어 선택
사용 가능한 NVIDIA GPU를 자동 확인하고 GPU가 없거나 실행에 실패하면 CPU로 전환합니다. GPU와 CPU를 위한 별도 설치 파일을 고를 필요가 없습니다. CPU는 느릴 수 있습니다. 개발 PC의 합성 화면 추론은 RTX 3070 약0.24초, CPU 약3.3초였으며 클라이언트 성능/현장 정확도를 보장하는 측정이 아닙니다. 두 번의 연속 인식과 정지 조건을 확인하므로 실제 촬영 대기시간은 더 길 수 있습니다. 환경점검.cmd로 오프라인 모델/하드웨어/음성 점검을 할 수 있습니다.

## 개발 및 재빌드
Python 3.12 64비트와 Windows .NET Framework C# 컴파일러가 필요합니다. 런타임 의존성은 고정 버전입니다.

```powershell
py -3.12 -m venv .venv-ai
.venv-ai\Scripts\python.exe -m pip install --extra-index-url https://download.pytorch.org/whl/cu126 -r requirements.txt
.venv-ai\Scripts\python.exe camera-test\download_detector.py
.venv-ai\Scripts\python.exe camera-test\server.py --open --port 0
.venv-ai\Scripts\python.exe -m unittest discover -s camera-test -p "test_*.py" -v
node --test camera-test/test_capture_flow.cjs
node --check camera-test/web/app.js
.venv-ai\Scripts\python.exe packaging\build_release.py --output delivery\MOACUT-v0.1.0-Windows-x64
```

빌더는 기존 환경의 필수 의존성/Windows Python 런타임/고정 OWLv2 모델만 복사하고 실행기를 컴파일합니다. 결과 폴더는 존재하지 않는 새 경로여야 합니다. 아래 단일 설치 파일 빌드까지 진행한 뒤 GitHub Releases에 Setup.exe와 SHA256을 제공합니다. 배포 사진/비밀값/설치 캐시는 업로드하지 않습니다.

프로그램 코드의 별도 오픈소스 라이선스는 아직 지정하지 않았습니다. 이 저장소는 비공개 클라이언트 전달용입니다. 제3자 라이선스는 [고지](packaging/THIRD-PARTY-NOTICES.md)와 배포본 licenses 폴더를 따릅니다. Windows 실행 파일은 코드서명되지 않았습니다.

## 단일 Windows 설치 파일 빌드
설치 패키지0.1.1은 촬영 앱0.1.0의 기능과 검증된 런타임을 그대로 사용하며 설치/바로가기/제거 흐름을 제공합니다. 아래 명령은 위에서 만든 portable 출력 폴더를 설치파일 하나로 압축합니다.

공식 [Inno Setup6.4.3](https://github.com/jrsoftware/issrc/releases/tag/is-6_4_3) 컴파일러를 사용했습니다. 공식 다운로드의 SHA256은 `f3c42116542c4cc57263c5ba6c4feabfc49fe771f2f98a79d2f7628b8762723b`이며, 이 고정버전은 상업용 포함 사용이 허용된 무료 빌드도구입니다. 라이선스는 해당공식소스를참조하세요.

```powershell
.venv-ai\Scripts\python.exe packaging\build_setup.py --source delivery\MOACUT-v0.1.0-Windows-x64 --compiler "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" --output delivery\setup-v0.1.1
```

컴파일러 경로는 설치 위치에 맞춰 지정합니다. 출력 경로는 새 폴더여야 하며, 빌더는 GitHub2GiB제한을 검사하고 SHA256을 기록합니다. 설치기는 현재 사용자 권한으로 동작하고 바탕화면/시작메뉴 바로가기를 만듭니다. 앱 제거 시 사용자 사진/작업기록은 삭제하지 않습니다. v0.1.0의 다중ZIP배포는 이전 버전용이며 새사용자는 v0.1.1설치파일을 사용하세요.
