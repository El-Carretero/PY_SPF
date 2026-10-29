# PY-SPF 1.5.1 변경 및 검증 보고서

작성일: 2026-10-29 UTC. 기준: 배포된 1.5.0 소스 ZIP.
이번 작업은 실제 장비, RDC, 가상 XP에 접속하지 않고 수행했습니다.

## 변경 내용

### 화면 갱신과 Fault 유지

1.5.0은 큐의 각 이벤트마다 전체 화면을 갱신했습니다. 1.5.1은 한 주기에 최대 256개/8ms의
이벤트를 처리한 뒤 최신 상태로 한 번 갱신하고 로그도 한 번에 삽입합니다.
바뀌지 않은 변수·표시등·수치는 다시 쓰지 않습니다. 상태 문구와 측정값의 길이가 바뀌어도
주요 버튼의 위치와 크기가 바뀌지 않도록 레이아웃을 조정했습니다.

Fault 조회 실패/유효하지 않은 응답/통신 단절은 정상 초기값으로 처리하지 않습니다.
마지막 유효한 Fault 표시와 원시 응답을 보관하며, 현재 확인할 수 없으면 `*` / `[last/stale]`를 붙입니다.
마지막 값이 오류이면 빨강을 유지하고, 마지막 정상값이 오래되었으면 주황, 조회 이력이 없으면 회색입니다.
새 유효 응답으로 해제가 확인되면 오류 표시를 지웁니다. 연결을 새로 시작하면 이전 세션의 표시 캐시는 지웁니다.
이 캐시는 화면 표시용이며 RUN 조건에 필요한 최신 응답을 대체하지 않습니다.

전체 시험 중 TCU health의 별칭 응답(1029/1057)이 canonical 1088의 값·시각만 갱신하고
원시 문자열을 누락하여 화면 갱신이 중단되는 예외를 발견했습니다.
별칭 응답이 대표 ID의 원시값도 함께 갱신하도록 수정하고 해당 회귀 시험을 추가했습니다.

### RUN / STOP

- 버튼 문구를 정확히 `RUN`, `STOP`으로 변경했습니다.
- RUN 문자 입력 확인을 제거하고 마우스로 버튼을 3초 연속 누를 때 한 번만 실행합니다.
- 짧은 클릭, 중간 해제, 포인터 이탈, 포커스 상실, 탭 변경, 창 숨김, 연결/프로필 변경은 누르기를 취소합니다.
- 일반 버튼 invoke 및 Space/Enter로 길게 누르기를 건너뛰지 못합니다.
- GUI timer가 0.5초 넘게 지연되면 취소하며, 화면이 재개될 때 뒤늦게 RUN을 실행하지 않습니다.
- STOP은 누르는 시점에 실행하며 확인 창/3초 대기 없이 진행 중 RUN을 취소하고 OFF를 우선 요청합니다.
  현재 진행 중인 UDP 교환의 응답 대기와 장비 처리 시간은 남습니다. 물리적 정지 시간을 보증하지 않습니다.

External RUN의 PC2 ON 확인 → PC1 ON 확인, 중간 실패 시 두 PC OFF 정리,
최신 fault/HV/전압/소스/80 MHz/보호조건 검사 등 controller 동작은 1.5.0을 유지했습니다.
이 버전에서 RUN/STOP이 외부 펌프나 seed를 제어하도록 바꾸지 않았습니다.
Empower 모드도 메인 RUN의 3초 확인과 STOP 즉시 요청 UI를 사용합니다.

### TEC ON/OFF

두 버튼은 실제 명령 경로에 연결되어 있습니다. ON은 `2022 ECU:TECON`, OFF는 `2023 ECU:TECOFF`를
전송하며 `1028 ECU:STB?` 조회로 상태를 확인합니다. 기존 completion의 bit 0 판정을 그대로 사용합니다.
온도 화면에 현재 TEC reported ON/OFF/unknown과 마지막 요청 결과를 추가했습니다.
ACK는 적용 확인과 구분하고, 조회가 요청과 다르면 설정 불일치를 표시합니다.
TEC overtemperature 등 Fault는 별도 health/fault 표시로 유지합니다.

Verifier에서 ON/OFF 후 조회 일치와 ACK 후 상태 미변경 시 불일치를 확인했습니다.
실제 TEC 전원·냉각·온도 응답은 측정하지 않았습니다.

## 검증 결과

| 항목 | 결과 | 증거 |
| --- | --- | --- |
| 제품 전체 회귀 | 407 통과, 실패 0, 생략 0 | `verification/results/v1_5_1/linux_control` |
| Verifier 전체 회귀 | 209 통과, 실패 0, 생략 1 | `verification/results/v1_5_1/linux_verifier` |
| 이번 버전 신규 시험 | 23개, 제품 407개에 포함 | `tests/test_refresh_hold_151.py` |
| 기존 GUI RUN 시험 | 실제 3초 누르기를 통해 명령 전송까지 확인 | `tests/test_gui_output_150.py` 및 캡처 JSONL |
| 새 가상환경의 wheel 설치·External 데모 | PASS, 외부 I/O 차단 | `verification/results/v1_5_1/wheel_external_demo/result.json` |
| 1024×768 화면 | RUN/STOP 위치 안정 및 Fault 현재/오래된 상태 확인 | `verification/results/v1_5_1/screenshots` |
| Windows 10 / 실장비 / 실제 TEC 냉각 | 미실시 | Linux Python 3.12.14, Tk 8.6 가상 화면에서 검증 |

Verifier의 생략 1개는 배포하지 않은 vendor EXE의 선택적 해시 비교입니다.
시험 실행기는 loopback 외 소켓 송신을 차단합니다. 실제 Tk GUI, controller worker,
독립 UDP Verifier를 연결해 시험했으며, 과거 Windows/XP 결과를 이번 결과에 합산하지 않았습니다.
스크린샷의 UDP 표시도 loopback Verifier입니다. Fault 단절 화면은 통신 상태를 명시적으로 주입한 UI fixture입니다.

## 배포

런타임 의존성 추가 없음: Python 3.10 이상, Tk, pySerial 3.5.
소스와 wheel, pySerial wheel, 시험 코드·보고서·패킷 기록을 포함하며 EXE는 포함하지 않습니다.
기존 설정/로그는 보관하고 새 폴더에 압축을 푸십시오. 자동 데이터 CSV 저장은 기본 OFF를 유지합니다.
제품 변경 사항은 `verification/source_changes_1_5_0_to_1_5_1.patch`에 있습니다.
루트 `SHA256SUMS`는 배포 파일 무결성 확인용입니다.
