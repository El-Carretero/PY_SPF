# PY_SPF_1.0 배포 파일

- `PY_SPF_1.0.zip`: `PY_SPF_1.0/` 폴더에 앱 소스·원본 NI 리소스·설치/실행 배치·공개 분석 근거·시험·1.0.0 wheel을 담습니다.
- `spitfire_gui_reconstruction-1.0.0-py3-none-any.whl`: Python 패키지 버전 1.0.0의 설치용 앱.
- `SHA256.json`: ZIP과 wheel의 크기 및 SHA256.

ZIP을 풀고 `install.bat`을 실행합니다. 일반 Native는 `run_native.bat`, 읽기 전용 Native는
`run_readonly.bat`, 시뮬레이터는 `run_demo.bat`입니다. 설치는 장비에 접속하지 않습니다.
필요한 32비트 Python을 찾거나 공식 서명 확인 후 준비하고 `.venv-native`에 앱을 설치합니다.
인터넷은 Python/의존성 설치 시 필요합니다. Qt는 `install.bat qt`로 명시적으로 선택합니다.

이전 등록 경로의 Python이 이동·삭제돼도 서명된 공식 설치기의 한 차례 Repair와 경로 재탐색을 유지합니다.
사용자가 `.python32`나 기존 가상환경을 먼저 삭제할 필요는 없습니다.

`py3-none-any`는 앱 wheel의 태그이며 NI DLL이 모든 OS에서 실행된다는 뜻은 아닙니다.
Native는 32비트 Windows Python이 필요합니다. 원본 NI GUI 1.6.0과 장치 펌웨어 버전은 프로젝트 1.0.0과 별개입니다.
런타임 로그·진단 폴더·개인 실장비 원문은 배포물에 포함하지 않습니다.
재생성은 개발 환경에서 `python tools/build_release.py`로 수행합니다.
