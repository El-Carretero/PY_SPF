# Windows 실행 및 조회 전용 장비 자동 검증

이 검증기는 **실행 호환성과 조회 응답의 해석**을 점검합니다. PASS는 레이저 운전 허가나
물리적 안전 인증이 아닙니다. 실제 장비 검사 전 발진·고전압을 물리적으로 억제하는 절차는
사용자가 장비의 SOP에 따라 수행해야 하며, 소프트웨어가 이를 대신 확인하지 않습니다.

## 1. 준비

Python 3.10 이상과 Tk, pySerial 3.5가 필요합니다. 제공 ZIP을 압축 해제한 폴더에서 실행합니다.
Windows XP는 지원 대상이 아닙니다. Python 실행 환경과 GUI 표시가 가능한 Windows PC를 사용하십시오.
검증 스크립트는 관리자 권한, 자동 설치, 방화벽/NIC/COM 설정 변경을 요구하거나 수행하지 않습니다.

이미 프로그램이 실행되는 환경이라면 설치 없이 다음 단계로 진행합니다. 독립 환경이 필요하면:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index --find-links release\vendor pyserial==3.5
.\.venv\Scripts\python.exe validate_spitfire.py offline
```

검증은 기존 GUI 설정 파일을 읽거나 저장하지 않습니다. 저장된 mode가 UDP여도
오프라인 검사 창은 명시적으로 Simulator만 사용합니다.

## 2. Windows / 오프라인 검사

```powershell
py validate_spitfire.py offline
```

PowerShell 래퍼도 제공합니다:

```powershell
.\validate_windows.ps1
# 별도 가상환경을 쓰는 경우
.\validate_windows.ps1 -PythonExecutable .\.venv\Scripts\python.exe
```

PowerShell 정책 때문에 ps1 실행이 차단되면 위의 Python 명령으로 실행하십시오.
시뮬레이터 창이 잠깐 나타난 뒤 자동으로 닫힙니다. 검사 중 그 창을 직접 조작하지 마십시오.

검사 항목:

- Python·Tk·pySerial import, 고정 조회 목록과 command catalogue 일치
- Simulator 연결, 1,250 Hz 설정과 readback, 편집 중 1,500 Hz 보존, USE READBACK
- 7개 탭과 서비스 제어의 표시 영역, raw RS-232 창이 포트를 열지 않는지, 정상 종료
- 포함된 전체 회귀 테스트: 실제 UDP 테스트는 **127.0.0.1 내부**에서만 수행

GUI 검사는 모든 Python socket 송신/연결과 COM 포트 열기를 차단한 별도 프로세스에서 실행합니다.
회귀 테스트는 loopback 통신만 허용합니다. 이 장치는 실수 방지를 위한 Python 수준 방어이며
악의적으로 수정된 코드에 대한 운영체제 보안 경계는 아닙니다.
GUI가 없거나 DPI/화면 크기 때문에 제어가 잘리면 PASS가 되지 않습니다.
테스트 프로세스는 각각 최대 60초 후 종료합니다.

## 3. 실제 장비 조회 검사

원본 Spitfire GUI 및 다른 제어 프로그램을 닫아 UDP 1024 포트를 비우십시오.
장비 주소와 NIC 연결은 사용자가 확인해야 합니다. 주소를 검색하거나 PC 네트워크를 자동 변경하지 않습니다.

```powershell
py validate_spitfire.py hardware --host 10.19.70.13
```

가상환경을 쓴다면 같은 명령의 `py`를 `.\.venv\Scripts\python.exe`로 바꿉니다.
여러 NIC가 있으면 장비에 연결된 PC의 실제 IPv4 주소를 `--local-host`로 지정합니다.
다음은 주소와 IDN 확인 조건을 명시한 예입니다. PC 주소와 IDN 조건은 실제 값으로 바꾸십시오.

```powershell
py validate_spitfire.py hardware --host 10.19.70.13 --local-host 10.19.70.1 --expect-idn Spitfire
```

`--expect-idn`은 응답에 포함되어야 하는 문자열이며, 대소문자를 구분하지 않습니다.
장비 serial 등 고유 문자열을 알고 있다면 이를 지정할 수 있습니다.

PowerShell 예:

```powershell
.\validate_windows.ps1 -Mode Hardware -HostAddress 10.19.70.13 -ExpectIdn Spitfire
```

장비 검사는 오프라인 필수 검사가 모두 PASS인 경우에만 시작합니다.
48개의 고정 조회 명령으로 identity/version, HV 상태, 측정 출력·전류·HV,
모듈 status/fault, opt-out/override, 주파수·온도·습도·Delay 등을 읽습니다.
자동 장비 탐색, 임의 command ID, raw 명령 입력 기능은 없습니다.

| 조건 | 동작 |
|---|---|
| 첫 IDN 무응답·오류·식별 불가 또는 기대 IDN 불일치 | 이후 조회 중단 |
| HV ON / 양수의 출력·다이오드 전류·측정 HV | 추가 조회 중단, WARN 및 미완료 기록 |
| 해당 초기 측정값이 음수·NaN·잘못된 응답 | 0으로 간주하지 않고 실패·중단 |
| 연속 2회 통신 실패 | 추가 조회 중단 |
| 개별 응답 해석 실패 | FAIL 기록; 초기 확인 항목 외에는 제한 내에서 다른 조회 계속 |
| 모듈 통신 오류 mask 0x800 | 해당 항목 FAIL |
| fault word 비영 / opt-out·override 활성 | WARN 기록; 해제·복구하지 않음 |
| Delay 숫자만 있고 모드 flag 없음 | 모드 미검증 WARN |
| 보고서/trace를 기록할 수 없음 | 전송 중단; 조회 전 로그 기록 실패 시 해당 패킷 미전송 |
| Ctrl+C / 시간 제한 / 종료 | 소켓만 닫음. OFF, HV OFF, RESET 등을 보내지 않음 |

측정값에 임의의 허용 오차를 적용하지 않으므로 작은 양수나 음수 offset도 검사 중단 사유가
될 수 있습니다. 장비가 0이라고 응답해도 실제 출력과 잔류 HV가 0임을 증명하지 않습니다.
쿼리는 한 번에 하나씩 보내며, reply는 지정한 IP·포트 및 현재 command ID가 일치해야 합니다.

기본값과 제한:

- query timeout 2초, 허용 0.1–5초: `--timeout`
- 응답 처리 후 다음 query까지 0.25초, 최소 0.2초: `--interval`
- 전체 조회 1회, 최대 5회: `--cycles`
- 장비 통신 단계 최대 120초, 최대 설정 300초: `--max-seconds`
- 원격/로컬 UDP 포트 각각 1024: `--remote-port`, `--local-port`
- 호스트명 대신 IPv4 한 주소만 허용; broadcast/multicast 및 .0/.255 대상 거부

시간 제한은 다음 송신과 응답 대기에 적용됩니다. OS 파일 I/O가 멈추는 상황이나
프로세스 강제 종료에서는 완성 보고서를 보장하지 않으며, 이미 전송된 UDP 패킷도 회수할 수 없습니다.
기본 48개 query는 정상적인 로컬 응답에서 약 12초 이상 걸립니다. 오프라인 점검 시간은 별도입니다.

## 4. 생성되는 결과

`validation_reports/YYYYMMDD_HHMMSS_<ID>/` 아래에 실행별로 새 폴더를 생성합니다.

- `report.html`: 브라우저에서 열어 보는 결과와 항목별 증거
- `report.json`: 자동 수집 가능한 구조화 결과, 대상 주소, 환경, 버전, 판정 범위
- `trace.jsonl`: UTC 시각, 송신 시도/완료, 실제 송신 datagram의 hex, 검증된 endpoint의 원문 응답
- `gui.json`, `tests.json`, `unittest.txt`: 시뮬레이터 GUI와 전체 테스트 결과
- 선택한 경우 `exe.json`: 빌드된 Windows EXE의 시뮬레이터 자체 검사 결과

trace는 패킷 캡처 파일(PCAP)이 아닙니다. 무관한 endpoint에서 폐기한 패킷이나
전체 네트워크 트래픽을 기록하지 않습니다. 보고서에는 장비 ID, IP, 경로가 들어갈 수 있습니다.
공유 전에 내용을 확인하십시오. HTML에는 외부 스크립트나 원격 리소스가 없습니다.

| 종료 코드 | 의미 |
|---|---|
| 0 | 수행한 필수 검사 PASS. 생략된 선택 항목은 보고서 확인 |
| 1 | 실패 발생 |
| 2 | WARN 또는 필수 항목 미완료. CLI 인자 오류도 argparse 관례에 따라 2 |
| 130 | Ctrl+C로 중단 |

비 Windows에서 실행하면 Windows 항목은 SKIP이고 `windows_execution_verified=false`입니다.
EXE를 지정하지 않으면 EXE 항목도 SKIP입니다. 어떤 경우든 `physical_safety_verified=false`입니다.
wheel만 설치한 환경에는 회귀 테스트 소스가 없으므로 해당 항목은 선택 SKIP가 됩니다.
전체 검증에는 이 ZIP의 `validate_spitfire.py`를 사용하십시오.

## 5. Windows EXE도 자동 점검하기

현재 버전의 빌드 스크립트를 Windows에서 실행하면 EXE와 SHA-256 기록 파일을 함께 만듭니다.
빌드는 기존 방식대로 pip/PyInstaller 설치를 수행하며 인터넷이 필요할 수 있습니다.
검증 스크립트 자체는 패키지를 설치하지 않습니다.

```powershell
.\build_windows.ps1
.\validate_windows.ps1 -ExePath .\dist\SpitfirePythonControl.exe
```

Python 명령으로도 실행할 수 있습니다:

```powershell
py validate_spitfire.py offline --exe .\dist\SpitfirePythonControl.exe
```

`SpitfirePythonControl.validation.json`의 파일명·버전·SHA-256·self-test protocol을 확인한 뒤
`--simulator --self-test-report ...`로 EXE를 실행합니다. 기록 파일이 없거나 해시가 다르면
EXE를 실행하지 않습니다. 이는 원본 vendor EXE/구버전을 잘못 고르는 실수를 막는 장치이며
제작자 인증용 디지털 서명이 아닙니다. 신뢰할 수 있는 이 소스로 직접 빌드한 파일에만 사용하십시오.
EXE 검사 인자와 UDP 관련 인자는 동시에 사용할 수 없습니다.

## 6. 자동화가 검증하지 않는 것

실제 ON/OFF·HV switching·모터·setpoint 변경·reset·override·raw RS-232 송신은 수행하지 않습니다.
인터록 차단 능력, 비상 정지, 냉각 유지, 광출력, HV 잔류 전압, 단위의 물리적 보정도 검증하지 않습니다.
PRF 변환은 원본 코드 및 simulator 왕복 기준이며, 실제 반복률은 별도 계측이 필요합니다.
이러한 능동 장비 검증은 [COMMISSIONING.md](COMMISSIONING.md)의 별도 절차로 수행해야 합니다.
