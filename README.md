# 모아컷 · MOACUT 1차 MVP

Windows 10/11 64비트에서 USB 카메라로 상품을 촬영하고, 4컷씩 묶어 검토한 사진을 로컬 폴더로 정리합니다. 유료 API와 사진 외부 전송을 사용하지 않습니다.

## 클라이언트 실행
[Releases](https://github.com/aladdin-zero/moacut-mvp/releases)에서 모든 part ZIP과 Install-MOACUT.cmd를 같은 폴더에 받고 **Install-MOACUT.cmd 실행**합니다. 해시 확인과 압축 해제를 마치면 MOACUT.exe가 열립니다. Python 설치는 필요하지 않습니다. 작업 표시줄의 모아컷 아이콘에서 종료합니다. 자세한 사용법은 [사용 안내](packaging/USER-GUIDE.md)를 참조하세요.

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
.venv-ai\Scripts\python.exe packaging\build_release.py --output delivery\MOACUT-v0.1.0-Windows-x64 --assets delivery\release-v0.1.0
```

빌더는 기존 환경의 필수 의존성/Windows Python 런타임/고정 OWLv2 모델만 복사하고 실행기를 컴파일합니다. 결과 폴더는 존재하지 않는 새 경로여야 합니다. 압축/검증 후 GitHub Releases에 ZIP을 올리고 SHA256을 함께 제공합니다. 배포 사진/비밀값/설치 캐시는 업로드하지 않습니다.

프로그램 코드의 별도 오픈소스 라이선스는 아직 지정하지 않았습니다. 이 저장소는 비공개 클라이언트 전달용입니다. 제3자 라이선스는 [고지](packaging/THIRD-PARTY-NOTICES.md)와 배포본 licenses 폴더를 따릅니다. Windows 실행 파일은 코드서명되지 않았습니다.
