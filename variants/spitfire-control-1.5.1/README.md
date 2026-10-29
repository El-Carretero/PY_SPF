# Spitfire Python Control 1.5.1

Spitfire/Empower 원본 GUI의 통신을 구현한 Python 소스 배포본입니다.
이번 버전은 실제 장비/RDC에 접속하지 않고 Simulator와 loopback Twin Verifier로 검증했습니다.

## 1.5.1 변경

- 갱신 이벤트를 묶어 화면을 한 번 갱신하고, 바뀌지 않은 값은 다시 그리지 않습니다.
  값과 상태 문구의 길이가 바뀌어도 RUN/STOP 등 주요 버튼의 위치가 움직이지 않도록 조정했습니다.
- 통신 실패/잘못된 응답 때문에 Fault가 초기값으로 돌아가지 않습니다. 마지막 확인된 Fault를
  `*` / `[last/stale]`로 보존하며, 새 조회로 해제가 확인되어야 오류 표시를 지웁니다.
  오래된 정상값은 정상 녹색으로 표시하지 않으며, RUN 보호 검사에는 과거 표시값을 사용하지 않습니다.
- 메인 버튼은 **RUN / STOP**입니다. RUN은 버튼 위에서 마우스를 **3초 연속 누르면** 요청됩니다.
  문자 입력은 없으며, 짧은 클릭·중간 해제·포인터 이탈·포커스 상실·탭 변경은 실행하지 않습니다.
  GUI가 0.5초 넘게 멈추면 누르기를 취소하므로 재개 순간 RUN이 발생하지 않습니다.
- STOP은 누르는 즉시 진행 중 RUN을 취소하고 OFF를 우선 요청합니다. 확인 창이나 길게 누르기는 없습니다.
  진행 중인 통신 응답 대기와 장비 처리 시간까지 없애는 기능은 아닙니다.
- TEC ON/OFF의 기존 명령에 현재 상태와 명령 결과 표시를 추가했습니다.
  ON=`2022 ECU:TECON`, OFF=`2023 ECU:TECOFF`, 상태 확인=`1028 ECU:STB?`.
  ACK만 받았거나 조회 결과가 다르면 성공으로 표시하지 않습니다.
- TCU health 별칭 응답으로 갱신될 때 원시값이 누락되어 화면 갱신이 중단되는 예외를 수정했습니다.

## 유지되는 1.5.0 동작

- External 모드의 **RUN / STOP**은 PC1+PC2를 제어합니다.
  RUN은 PC2 ON 조회 확인 후 PC1 ON을 요청합니다. STOP은 PC1 OFF와 PC2 OFF를 모두 요청합니다.
  외부 펌프, seed, HV ON은 이 RUN/STOP에서 제어하지 않습니다. HV OFF는 별도 버튼입니다.
- RUN 중 오류·응답 유실·조회 불일치가 생기면 다음 ON을 취소하고 두 PC 채널에 OFF를 요청합니다.
  첫 OFF가 실패해도 두 번째 OFF를 시도합니다. 조회로 확인하지 못한 OFF를 완료로 표시하지 않습니다.
- `Device HV`, HV1/HV2 측정 전압, 현재 `Key interlock`, PC1/PC2 ON/OFF를 각각 표시합니다.
  `1021=1`은 장치의 HV 상태 보고이며, 물리적 Keyswitch 위치나 PC 출력 ON으로 해석하지 않습니다.
- 기존 `TDG / HV` 버튼은 `Open timing / HV settings`로 분리했습니다. 이 버튼은 설정 탭만 엽니다.
- 일반 polling을 꺼도 HV 상태·HV1/HV2 전압·Key interlock·PC1/PC2를 계속 조회합니다.
  값이 없거나 오래되면 `unknown/stale`로 표시합니다. 전류 추가 조회는 별도 선택입니다.
- Fault Reset 확인 창에 Keyswitch ON 상태에서 HV가 활성화될 수 있다는 설명을 추가했습니다.
  전후 HV·Key interlock·PC 상태를 시간/유효 여부와 함께 감사 로그에 남깁니다.
- 1.4.0의 전역 RESET 누락/차단 수정, 빈 응답 처리, EXT 소스 연속 설정, 단위 환산을 유지했습니다.
  Reset 순서는 `2044 → 2049 → 2052 → 2050`이며, 리셋 자체가 RUN을 실행하지 않습니다.

RUN은 최신 External 보호 조건, Device HV ON, 양수의 HV1/HV2 측정값, Key interlock clear,
두 PC 채널 OFF를 확인해야 시작합니다. 이 조건과 PC 조회 일치는 실제 광출력·광학 동기의 측정이 아닙니다.
원본에는 PC1/PC2 개별 버튼이 있으며, 이번의 묶음 RUN 순서는 새로 추가한 애플리케이션 동작입니다.

## Windows 실행

**소스 ZIP과 wheel이며 EXE는 포함하지 않았습니다.** Python 3.10 이상(Tk 포함)과 pySerial 3.5가 필요합니다.
이번 1.5.1 검증 환경은 Linux Python 3.12.14 + Tk 가상 화면입니다. Windows 10/실장비 검증은 수행하지 않았습니다.

1. ZIP 전체를 새 폴더에 풉니다. 기존 버전과 설정/기록은 보관합니다.
2. Python 설치 후 `install_windows.cmd`를 실행합니다. pySerial은 포함된 wheel로 설치합니다.
3. 장치 없이 확인하려면 `start_external_demo.cmd`를 실행합니다.
4. 장비를 연결할 때만 `start_external_pump.cmd` 또는 `start_empower.cmd`를 사용합니다.

```powershell
.\.venv\Scripts\python.exe run_spitfire.py --simulator --pump-mode external
```

기본 장비 주소는 `10.19.70.13:1024`, 로컬 포트는 `1024`입니다. 기존 설정은 자동 변경하지 않습니다.
동일 PC에서 원본 GUI와 Python이 같은 수신 포트를 동시에 사용하지 않도록 구성하십시오.
자동 데이터 CSV 저장은 기존처럼 기본 OFF입니다. 명령 감사 로그는 별도로 자동 기록합니다.

## 재현 가능한 검증

```powershell
.\.venv\Scripts\python.exe verification\run_tests.py --output verification\my_control_run
.\.venv\Scripts\python.exe verification\run_tests.py --suite verifier --output verification\my_verifier_run
.\.venv\Scripts\python.exe run_spitfire.py --pump-mode external --self-test-report verification\demo_result.json
```

시험 실행기는 loopback 외 소켓 송신을 차단하고 사용자 설정을 임시 폴더에 격리합니다.
GUI 시험에는 화면이 필요합니다. 1.5.1 결과와 패킷 기록은 `verification/results/v1_5_1`에 있습니다.
그 외 기존 결과 폴더는 이전 버전 기록입니다. Twin Verifier는 통신 모델이며 실제 레이저 물리를 재현하지 않습니다.

- [1.5.1 변경·검증 보고서](docs/VALIDATION_1_5_1_KO.md)
- [1.5.0 변경·검증 보고서](docs/VALIDATION_1_5_0_KO.md)
- [외부 펌프 사용 안내](docs/EXTERNAL_PUMP_KO.md)
- [프로토콜 및 단위](docs/PROTOCOL.md)
- [1.4.0 보고서](docs/VALIDATION_1_4_0_KO.md)

과거 버전 보고서는 당시의 기록입니다. 현재 동작은 이 README와 1.5.1 보고서를 기준으로 합니다.
