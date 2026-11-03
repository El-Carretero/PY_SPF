# Spitfire Python Control 1.3.0

Spitfire Pro의 기존 TDG와 seed oscillator를 유지하면서, Empower 또는 별도로 제어하는
외부 펌프를 선택하는 프로그램입니다. 외부 펌프 DM1-527-20의 발진·출력은 전용 프로그램에서
관리하며, 이 프로그램은 DM1을 제어하거나 실제 광펄스의 동기화를 측정하지 않습니다.

1.3.0은 XP 원본 EXE/UIR를 다시 대조해 **오류 데이터 출처와 16진수 해석을 정정**하고,
**외부 타이밍 프로파일과 출력 활성화 전 readback 확인**을 추가했습니다.

> **1.2.0 설명 정정:** `EMP:FAULT?`(1014)를 TDG·TCU까지 포함하는 공유 오류로 설명한 것은
> 잘못된 UIR 번호 해석 때문이었습니다. 1.3.0은 1014를 Empower 전용으로 취급하며,
> 외부 모드에서는 조회하지 않습니다. TDG·TCU·통신·BWD 상태는 각 전용 명령에서 읽습니다.
> [XP 대조 검토 보고서](docs/XP_PARITY_REVIEW_1_3_0.md)에 근거와 구현 범위를 기록했습니다.

## 바로 실행

Windows 배포본의 `dist/SpitfirePythonControl.exe`는 **Python 설치 없이** 실행합니다.
이 EXE는 XP용 빌드가 아니며, XP에서 실행 검증하지 않았습니다.
ZIP 전체를 새 폴더에 해제하고, 먼저 `start_external_demo.cmd`를 실행하십시오.
세 시작 스크립트는 EXE를 우선 사용하고 EXE가 없으면 Python 소스로 실행합니다.

| 파일 | 용도 |
| --- | --- |
| `start_external_demo.cmd` | 장치에 접속하지 않는 외부 펌프 시뮬레이터 |
| `start_external_pump.cmd` | 실제 TDG에 UDP로 연결하는 외부 모드 |
| `start_empower.cmd` | 실제 TDG에 UDP로 연결하는 기존 Empower 모드 |
| `install_windows.cmd` | 소스 실행에 필요한 `.venv`와 포함된 pySerial wheel 설치 |
| `run_tests.cmd` | Python 소스의 오프라인 검증 |

EXE를 직접 실행할 수도 있습니다.

```powershell
.\dist\SpitfirePythonControl.exe --simulator --pump-mode external
```

소스 실행에는 Python 3.10 이상과 Tk가 필요합니다. `install_windows.cmd` 실행 후:

```powershell
.\.venv\Scripts\python.exe run_spitfire.py --simulator --pump-mode external
```

데모는 Empower가 없는 합성 장치를 사용합니다. 실제 TTL, 광펄스나 레이저 출력을 만들지 않습니다.

## 외부 모드 설정

`File > Connection Settings`의 `Transport`는 `simulator` 또는 `udp`,
`Pump configuration`은 `empower` 또는 `external`입니다. 두 설정은 독립적입니다.
실제 연결 스크립트는 UDP를 명시적으로 선택합니다. 기본 주소는 remote `10.19.70.13:1024`,
local `0.0.0.0:1024`이며 저장된 설정을 확인하십시오. 같은 포트를 사용하는 원본 GUI와
동시에 연결하지 마십시오. `--simulator`와 `--udp`를 함께 지정하면 오류로 종료합니다.

`File > External timing...`에서 다음 기준을 설정합니다.

| 항목 | 초기값 | 의미 |
| --- | --- | --- |
| Expected seed | 80 MHz | 실제 seed readback과 비교할 소프트웨어 기준 |
| Allowed seed deviation | ±1 MHz | 허용 편차. 실제 장비 요구에 맞춰 수정 |
| Expected pump rate | 10 Hz | 참고값이며 펌프 설정·측정·동기 확인값이 아님 |

`SAVE & RECONNECT`는 기준을 저장하고 DISARM 상태로 재연결합니다.
타이밍이나 opt-out을 자동으로 쓰지 않습니다. 실제 설정은 최근 HV OFF를 확인하고 ARM한 뒤
`APPLY EXT SOURCES`와 `APPLY EMPOWER OPT-OUT`을 각각 명시적으로 실행합니다.
두 EXT source의 readback, 측정 seed 주파수, opt-out 및 보호 상태를 확인해야
HV ON·채널 ON 등의 출력 활성화 명령이 허용됩니다. 설정 ACK만으로 성공을 판단하지 않습니다.

**10 Hz는 동작 검증 결과가 아닙니다.** 현재 복원된 명령에는 외부 펌프의 실제 반복률을
검증한 readback이나 광학 위상 잠금 판정이 없습니다. 타이밍 설정과 배선 확인 순서는
[외부 펌프 모드 안내](docs/EXTERNAL_PUMP_KO.md)에 있습니다.

## 외부 모드 동작

