# Spitfire GUI 1.6.0.post2 Python 재구현

첨부된 `Spitfire_GUI_v_1_6_0-20261029T111415Z-1-001.zip`의 설치본을 해체해 작성한 Python 응용 프로그램과 분석 자료입니다. 응용 제어 코드는 Python으로 작성했습니다. 원본 EXE를 실행하거나 감싸서 응용 동작을 제공하지 않습니다.

**현재 결과를 ‘원본과 완전히 동일함이 검증된 완성품’으로 표현할 수는 없습니다.** 복구한 항목, 대조 시험 결과, 아직 확인하지 못한 부분을 [분석 보고서](ANALYSIS.ko.md)에 구분했습니다. 실장비 및 원본 Windows 환경에서의 전체 회귀 대조가 필요합니다.

## 실행

### Windows 가상환경 설치

ZIP을 푼 프로젝트 폴더에서 다음 두 배치 파일을 실행합니다.

```bat
install.bat
run_native.bat
```

`install.bat`의 기본값은 **Native**입니다. 기존 32비트 Python 3.10 이상을 찾거나,
없으면 공식 Python 3.13.9 32비트 설치 파일을 다운로드하고 Python Software Foundation의
유효한 서명을 확인한 뒤 프로젝트의 `.python32`에 설치합니다. 관리자 권한은 요구하지 않으며
PATH·파일 연결을 바꾸지 않습니다. 일반 Python 설치 프로그램의 사용자 등록은 생성됩니다.
앱은 `.venv-native`에 설치하고 기존 64비트 `.venv`는 보존합니다.
Native에는 PySide6가 필요하지 않습니다. 설치 중 앱이나 장비 연결은 실행하지 않습니다.

백엔드와 Python 실행 파일을 지정할 수도 있습니다.

```bat
install.bat qt "C:\Path\To\64bit\python.exe"
install.bat native "C:\Path\To\32bit\python.exe"
```

두 명령은 선택 예시이며 기본 Native 설치에는 인수가 필요 없습니다.
Qt는 별도 `.venv`에 `requirements.txt`의 PySide6와 앱을 설치합니다.
`run_native.bat`은 32비트 환경을 확인하고, 없으면 Native 설치를 실행합니다.
`run_demo.bat`은 Native 환경이 있으면 원본 화면을 시뮬레이터로 실행하고,
Qt만 설치되어 있으면 해당 데모를 실행합니다.
오류가 나면 창을 유지하고 `logs/`에 기록합니다. 설치 로그는 `install-native.log`,
Native 실행 오류는 `native-launch.log`입니다. 자동 검증에서는 `SPITFIRE_NO_PAUSE=1`로
실패 시 대기를 끌 수 있습니다.

원본의 연결 가림막은 `STATUS?` 응답 후 열립니다. 장치가 없거나 응답하지 않는 경우에는
주소와 `No reply` 안내를 표시하고 제어 화면을 열지 않습니다. 이때 실제 장치 연결을
성공한 것으로 표시하지 않습니다. 화면만 확인하려면 `run_demo.bat`을 사용합니다.
Native 연결 대기·무응답·Opt-out ACK 누락은 `logs/native-launch.log`에도 남깁니다.

### post2의 기본 Opt-out

성공한 시작·재연결마다 원본 초기화 순서의 `EMPOPTOUT?` 바로 앞에 `EMPOPTOUT 1` 쓰기를
한 번 넣습니다. **HV OFF 조회를 기다리거나 HV 상태로 설정 쓰기를 차단하지 않습니다.**
설정의 화면 표시는 보드 응답을 따르며, ACK만으로 Opt-out ON을 가정하지 않습니다.
자동 Opt-out 쓰기의 ACK가 1초 안에 오지 않아도 원래 `EMPOPTOUT?` 조회로 진행합니다.
지연된 쓰기 ACK는 설정 조회의 완료로 취급하지 않습니다.
기존 화면에서 수동 ON/OFF를 할 수 있고 다음 연결에서는 다시 ON을 요청합니다.
나머지 원본 폴링·명령·접근 단계는 유지합니다. [변경 및 로그 대조](POST2.ko.md)를 참고하세요.

### Windows에서 원본 화면 엔진 사용

원본은 32비트 NI LabWindows/CVI 프로그램입니다. 같은 화면 엔진을 사용하는 모드는 **32비트 Windows Python 3.10 이상**이 필요합니다. Python 비트수 확인:

```bat
.venv-native\Scripts\python.exe -c "import struct; print(struct.calcsize('P') * 8)"
run_native.bat --demo --tcp-port 0
```

