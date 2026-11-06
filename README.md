# Native PY_SPF 1.3

현재 `main`의 기준은 **Native PY_SPF 1.3 설치형 Windows 앱**입니다. 원본 Spectra-Physics Spitfire GUI **1.6.0**의 NI 화면과 통신 규칙을 사용하며, 프로젝트 버전 **1.3.0**과 장치 펌웨어 버전은 별개입니다. [패치노트](CHANGELOG.ko.md)는 이전 버전부터 현재 변경까지 최신순으로 기록합니다.

## 다운로드와 실행

- [Windows x86 설치 파일](output/native-installer/PY_SPF_1.3_Setup_x86.exe)
- [Portable ZIP](output/native-installer/PY_SPF_1.3_win32_portable.zip)
- [SHA256 체크섬](output/native-installer/SHA256SUMS)
- [설치·실행·제거 및 환경 격리 검증 기록](output/native-installer/install-validation.json)

Windows 10 **1903 이상** 또는 Windows 11에서 실행합니다. Python·pip·venv·NI Runtime을 별도로 설치할 필요가 없습니다. 설치 파일은 현재 사용자 계정에 앱 전용 런타임을 설치하며 관리자 권한을 요구하지 않습니다. 배포 EXE에는 코드 서명이 없습니다.

설치 후 시작 메뉴의 **Native PY_SPF 1.3 Demo (no equipment)**로 장비 없이 화면을 확인할 수 있습니다. **Native PY_SPF 1.3**은 설정된 실장비 연결을 사용합니다. Portable ZIP은 압축을 모두 풀고 폴더 전체를 유지한 상태로 `PY_SPF.exe`를 실행합니다.

기본 설치 위치는 `%LOCALAPPDATA%\Programs\Native_PY_SPF_1.0`, 설정·데이터·세션 로그는 `%LOCALAPPDATA%\PY_SPF_1.0`입니다. 기존 Python·venv·NI 등록, PATH·파일 연결, 방화벽·어댑터·네트워크 설정을 변경하지 않습니다. [설치·업데이트·제거 안내](packaging/windows/README.ko.md)에서 경로 제한과 보존되는 사용자 데이터를 확인하세요.

현재 설치 파일의 자동 검증은 **시뮬레이터를 사용한 Native GUI, 설치·실행·제거 및 환경 격리 시험**입니다. 실장비 제어와 광학적 Emission을 검증한 결과는 아닙니다. [배포 파일과 검증 출처](output/native-installer/README.md)에 정확한 소스와 시험 기록이 있습니다.

1.3에서는 Reset/Fault 작업의 중복 등록을 제한하고, **View → Communication Monitor**에서 현재 세션 로그를 읽는 별도 통신 확인 패널을 엽니다. 진단 로그의 대기열·파일 크기도 제한합니다. 패널은 장치에 조회나 제어 명령을 보내지 않습니다. [사용법과 로그 형식](docs/communication-monitor.md), [변경과 검증 범위](CHANGELOG.ko.md#130--resetfault-중복-제한과-통신-확인-패널)를 확인하세요.

1.2는 Timing 창의 **HV ON/OFF** 스위치를 표시하고 주변 배치를 조정합니다. [레이아웃 변경과 검증 범위](docs/hv-switch-1-2.md)를 확인하세요.

1.2.1에서는 기존 반복률 입력을 EXT Pump/AMP 표시와 공유합니다. Empower PRF 대신 확인된 입력 주파수와 DIVISOR로 계산하며, 외부 TTL 주파수 측정값을 뜻하지 않습니다. [공용 입력과 검증 범위](docs/shared-ext-rate.md)를 확인하세요.

## 문서와 이전 버전

- [설치·실행 요약](README.ko.md)
- [최신순 패치노트](CHANGELOG.ko.md)
- [하드웨어–소프트웨어 통합 제어 흐름: 영문·한글 문서와 PDF](docs/README.md)
- [Native 1.0 제어 로직 변경 및 과거 실장비 관측 범위](RELEASE.ko.md)
- [소스 실행·개발·시험](docs/source-development.md)
- [이전 배포물과 분석 기록](Legacy/README.md)
- [원본 NI 리소스와 타사 구성요소 출처](THIRD_PARTY_NOTICES.md)
