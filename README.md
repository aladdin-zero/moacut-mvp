# 모아컷 · MOACUT v0.2.0

## ⬇️ [Windows 설치 파일 바로 다운로드](https://github.com/aladdin-zero/moacut-mvp/releases/download/v0.2.0/MOACUT-Setup-0.2.0-Windows-x64.exe)

**Windows 10/11 64비트 · 약 2.08GB · 설치 파일 하나로 실행**

설치 파일을 실행한 뒤 바탕화면 또는 시작 메뉴의 **모아컷**을 누르세요. 이전 버전이 켜져 있다면 작업 표시줄에서 먼저 종료하고 업데이트합니다. 사진과 작업 기록은 보존됩니다.

[배포 페이지](https://github.com/aladdin-zero/moacut-mvp/releases/tag/v0.2.0) · [사용 안내](packaging/USER-GUIDE.md)

## 이번 버전에서 바뀐 점
- 여러 브랜드 상품을 브랜드 입력 없이 먼저 촬영하고, 촬영 후 상품을 선택해 브랜드를 일괄 지정합니다.
- 사진 확인의 왼쪽 패널이 고정되어 목록을 내리며 브랜드를 지정하고 검토할 수 있습니다.
- 브랜드 적용 성공 후 선택 상자가 해제됩니다. 실패하면 선택과 입력을 유지합니다.
- 선택 검토와 전체 상품 검토를 지원합니다. 브랜드 미지정·삭제·전부 제외 상품은 저장하지 않습니다.
- 저장 대기 이유·완료 경로·오류를 저장 화면에 표시합니다.
- 전체 검토 후 이동 질문에서 ‘예’는 폴더 저장 화면으로 이동하고, ‘아니요’는 화면과 검토 상태를 유지합니다.

## 사용 순서
오늘 작업 선택 → 카메라·빈 배경 준비 → 상품당 4컷 촬영 → 상품 선택·브랜드 적용 → 사진 확인·검토 완료 → 저장 위치 선택·폴더 저장.

폴더 저장은 원본을 보존하며 브랜드/상품별로 복사합니다. 사진 휴지통/복원, 묶음 합치기/나누기, 사용자 음성 안내, 날짜별 작업을 제공합니다. 4컷은 묶음 전환 규칙이며 동일 상품이나 사진 종류를 AI가 확정하지 않습니다. 브랜드는 사용자가 지정합니다.

## 실행 조건과 데이터
Windows 10/11 64비트와 USB 카메라를 사용합니다. NVIDIA GPU를 자동 선택하고 GPU가 없거나 실패하면 CPU로 전환합니다. CPU는 느릴 수 있으며 실제 작업속도/품질은 클라이언트 환경에서 확인해야 합니다. 한국어 음성 안내는 설치된 Windows 음성을 사용합니다. 유료 API와 사진 외부 전송은 없습니다.

프로그램은 `%LOCALAPPDATA%\Programs\MOACUT`, 사진·작업은 `%LOCALAPPDATA%\MOACUT\captures`입니다. 제거/업데이트 시 사용자 데이터를 보존합니다. captures 전체와 별도 결과 폴더를 백업하세요. 브라우저를 닫은 뒤에도 앱은 남아 있으므로 작업 표시줄의 모아컷 아이콘으로 종료합니다. 실행 문제는 환경점검.cmd를 참고하세요. 실행 파일은 코드서명이 없습니다.

## 개발 및 재빌드
Python 3.12 64비트와 Windows .NET Framework C# 컴파일러를 사용합니다. 의존성 버전을 고정하고 모델은 별도로 내려받습니다. 고객 사진/작업/API 키/생성된 실행 환경은 Git에 포함하지 않습니다.

```powershell
py -3.12 -m venv .venv-ai
.venv-ai\Scripts\python.exe -m pip install --extra-index-url https://download.pytorch.org/whl/cu126 -r requirements.txt
.venv-ai\Scripts\python.exe camera-test\download_detector.py
.venv-ai\Scripts\python.exe camera-test\server.py --open --port 0
.venv-ai\Scripts\python.exe -m unittest discover -s camera-test -p "test_*.py" -v
node --test camera-test/test_capture_flow.cjs camera-test/test_review_interactions.cjs
node --check camera-test/web/app.js
.venv-ai\Scripts\python.exe -m unittest discover -s packaging -p "test_*.py" -v
.venv-ai\Scripts\python.exe packaging\build_release.py --output delivery\MOACUT-v0.2.0-Windows-x64
.venv-ai\Scripts\python.exe packaging\build_setup.py --source delivery\MOACUT-v0.2.0-Windows-x64 --compiler C:\Tools\InnoSetup\ISCC.exe --output delivery\setup-v0.2.0
```

단일 설치 파일 빌드는 Inno Setup 6.4.3을 사용합니다. 예시 컴파일러 경로는 실제 위치로 바꾸세요. 출력 폴더는 새 경로여야 하며 빌더가 파일별 SHA256을 생성합니다. 설치기는 현재 사용자 권한으로 설치하고 바탕화면/시작 메뉴 바로가기를 만듭니다. 이전 Release는 보존합니다.
