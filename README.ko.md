# Empower 독립형 PY_SPF 실행 안내

이 브랜치는 Spitfire GUI 1.6.0에서 복구한 화면과 TDG·ECU·Head 제어를 기반으로 한 External Pump 앱입니다.
Empower 전용 화면·초기 조회·주기 조회·제어 명령을 실행 경로에서 제외합니다.
원본 명령 카탈로그와 분석 자료는 출처 확인용으로 남겨 두며 실제 송신은 External 정책으로 제한합니다.
세부 동작은 [External Pump 안내](EXTERNAL_PUMP.ko.md)에 설명합니다.
패키지 이름은 `spitfire-external-control`, 버전은 `2.0.0`입니다.

## 설치

Python 3.10 이상을 사용합니다. 저장소를 이 브랜치로 체크아웃한 디렉터리에서 별도 가상환경을 만듭니다.

Windows:

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install ".[qt]"
.venv\Scripts\python.exe -m spitfire --backend qt --demo --tcp-port 0
```

Linux/macOS:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install ".[qt]"
.venv/bin/python -m spitfire --backend qt --demo --tcp-port 0
```

`--demo`는 장치 연결 없이 시뮬레이터를 사용합니다. 시뮬레이터에는 Empower 응답이 없으며,
보드 opt-out은 적용된 상태이고 HV와 PC1·PC2는 OFF로 시작합니다.
시뮬레이터는 광출력이나 광학 동기를 재현하지 않습니다.

아래의 `python`은 설치한 가상환경의 Python을 의미합니다.

[배포 wheel](output/external/spitfire_external_control-2.0.0-py3-none-any.whl)로 설치할 수도 있습니다.
저장소 루트에서 다음 명령을 실행합니다. [소스 ZIP](output/external/PY_SPF_external_2.0.0.zip)도 제공합니다.

```sh
python -m pip install "output/external/spitfire_external_control-2.0.0-py3-none-any.whl[qt]"
spitfire-external --backend qt --demo --tcp-port 0
```

설치된 `spitfire`, `spitfire-external`, `python -m spitfire`는 같은 External 앱의 실행 진입점입니다.

## 장치 연결

```sh
python -m spitfire --backend qt --host 10.19.70.13 --port 1024 --local-port 1024 --tcp-host 127.0.0.1
```

`--demo`를 생략하면 실제 UDP 장치 경로입니다. 기본 장치 주소는 `10.19.70.13:1024`,
PC UDP 수신 포트는 `1024`입니다. 동일 PC에서 다른 제어 앱과 같은 로컬 UDP 포트를 동시에 사용하지 않습니다.
TCP 상태 서버는 기본 `127.0.0.1:1001`에서 같은 PC의 클라이언트만 받으며 `--tcp-port 0`으로 끌 수 있습니다.
다른 PC에서 조회하려면 원하는 인터페이스를 `--tcp-host`로 명시합니다.

장치 연결 후 다음 상태를 구분합니다.

1. 통신 연결은 보드·TDG·ECU·Head의 유효 응답으로 갱신됩니다. Empower 응답은 기다리지 않습니다.
2. 보드의 `EMPOPTOUT?`가 1이어야 출력 허용 조건을 만족합니다. 아직 0이면 HV OFF의 최신 readback을 확인한 뒤
   메뉴의 **Apply external pump opt-out**으로 1을 적용합니다. 연결만으로 설정을 자동 변경하지 않습니다.
3. PC RUN은 3초 누르기로 요청하며, 필요한 현재 상태를 검증합니다. HV와 외부 펌프는 자동으로 켜지지 않습니다.
4. PC STOP 또는 Esc는 PC1·PC2 OFF를 요청합니다. HV OFF는 Timing and High Voltage 화면의 별도 조작입니다.

Opt-out은 Spitfire 컨트롤러에 저장되는 구성값입니다. 해당 구성 지원 여부와 외부 펌프·seed·인터록 연결은
실제 장치 및 펌웨어에서 확인해야 합니다. 본 브랜치는 외부 펌프 자체의 전원·발진 드라이버를 제공하지 않습니다.

## Windows NI 화면 엔진

