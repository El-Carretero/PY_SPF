# 소스 실행·개발·시험

다음은 저장소 소스를 직접 실행하는 개발 절차입니다. 현재 Windows 설치형 EXE 사용법은 [설치·실행 안내](../README.ko.md)와 [Windows 설치 문서](../packaging/windows/README.ko.md)에 있습니다.

아래 명령은 저장소 **루트 디렉터리**에서 실행합니다. 프로젝트 패키지 버전은 **1.0.0**, 원본 NI GUI 리소스는 **1.6.0**이며 장치 펌웨어 버전과 별개입니다.

## Windows Native 소스 실행

저장소 루트에서 `install.bat`을 실행합니다. 설치 뒤 원본 화면은 `run_native.bat`으로 시작합니다.

```bat
install.bat
run_native.bat
```

기본 설치는 Native용 **32비트 Python 3.10 이상**을 찾아 `.venv-native`를 만듭니다.
없으면 공식 CPython 3.13.9 x86 설치 파일을 받아 Python Software Foundation 서명을 확인한 뒤 설치합니다.
PATH와 파일 연결을 바꾸지 않으며 공식 설치 프로그램의 사용자 등록은 생성됩니다.
기존 64비트 Qt `.venv`는 보존합니다. Native에는 PySide6가 필요하지 않습니다.
소스 설치 절차의 구현은 [tools/install_windows.ps1](../tools/install_windows.ps1)에 있으며,
설치 중에는 앱이나 장비에 접속하지 않습니다.

이전 폴더의 Python 등록만 남아 있으면 설치 후 등록·설치 로그의 실제 경로를 재탐색하고,
필요할 때 공식 설치기의 Repair를 한 번 수행합니다. 기존 Python을 수동 삭제할 필요는 없습니다.
Python 검사는 제한 시간과 `-I` 격리를 사용하며, 결과는 `logs/python-probes.json`에 남습니다.
설치·실행은 상속된 `PYTHONHOME`·`PYTHONPATH`의 영향을 피하고 저장된 사용자 환경변수는 변경하지 않습니다.

설치 오류는 `logs/install-native.log`, Python 복구는 `logs/python32-repair.log`,
실행 오류는 `logs/native-launch.log`에서 확인합니다. 실패 시 배치 창은 닫히지 않습니다.
자동 검증에만 `SPITFIRE_NO_PAUSE=1`을 설정해 대기를 끌 수 있습니다.

## 세 가지 실행 방법

```bat
run_native.bat
run_readonly.bat
run_demo.bat
```

각각 일반 장치 제어, **장치 조회만 허용하는 Native**, 장치 없는 시뮬레이터입니다.
읽기 전용에서는 자동 Opt-out·Reset·RUN/OFF·HV·모터·온도·raw 쓰기를 차단합니다.
Opt-out 값은 보드가 응답한 그대로 표시하며, 읽기 전용 실행으로 설정을 켜지 않습니다.
일반 모드는 시작과 재연결 때 `EMPOPTOUT 1`을 요청한 뒤 `EMPOPTOUT?`로 확인합니다.
HV OFF 선행 확인은 없고, 자동 쓰기 ACK가 누락돼도 제한 시간 후 조회로 진행합니다.

연결 전에는 전체 원본 레이아웃과 메뉴를 표시하되 `OFFLINE`·`NOT CONNECTED`로 상태를 알리고
장치 입력·수치를 비활성화합니다. 연결된 읽기 전용 화면에서도 장치 입력은 허용하지 않습니다.
오프라인 기본 수치는 실측값이 아니며 장치 없는 확인에는 데모를 사용합니다.

기본 장치 주소는 `10.19.70.13:1024/UDP`, PC 수신 포트는 `1024/UDP`입니다.
다음 예시는 읽기 전용 실행과 진단 저장 위치를 명시하고 TCP 상태 서버를 끕니다.

```bat
run_native.bat --read-only --tcp-port 0 --diagnostics-dir logs/session
```

Windows에서는 UDP 수신 포트를 독점 사용합니다. 다른 앱이나 수집기가 이미 같은 포트를 쓰고 있으면
중복 bind 대신 연결 오류를 표시합니다. 기존 장비 제어 프로그램의 실행 상태를 확인해 포트 충돌을 해결합니다.

