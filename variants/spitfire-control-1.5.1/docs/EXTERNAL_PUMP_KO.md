# External Pump 사용 안내 — 1.5.1

외부 펌프와 seed는 해당 전용 제어기로 관리합니다. PY-SPF는 TDG 상태와 PC 채널을 제어하며,
외부 펌프의 실제 발진·출력·반복률·광학 동기 상태를 측정하지 않습니다.

## 화면과 명령의 구분

| 표시/버튼 | 의미 |
| --- | --- |
| Device HV | 1021 `TDG:HV:ON?`의 최신 응답. Keyswitch 위치나 PC ON 상태가 아님 |
| HV1 / HV2 | 1042/1043 실제 측정 응답. wire kV를 화면 V로 변환 |
| Key interlock | 1039 현재 상태의 `0x4000` 비트: asserted/clear/unknown. 기계적 스위치 위치 센서로 단정하지 않음 |
| FAULTS의 TDG Key fault | 1066 fault register의 `0x4000`. 현재 interlock과 별도 |
| PC1 / PC2 | 1045/1046 복합 응답에서 읽은 채널 ON/OFF. 수신 확인만으로 바꾸지 않음 |
| RUN | 3초 연속 누르기 → PC2 ON → PC2 조회 확인 → PC1 ON → PC1 조회 확인 |
| STOP | 누르는 즉시 PC1 OFF → PC2 OFF 우선 요청 후 각각 조회. HV·펌프·seed는 유지 |
| HV OFF | 별도 2016 명령. 진행 중 RUN을 취소하고 PC OFF 정리를 요청 |
| Open timing / HV settings | 설정 탭 열기. 장치 명령 없음 |
| CLEAR FAULTS | EMP reset → TCU reset → TDG reset → 전역 RESET. 자동 RUN 없음 |

ON/STOP 확인은 PC 채널의 보고값에 대한 확인입니다. 실제 광출력 유무를 보증하지 않습니다.
화면의 `Last RUN/STOP`은 마지막 명령 결과입니다. 현재 상태는 위의 PC1/PC2 최신값으로 확인합니다.

RUN은 문자 입력 대신 버튼 위에서 마우스를 3초 연속 누릅니다. 도중에 놓거나 버튼을 벗어나거나
포커스/탭을 바꾸면 취소됩니다. GUI가 0.5초 이상 멈추어도 취소되며, 다시 눌러야 합니다.
STOP은 누르는 순간 우선 OFF를 요청하지만 진행 중인 UDP 응답 대기/장비 처리 시간은 남습니다.

Fault 조회가 끊기면 마지막 확인값을 `*` / `[last/stale]`로 표시합니다. 과거 오류는 빨강,
오래된 정상값은 주황, 조회 이력이 없는 값은 회색입니다. 새 응답의 오류 해제 확인으로만 빨강을 지웁니다.
이 보존은 표시용이며 최신 데이터가 없는 상태에서 RUN을 허용하지 않습니다.

## 소프트웨어 RUN 조건

기존 External 조건을 유지합니다: 최신 통신, Empower opt-out=1, OSC/TRIG=EXT,
유효한 seed 측정값(기본 80 MHz ±1 MHz), TDG·TCU·head 통신 정상,
보호 우회=0, PC1/PC2의 BWD와 ENA 활성, 확인된 fault와 통신 오류 없음.

묶음 RUN에는 Device HV ON, 최신 양수 HV1/HV2 측정값, 현재 Key interlock clear,
두 PC 채널 OFF가 추가로 필요합니다. 값이 없거나 오래되면 RUN을 보류합니다.
설정 명령이나 Reset이 진행 중일 때도 완료 후 RUN을 요청해야 합니다.
부분 ON 상태에서는 먼저 STOP으로 두 채널 OFF를 확인합니다.

RUN은 HV를 자동으로 켜거나 Fault Reset을 실행하지 않습니다.
RUN 중에는 상태 조회와 OFF를 허용하며 다른 설정 쓰기는 차단합니다.
채널별 ON 확인에 실패하면 남은 ON을 취소하고 두 채널에 OFF를 요청합니다.
OFF 중 한 채널이 실패해도 다른 채널의 OFF 요청은 계속합니다.
OFF 확인 실패는 `unverified`로 남기며 통신 복구 후 ON을 재시도하지 않습니다.

## 조회와 기록

일반 Automatic polling을 꺼도 External 필수 18개와 HV1/HV2 측정 2개를 순환합니다.
Device HV, Key interlock, PC1/PC2는 기존 18개에 포함됩니다. 연결 heartbeat는 별도입니다.
명목 간격은 2초/20이며 응답 대기 시간이 더해집니다. 실시간 보호회로를 대체하지 않습니다.
다른 모드에서도 HV·전압·Key interlock·PC1/PC2 기본 조회 6개는 계속됩니다.
`Extra HV current monitoring`은 전류 추가 조회를 선택하며 기본 OFF입니다.

Reset 후 0.5 / 1.5 / 3.5 / 6초에 fault·HV·PC를 재조회합니다.
Reset 완료는 모든 fault 해제 판정이 아닙니다. Keyswitch가 ON이면 리셋 후 HV가 활성화될 수 있습니다.
`RESET_BEFORE`/`RESET_AFTER` 감사 기록에는 원시 응답, 갱신 시각, freshness가 함께 저장됩니다.
Before는 요청 당시의 캐시이며 새로 측정한 값이라는 주장을 하지 않습니다.

기본 데이터 CSV 저장은 OFF입니다. 명령 감사 CSV는 자동 기록하며, 기록 경로 문제로 OFF 전송을 막지 않습니다.

## 장치 없는 확인

Python 3.10 이상과 Tk 설치 후 `install_windows.cmd`, `start_external_demo.cmd`를 사용합니다.
EXE는 이 배포본에 없습니다. 데모에서 opt-out과 EXT 소스를 명시적으로 설정하고
HV ON을 요청한 뒤 RUN/STOP을 확인할 수 있습니다. 모두 합성 상태이며 실제 장치에 연결하지 않습니다.

실장비에서는 전용 장비 절차와 광학 측정으로 확인해야 합니다. 이번 버전에서 PC1/PC2 실제 전기 출력,
80 MHz 잠금, 광펄스 및 HV 방전 시간은 시험하지 않았습니다. 연결 해제나 앱 종료는 STOP 명령이 아닙니다.
원본의 개별 PC 버튼과 새 묶음 RUN의 순서가 동일하다고 주장하지 않습니다.
