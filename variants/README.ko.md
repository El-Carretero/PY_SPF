# 구현별 위치와 실행

| 구분 | 위치 | 목적 |
|---|---|---|
| 기존 PY_SPF | 저장소 루트의 `spitfire/` | Spitfire GUI 1.6.0의 원본 동작·화면 재구현. 패키지 버전 `1.6.0.post1` |
| 첨부 코드 | [`spitfire-control-1.5.1/`](spitfire-control-1.5.1/) | 별도 Tk GUI, Empower/External 프로필, 조회 확인 및 외부 펌프 운용 기능. 패키지 버전 `1.5.1` |

두 버전 번호는 서로 다른 프로젝트의 번호이며, 숫자만으로 신·구 관계를 판단할 수 없습니다.
첨부본 470개 파일은 ZIP에서 최상위 폴더 이름만 바꿔 바이트 그대로 보존했습니다.
소스, 문서, 과거 시험 기록, wheel 및 라이선스를 포함합니다.
비교 내용과 이번 검증 결과는 [`comparisons/spitfire-control-1.5.1/`](../comparisons/spitfire-control-1.5.1/README.ko.md)에 있습니다.

## 기존 재구현 데모

저장소 루트에서 기존 환경으로 실행합니다.

```sh
python -m pip install ".[qt]"
python -m spitfire --backend qt --demo --tcp-port 0
```

32비트 Windows Python의 NI 백엔드는 루트 [실행 안내](../README.ko.md)를 따릅니다.

## 첨부본 External 데모

Python 3.10 이상과 Tk가 필요합니다. 두 구현을 구분하기 위해 첨부본 디렉터리에서 별도 가상환경을 만듭니다.

Windows:

```bat
cd variants\spitfire-control-1.5.1
install_windows.cmd
start_external_demo.cmd
```

Linux/macOS (Tk가 설치된 Python):

```sh
cd variants/spitfire-control-1.5.1
python3 -m venv .venv
.venv/bin/python -m pip install --no-index --find-links release/vendor release/spitfire_control-1.5.1-py3-none-any.whl
.venv/bin/python run_spitfire.py --simulator --pump-mode external
```

새 설정의 기본값은 `simulator` + `empower`입니다. 저장된 설정도 사용하므로,
장치 없는 External 데모에는 **`--simulator --pump-mode external` 두 옵션을 함께 명시**합니다.
Windows의 `start_external_pump.cmd`는 `--udp --pump-mode external`로 장치 연결을 선택합니다.
해당 모드의 RUN/STOP은 PC1·PC2 제어이며 외부 펌프 자체나 seed, HV ON을 제어하지 않습니다.

두 프로그램의 기본 장치 주소·수신 포트는 같으므로 실제 연결 시 동시에 같은 로컬 UDP 포트를 사용하지 않습니다.
기존 `config.sp`와 첨부본 `spitfire-control/config.json`은 별도 형식이며 설정 자동 변환은 없습니다.

## 보존 범위

첨부본의 코드와 기본값은 수정하지 않았습니다. `Empower`/`SERVICE` 탭과 Empower 코드도 그대로 존재합니다.
External 모드는 해당 탭을 비활성화하고 명령 정책을 적용합니다. 이 저장 작업은 첨부본의
기능을 기존 재구현에 이식하거나 두 프로그램을 통합하는 변경을 포함하지 않습니다.
첨부본 내부 문서와 검증 결과는 제공된 자료로 보존했으며 이번 작업의 실행 지시로 취급하지 않았습니다.