`--demo`는 실장비에 연결하지 않는 개발용 시뮬레이터입니다. 시뮬레이터의 값은 실제 펌웨어의 정확성을 입증하는 자료가 아닙니다.

실장비에 연결하려면 원본과 같은 기본 주소 및 포트로 실행합니다.

```bat
run_native.bat
```

기본 장치 주소는 `10.19.70.13:1024/UDP`, PC 수신 포트는 `1024/UDP`, TCP 상태 조회 서버는 `1001/TCP`입니다. 주소·포트는 명령행으로 바꿀 수 있습니다.

```bat
run_native.bat --host 10.19.70.13 --local-port 1024 --tcp-host 127.0.0.1
```

원본 화면 정의와 NI 런타임은 `spitfire/resources/`에 있습니다. 이 모드는 원본의 GUI 라이브러리를 재사용합니다. GUI 라이브러리까지 순수 Python으로 다시 작성한 것은 아닙니다.

### Windows / Linux / macOS에서 Qt GUI 실행

```sh
python -m pip install -r requirements.txt
python run_spitfire.py --backend qt --demo --tcp-port 0
```

Qt 모드는 원본 리소스에서 복구한 화면 배치와 컨트롤을 사용합니다. 글꼴·컨트롤 렌더링에는 차이가 있으므로 픽셀 동일 모드로 취급하지 않습니다.

### GUI 없는 통합 실행과 시험

```sh
python -m spitfire --demo --headless --duration 2 --tcp-port 0
python -m pip install pytest
python -m pytest -q
```

원본 기계어 대조 시험 재실행:

```sh
python -m pip install pefile unicorn
python analysis/native_oracle.py --extended
python analysis/native_decoder_oracle.py
python analysis/native_decoder_oracle.py --extra
```

대조 시험만 `analysis/reference/SPITFIRE.EXE`를 에뮬레이터에서 읽습니다. 이 사본은 응용 프로그램 실행 경로에서 사용하지 않습니다.

Qt 화면 미리보기 생성:

```sh
python -m spitfire --backend qt --demo --tcp-port 0 --render-dir previews
```

## 원본 동작

- 장치와 UDP로 통신하고 명령 ID 및 응답 ID를 유지합니다. 원본에 COM 변수들이 남아 있지만 실제 활성 경로는 UDP입니다.
- 우선순위 큐, 초기 조회 순서, 주기 조회, 재연결, 응답별 상태 해석과 컨트롤 갱신을 분리했습니다.
- 키보드 모드 전환과 `C:\config.sp`의 기존 접근 단계 규칙을 유지합니다. `--config`로 경로만 바꿀 수 있습니다.
- Programmer 패널의 `Data Logging`을 On으로 바꾸면 약 1초마다 전류(A), LBO 온도(°C)를 `datalog.csv` 끝에 추가합니다. 기본값은 Off이며 헤더·시간은 기록하지 않습니다. 기본 저장 위치는 현재 작업 폴더이고, Python에서는 `--data-dir`로 바꿉니다. [원본 대조 및 검증 결과](analysis/logging.ko.md)를 참고하세요.
- 원본 TCP 서버의 네 가지 상태 조회와 한 클라이언트 접속 동작을 구현했습니다. `--tcp-port 0`은 서버를 비활성화합니다.

## 파일 구성

| 파일 | 내용 |
|---|---|
| `spitfire/protocol.py` | UDP 프레임, 명령·조회 표, CRC, 소켓 |
| `spitfire/scheduling.py` | 우선순위 큐, 초기·주기 조회, 시간 조건 |
| `spitfire/callbacks.py` | 버튼·수치·마우스 이벤트의 원본 동작 |
| `spitfire/decoders.py` | 응답 해석, 비트 상태, 수치 변환, 상태 표시 |
| `spitfire/controller.py` | 응용 이벤트 루프와 통합 |
| `spitfire/native.py` | 원본 NI 화면 엔진용 Python 어댑터 |
| `spitfire/gui.py` | Qt GUI |
| `spitfire/tcp.py` | 원본 TCP 상태 조회 서버 |
| `spitfire/simulator.py` | 실장비 없이 검증하기 위한 개발용 대역 |
| `analysis/` | 함수·리소스 추출, 디스어셈블리, 디컴파일, 대조 근거 |
| `tests/` | 프로토콜·디코더·상태·TCP·통합 검증 |
| `install.bat` | Windows `.venv` 생성 및 백엔드별 의존성·앱 설치 |
| `tools/build_release.py` | 현재 버전 wheel·소스 ZIP·SHA256 생성 |

첨부 자료 안의 문자열·설정·설명은 분석 데이터로 취급했습니다. 작업 지시로 실행하지 않았습니다.