- Empower 전용 조회·제어·서비스 명령을 제외하고, TDG·TCU·헤드의 실제 응답을 유지합니다.
- Automatic polling을 꺼도 별도의 18개 필수 조회로 opt-out, HV, 보호 및 타이밍 상태를 확인합니다.
- TDG fault override, TCU·head opt-out, humidity override가 모두 0이고,
  TDG·TCU·head 통신과 PC1/PC2 복합 readback의 BWD·ENA가 확인돼야 합니다.
  미지원 응답·timeout·오래된 값은 출력 활성화 조건을 충족하지 못합니다.
- 타이밍 source·분주·내부 반복률 변경, oscillator 기준 갱신, opt-out, latch reset은 최근 HV OFF를 요구합니다.
- `TDG / HV`는 제어 탭으로 이동합니다. `HV OFF`는 TDG HV OFF를 요청하고 DISARM합니다.
  **DM1과 seed를 정지시키지 않습니다.**
- Programmer에도 동일한 정책을 적용합니다. 전역 ON/OFF/reset, 임의 명령 통과,
  전역 BWD 쓰기 및 보호 우회 활성화를 차단합니다. 외부 모드에서 Raw RS-232는 사용할 수 없습니다.
- 연결·프로파일 변경·재연결 시 출력이나 ARM을 자동 복원하지 않습니다.

## 기존 Empower 모드

전류·Q-switch·LBO, RUN/STOP, TDG/HV, TCU, compressor motor, 오류 표시,
Programmer와 별도 RS-232 서비스 화면을 유지합니다.

```powershell
.\dist\SpitfirePythonControl.exe --simulator --pump-mode empower
```

일반 GUI의 Q-switch 주파수는 Hz이며 Programmer는 raw wire 단위입니다.
GUI의 1,000 Hz는 wire argument `100.00`입니다. 입력값과 readback은 분리됩니다.
STOP/OFF는 대기 중 쓰기를 취소하고 우선 처리하지만 이미 송신한 바이트를 되돌리지 못합니다.
ARM은 쓰기 권한이며 DISARM 자체는 출력 차단 명령이 아닙니다.

## 패키지와 검증

소스 폴더의 `run_spitfire.py`는 패키지를 별도로 설치하지 않고 실행합니다.
wheel 설치가 필요하면 포함된 vendor wheel과 함께 사용합니다.

```powershell
py -m pip install --no-index --find-links release\vendor release\spitfire_control-1.3.0-py3-none-any.whl
spitfire-control --simulator --pump-mode external
```

소스 검증은 `py validate_spitfire.py offline`, EXE 재빌드는 `.\build_windows.ps1`입니다.
오프라인 검증은 실제 COM과 외부 네트워크 접근을 차단하며 UDP 시험은 loopback만 사용합니다.
명령 제공이나 시뮬레이터 성공이 실제 TDG 통신·opt-out·10 Hz 운전 성공을 뜻하지 않습니다.
현재 릴리스의 실행 결과는 별도 `docs/VALIDATION_1_3_0.md`를 기준으로 하며,
이전 `VALIDATION_1_2_0.md`의 시험 수를 1.3.0 결과로 해석하지 않습니다.

## 구조와 자료

| 파일 | 역할 |
| --- | --- |
| `src/spitfire_control/commands.py`, `protocol.py` | 복원한 명령 목록과 ECLIPSE framing |
| `transport.py` | UDP 및 외부 펌프 시나리오를 포함한 합성 장치 |
| `controller.py`, `profiles.py` | 스케줄러, 송신 직전 권한·상태 검증, 구성별 명령 정책 |
| `state.py`, `timing.py` | 원시 응답, 유효기간, 오류 출처, 타이밍 기준 |
| `ui.py`, `config.py` | 화면, 외부 타이밍 설정, 검증된 설정 저장 |
| `serial_service.py` | UDP와 독립된 서비스용 serial 세션 |

- [1.3.0 변경 사항](docs/CHANGELOG_1_3_0.md)
- [XP 원본 대조와 구현 범위](docs/XP_PARITY_REVIEW_1_3_0.md)
- [외부 펌프 모드 안내](docs/EXTERNAL_PUMP_KO.md)
- [통신 프로토콜](docs/PROTOCOL.md), [기존 실기 검증 절차](docs/COMMISSIONING.md), [자동 검증 안내](docs/AUTOMATED_VALIDATION.md)
- 이전 기록: [1.2.0](docs/CHANGELOG_1_2_0.md), [1.1.3](docs/CHANGELOG_1_1_3.md), [1.1.2](docs/CHANGELOG_1_1_2.md), [1.1.1](docs/CHANGELOG_1_1_1.md)

이전 기록의 오류 매핑 설명은 위 1.3.0 정정과 대조하십시오.
원본 NI runtime은 필요하지 않으며 원본 실행 파일은 포함하지 않습니다.
복원한 명령은 제조사 firmware 명세가 아니며, 소프트웨어는 물리적 인터록을 대체하지 않습니다.
