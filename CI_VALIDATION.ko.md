# External Control 2.0.0 자동 검증

기존 [2026-10-30 검증 기록](VALIDATION_EXTERNAL.ko.md)은 당시의 Linux 수동 실행 결과로 보존한다.
새 워크플로는 [.github/workflows/external-validation.yml](.github/workflows/external-validation.yml)에 있다.
프로그램 버전과 실제 장비 제어 코드는 변경하지 않았다.

## 자동 실행 범위

| Job | 환경 | 실행 내용 | 실행하지 않는 내용 |
|---|---|---|---|
| portable / Windows | windows-2022, Python 3.12 x64, PySide6 6.12.0 | 전체 pytest, 실제 Qt 입력·회귀 시험, 헤드리스 시뮬레이터 데모, Qt offscreen 8개 패널 렌더 | 실제 장비, Native NI GUI |
| portable / Linux | ubuntu-24.04, Python 3.12 x64, PySide6 6.12.0 | Windows와 동일한 전체 시험·데모·렌더 | 실제 장비, Native NI GUI |
| native-boundary | windows-2022, Python 3.12 **x86**, Qt 미설치 | Native 어댑터 mock 경계, 지원 OS/비트수 오류, DLL 없는 리소스 처리, UDP 프로토콜·통신 제한 시험, 헤드리스 시뮬레이터 | NI DLL 초기화, 원본 UIR 화면 표시, NI GUI 조작 |

pytest 9.2.0과 PySide6 6.12.0은 `requirements-ci.txt`로 고정한다. Python 3.12의 세부 패치 버전은
setup-python이 해당 OS/아키텍처에 제공하는 버전이며, 실제 값은 결과의 `environment.json`에 남긴다.
Native job은 `.[test]`만 설치한다. PySide6 Windows x86 wheel을 요구하지 않는다.
저장소에 NI DLL이 포함되어 있어도 CI에서는 해당 DLL 로드를 거부하므로, 이 job의 통과를 Native GUI 검증으로 해석하면 안 된다.

Linux runner에는 Qt offscreen에서도 필요한 `libegl1`, `libgl1`, `libopengl0`를 명시적으로 설치한다.
기존 CSV 시험은 Windows CRLF와 Linux LF를 텍스트 읽기로 정규화한 뒤 동일한 숫자·구분자·헤더 부재를 확인한다.
CSV를 쓰는 프로그램 동작은 그대로 유지한다.

`main`, `feature/empower-independent`, `ci/**` 브랜치의 push와 main/External 브랜치를 대상으로 하는 PR에서
실행한다. `workflow_dispatch`도 정의되어 있다. 수동 실행 버튼은 워크플로가 기본 브랜치에 있어야 표시되므로,
현재처럼 feature 브랜치에만 있을 때는 해당 브랜치 push로 실행한다. `pull_request_target`과 secrets는 사용하지 않으며
토큰 권한은 `contents: read`로 제한한다. 두 OS 중 하나가 실패해도 다른 job은 계속 실행한다.

## 장비 통신 제한

모든 pytest에는 `tests/conftest.py`에서 통신 가드를 적용한다. CI 데모는 `tools/ci_exec.py`를 거쳐
동일한 가드를 적용한 뒤 시작하며, 반드시 `--demo --host 127.0.0.1 --local-port 0 --tcp-port 0`을 사용한다.
헤드리스 출력에서 `mode=simulator`, 연결 성공, 컨트롤 갱신을 검사한다. 종료 코드 0만으로 통과시키지 않는다.

Python socket의 connect/sendto/DNS 경로에서 localhost와 loopback IP만 허용한다. 레거시 UDP transport의
`0.0.0.0` bind는 시험 프로세스 안에서만 `127.0.0.1`로 좁힌다. Python audit hook은 직접 `_socket`으로 수행하는
IP 연결/송신도 차단한다. 실제 장비 기본 주소 `10.19.70.13`, 사설 주소, broadcast, 외부 DNS, IPv6 원격 주소,
직접 wildcard bind가 거부되는지 회귀 시험에 포함한다. 통과한 기존 UDP/TCP 시험은 실제 loopback socket을 사용한다.
이 가드는 Python 시험·데모 범위의 제한이며 임의의 네이티브 코드에 대한 OS 방화벽은 아니다.

## 결과 확인

[Actions 실행 목록](https://github.com/El-Carretero/PY_SPF/actions)에서 각 OS/아키텍처 job을 구분해 확인한다.
각 job의 Step summary와 별도 artifact에 다음을 보존한다(30일 보관).

- `environment.json`: OS, Python 버전/비트수, 설치 패키지, Qt 버전, GitHub commit/ref/run 식별자, 미검증 범위
- `pytest.xml`, `pytest.stdout.txt`, `pytest.stderr.txt`: JUnit과 원문 시험 결과; 세부 subtest 수도 원문 로그에서 확인
- `headless-demo.stdout.txt`: 시뮬레이터 연결·상태 갱신 JSON
- `qt-panels/`: x64 Qt 렌더 결과 8장
- `results.json`, `summary.md`, 실패 시 `*.error.txt`: 단계별 통과/실패와 근거

artifact 이름은 `external-Windows-py3.12-x64-*`, `external-Linux-py3.12-x64-*`,
`external-Windows-py3.12-x86-native-boundary-*`로 분리된다. pytest 실패 시에도 데모·렌더를 시도하고
근거를 업로드한다. Qt가 누락되거나 시험이 조용히 skip되면 portable 검증은 실패한다.
Python/의존성 설치 자체가 실패하면 이후 단계는 실행되지 않을 수 있으므로 해당 Actions 단계 로그를 확인한다.

## 로컬 재현

Windows PowerShell 또는 Linux 셸에서 저장소 루트의 전용 가상환경을 활성화한 후:

```sh
python -m pip install -c requirements-ci.txt ".[qt,test]"
python -m pip check
python tools/ci_validate.py --profile portable --output artifacts/local-portable
```

이 스크립트가 `QT_QPA_PLATFORM=offscreen`과 UTF-8 환경을 자식 프로세스에 설정한다.
데모는 임시 디렉터리에서 실행해 설치된 패키지를 사용하며, `config.sp`와 로그도 임시 경로를 사용한다.

별도의 **Windows 32비트 Python 가상환경**에서는:

```sh
python -m pip install -c requirements-ci.txt ".[test]"
python tools/ci_validate.py --profile native-boundary --output artifacts/local-native-x86
```

2026-10-31 개발 환경의 Linux Python 3.12.14에서 전체 **152개 + 71개 subtest**, 헤드리스 데모 및
Qt 8개 패널 렌더를 확인했다. 이것은 로컬 실행 기록이며 GitHub-hosted Windows/Linux 실행 결과와 구분한다.
GitHub 실행 상태는 위 Actions의 해당 커밋 실행 결과가 기준이다.

실제 07 PC의 디스플레이·드라이버·장비 연결, Native NI GUI 표시 및 입력, 광출력과 타이밍은
이 자동 검증의 통과 여부와 관계없이 별도 검증 대상이다.
