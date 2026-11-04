# Native PY_SPF 1.0 설치와 실행

현재 배포는 원본 NI GUI **1.6.0**을 사용하는 **Native PY_SPF 1.0** Windows 앱입니다. 프로젝트 패키지 버전은 **1.0.1**이며, 장치의 IDN 응답에 표시되는 펌웨어 버전과 별개입니다.

## 설치

1. Windows 10 **1903(빌드 18362) 이상** 또는 Windows 11에서 [설치 파일](output/native-installer/PY_SPF_1.0_Setup_x86.exe)을 실행합니다. 이 EXE는 코드 서명이 없으며, [SHA256 체크섬](output/native-installer/SHA256SUMS)으로 파일을 대조할 수 있습니다.
2. 기본 설치 폴더 `%LOCALAPPDATA%\Programs\Native_PY_SPF_1.0`을 유지하거나 비어 있는 새 폴더를 선택합니다. 설치는 현재 사용자 계정에 적용되고 관리자 권한을 요구하지 않습니다.
3. 시작 메뉴에서 **Native PY_SPF 1.0 Demo (no equipment)**를 열면 장비 없는 시뮬레이터로 Native 화면을 확인합니다. **Native PY_SPF 1.0**은 설정된 장비에 접속하는 일반 실행입니다.

필요한 Python·패키지·NI DLL·GUI 리소스가 앱에 포함돼 있습니다. 별도 Python 설치, `install.bat`, pip 또는 venv 준비는 필요하지 않습니다. 설치 완료 화면의 앱 실행 항목과 바탕 화면 바로가기는 기본적으로 선택되지 않습니다.

[Portable ZIP](output/native-installer/PY_SPF_1.0_win32_portable.zip)을 사용하는 경우 압축을 전부 풀고 폴더 안의 `PY_SPF.exe`를 실행합니다. `_internal`과 `cvirte`를 포함한 폴더 전체가 필요합니다. 장비 없는 데모 실행은 다음과 같습니다.

```bat
PY_SPF.exe --demo --tcp-port 0 --local-port 0
```

## Internal 10 Hz 설정

1.0.1부터 Timing의 **INTERNAL AMP REP RATE** 입력 범위는 **10–10000 Hz**입니다. Amplifier Trigger를 Internal로 선택하고 `10`을 입력합니다. Divisor가 `1`일 때 내부 Pump/Amp 표시가 모두 `10 Hz`가 됩니다. 입력한 값의 적용 여부는 장비의 주파수 조회 응답으로 확인합니다. 상세한 검증 범위는 [Internal 10 Hz 변경 기록](docs/internal-trigger-10hz.md)에 있습니다.

## 설정·로그·제거

| 항목 | 위치 또는 동작 |
|---|---|
| 기본 프로그램 설치 위치 | `%LOCALAPPDATA%\Programs\Native_PY_SPF_1.0` |
| 설정 | `%LOCALAPPDATA%\PY_SPF_1.0\settings\config.sp` |
| 데이터 | `%LOCALAPPDATA%\PY_SPF_1.0\data` |
| 세션 로그 | `%LOCALAPPDATA%\PY_SPF_1.0\logs\<UTC>_<UUID>` |
| 기존 Python·venv·NI 등록 | 변경하지 않음 |
| PATH·파일 연결·시스템 로캘 | 변경하지 않음 |
| 방화벽·드라이버·어댑터·네트워크 설정 | 변경하지 않음 |

실장비 연결은 PC에 이미 구성된 케이블·어댑터·네트워크를 사용합니다. 설치 프로그램은 장비 검색이나 제어 명령을 실행하지 않습니다. 일반 앱 실행은 시작·재연결 때 Empower Opt-out ON을 요청하며, 읽기 전용 실행은 자동 Opt-out을 포함한 장치 쓰기를 차단합니다.

업데이트나 제거 전에 앱을 직접 종료합니다. Windows **설치된 앱 / 앱 및 기능**에서 제거하며, 별도 사용자 설정·데이터·로그는 남습니다. 원본 Native 런타임은 `PY_SPF.exe` 전체 경로에 UTF-8 **258바이트** 제한이 있으므로 기본 설치 경로를 권장합니다. 세부 사항은 [설치·격리·업데이트·제거 안내](packaging/windows/README.ko.md)에 있습니다.

## 검증과 문서

[현재 배포의 검증 기록](output/native-installer/install-validation.json)은 시뮬레이터를 사용한 Native GUI, 한글·이모지 경로, 설치·실행·제거와 환경 격리 시험입니다. 실장비 구동이나 광학적 Emission을 검증한 것은 아닙니다. [배포 출처](output/native-installer/README.md)에서 해당 소스 커밋과 자동 시험 기록을 확인할 수 있습니다.

- [통합 제어 흐름 문서와 영·한 PDF](docs/README.md)
- [Native 1.0 제어 변경과 과거 관측 범위](RELEASE.ko.md)
- [소스 실행·개발·시험](docs/source-development.md)
- [이전 버전과 역사적 분석](Legacy/README.md)
- [타사 구성요소 출처](THIRD_PARTY_NOTICES.md)