기존 TCP 상태 조회 서버를 쓰면 기본 포트는 `1001/TCP`입니다. `--tcp-host 127.0.0.1`로
로컬 인터페이스만 선택할 수 있습니다. TCP 질의를 장치 쓰기로 전달하지 않습니다.
실장비 UDP 송신 간격은 최소 0.25초입니다. 데모의 기본 속도와는 다릅니다.
응답 태그와 중복을 구분하지만 프로토콜에 거래 고유번호가 없어 늦은 동일 태그 응답을 완전히 식별하지는 못합니다.

## 진단 기록

`run_native.bat`은 기본으로 `logs/native/`를 사용합니다. `--diagnostics-dir`를 뒤에 지정하면
저장 위치를 바꿀 수 있습니다. 직접 Python으로 실행할 때는 이 옵션을 명시한 경우 기록합니다.

- `events.jsonl`: 앱 TX/RX와 컨트롤러 이벤트.
- `heartbeat.json`: PID·프로젝트/NI 버전·루프 진행·마지막 NI 작업·통신 상태와 카운터.
- `stacks.txt`: 메인 루프 진행이 10초 이상 없을 때의 스택. 모달 창이나 종료 처리도 포함될 수 있습니다.

관측 스레드는 NI나 소켓 함수를 호출하지 않습니다. 스택은 당시 실행 위치의 근거이며,
그 자체를 NI Runtime HALT·네트워크 어댑터 고장의 확정 증거로 읽지 않습니다.
진단 파일은 로컬 기록이며 배포 ZIP에 포함하지 않습니다.

## Qt와 GUI 없는 실행

Qt는 64비트 Python에서 별도로 설치합니다.

```bat
install.bat qt
.venv\Scripts\python.exe -E -s run_spitfire.py --backend qt --demo --tcp-port 0
```

Qt는 별도 Python 화면으로 원본 NI의 픽셀 동일 모드가 아닙니다.
Linux/macOS의 개발용 데모와 시험은 다음과 같습니다.

```sh
python -m pip install ".[qt,test]"
python -m spitfire --demo --headless --read-only --tcp-port 0 --diagnostics-dir logs/demo
python -m pytest -q
```

원본 기계어 대조에는 `.[analysis]` 의존성과 [analysis/reference/](../analysis/reference/)의 검증 사본을 사용합니다.
원본 EXE는 일반 앱 실행에 사용하지 않습니다. 공개 프로토콜 fixture는 합성 예제이며 실장비 로그가 아닙니다.
새 버전의 변경·관측 범위와 남은 제한은 [RELEASE.ko.md](../RELEASE.ko.md)에 있습니다.

이전 Native 1.0 소스의 실장비 읽기 전용 30분 관측과 메뉴를 약 45초 열어 두는 검증을 마쳤습니다.
관측 중 재연결·재시도 한도 초과 조회 timeout·새 Fault 변화는 0회였습니다.
조회 재시도 62회가 있었으며 실제 장치 쓰기 0회인 시험이므로 모든 제어 동작을 인증하지 않습니다.

## 배포 제작

개발용 소스 ZIP과 wheel은 `python tools/build_release.py`로 생성합니다.
출력은 Git에서 제외한 `dist/source/PY_SPF_1.0/`이며, `Legacy/`의 원본 배포물과
`output/native-installer/`의 검증된 설치 파일은 덮어쓰지 않습니다.

현재 Windows EXE·설치 파일의 제작과 검증 계약은 [packaging/windows/README.md](../packaging/windows/README.md)에 있습니다. 현재 설치형 앱은 전용 런타임을 포함하고, 위 소스 실행 절차는 개발 PC의 Python·venv를 사용합니다. 이전 소스 ZIP·wheel은 [Legacy 안내](../Legacy/README.md)에 보관합니다.

현재 설치 파일의 시뮬레이터 검증은 실장비 구동 시험이 아닙니다. [현재 배포 검증 출처](../output/native-installer/README.md)는 실제로 시험한 소스와 설치 파일을 식별합니다.