원본 UIR/NI 화면 엔진을 사용하는 경로에는 **32비트 Windows Python 3.10 이상**이 필요합니다.

```bat
python -c "import struct; print(struct.calcsize('P') * 8)"
python run_spitfire.py --backend native --demo --tcp-port 0
```

외부 전용 화면 제한은 Qt와 NI 어댑터에 적용합니다. 원본 화면 리소스와 NI 라이브러리는
`spitfire/resources/`에 있습니다. 이번 변경의 Windows NI 화면·실장비 회귀 검증은 수행하지 않았습니다.

## GUI 없는 확인과 시험

```sh
python -m spitfire --demo --headless --duration 2 --tcp-port 0
python -m pip install ".[qt,test]"
python -m pytest -q
```

Linux에서 Qt 화면 서버가 없는 경우:

```sh
QT_QPA_PLATFORM=offscreen python -m pytest -q
```

실행 화면을 저장하려면 별도 출력 디렉터리를 지정합니다.

```sh
python -m spitfire --backend qt --demo --tcp-port 0 --render-dir external-previews
```

원본 콜백·디코더 분석 스크립트는 `analysis/`에 보존돼 있습니다. 이 스크립트가 사용하는
`analysis/reference/SPITFIRE.EXE`는 분석용 사본이며 앱 실행 경로에서 실행하지 않습니다.
원본과의 과거 대조 결과는 External 변경 전체의 동일성 검증 결과를 뜻하지 않습니다.

## 기록

데이터 로깅을 켜면 `--data-dir`로 지정한 디렉터리(기본 현재 디렉터리)에 `external_datalog.csv`를 기록합니다.
열은 `utc_time,hv_enabled,hv1_kV,hv2_kV,crystal_C,humidity_percent,pc_status`입니다.
HV1/HV2는 원본 GUI와 같은 kV 단위이며, 응답에 `V`가 명시되면 1,000으로 나눠 kV로 정규화합니다.
누락되거나 오래된 측정값은 빈 칸으로 남깁니다. 기존 Empower 수치용 `datalog.csv`와는 별도 파일·형식입니다.

## 구성

| 파일 | 역할 |
|---|---|
| `spitfire/external_policy.py` | 허용 조회·쓰기 및 인자 검사, Empower·전역·raw 경로 차단 |
| `spitfire/external_state.py` | External 응답·신선도·출력 허용 조건 |
| `spitfire/external_ui.py` | 두 GUI의 Empower 화면 제한 및 External 표시 |
| `spitfire/controller.py` | PC RUN/STOP, 응답 확인, 접속·콜백·TCP 통합 |
| `spitfire/scheduling.py` | 조회 전용 초기화·폴링, STOP 우선 큐 |
| `spitfire/gui.py`, `spitfire/native.py` | Qt 및 NI 화면 어댑터 |
| `spitfire/tcp.py` | 로컬 상태 조회 및 External telemetry 호환성 |
| `spitfire/simulator.py` | Empower 없는 테스트용 보드·TDG·ECU·Head |
| `spitfire/protocol.py`, `spitfire/callbacks.py`, `spitfire/decoders.py` | 원본에서 복구한 규약·변환 근거와 재사용되는 처리 |

기존 `output/`의 `1.6.0.post1` wheel과 `Spitfire_Python_1_6_0.zip`은 원본 재구현 패키지입니다.
External 버전에는 이 브랜치의 소스 또는 `output/external/`의 2.0.0 wheel을 설치하세요. 첨부 ZIP과 원본 재구현을 비교한 이전 보고서는
[comparison/external-pump-1.5.1 브랜치](https://github.com/El-Carretero/PY_SPF/tree/comparison/external-pump-1.5.1)에 있습니다.

## 선택형 통신 진단 로그

`--comm-log-dir <폴더>`를 지정하면 원문 UDP·요청 순번·COMSTATUS/Fault·연결·timeout·Reset
과정을 별도 회전 JSONL로 기록합니다. 기본 OFF이며 기존 Data Logging과 독립적입니다.
[사용법·Wireshark CSV 비교·보존 및 손실 한계](COMMUNICATION_LOGGING.ko.md)를 참고하세요.
