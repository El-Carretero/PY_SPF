# PY-SPF 1.5.0 변경 및 검증 보고서

작성일: 2026-10-29 UTC. 기준 소스: Spitfire Python Control 1.4.0.
이번 작업에서 RDC/P04/실제 장비/가상 XP에 접속하지 않았습니다.

## 결과

| 시험 | 결과 | 환경/증거 |
| --- | --- | --- |
| 제품 전체 회귀 | **384 통과, 실패 0, 생략 0** | Python 3.12.14, Linux, Tk 8.6 가상 화면; `verification/results/v1_5_0/linux_control` |
| 독립 Twin Verifier 회귀 | **209 통과, 실패 0, 생략 1** | `verification/results/v1_5_0/linux_verifier` |
| 새 1.5.0 회귀 | **34개**, 위 제품 시험에 포함 | PC transaction 26개 + 실제 Tk/worker/UDP 8개 |
| 별도 가상환경의 wheel 설치·External 데모 | **PASS** | `verification/results/v1_5_0/wheel_external_demo/result.json` |
| 작은 화면 | **1024×768 확인** | 버튼 경계 및 실제 높이 검사, `screenshots`의 4개 화면 |
| Windows 10 / 실제 출력 | **미실시** | EXE 미포함, 소스와 wheel 배포 |

Verifier의 생략 1개는 재배포하지 않은 원본 vendor EXE의 선택적 해시 대조입니다.
이번 버전의 시험은 실제 명령 인코딩·UDP 송수신·상태 판정·Tk 조작까지 포함하지만,
HV 전기 출력, PC1/PC2 전기 신호, seed 80 MHz 잠금, 광학 동기, 레이저 출력은 확인하지 않았습니다.
이전 Windows/XP 결과 폴더는 1.4.0 이하의 기록이며 1.5.0 검증으로 계산하지 않았습니다.

## 화면과 의미 수정

- `TDG / HV`를 `Open timing / HV settings`로 명확히 분리했습니다. 이 버튼은 탭만 엽니다.
- External 메인 화면에 `RUN PC1+PC2`, `STOP PC1+PC2`, 별도 `HV OFF`를 배치했습니다.
- `Device HV`는 1021의 HV 보고값, `Key interlock`은 1039의 현재 비트입니다.
  1066의 Key fault는 별도로 유지합니다. 기계적 Keyswitch 위치로 이름을 바꾸지 않았습니다.
- HV1/HV2 측정 전압과 PC1/PC2 스위치 상태를 따로 표시합니다.
  데이터가 없거나 오래되면 `unknown/stale`로 남깁니다.
- 마지막 명령 결과와 현재 PC 상태를 분리했습니다. 예전 RUN 성공 이력이 있어도
  현재 응답이 오래되면 PC1/PC2는 unknown/stale로 표시합니다.
- 화면에서 긴 명령 상세가 다른 버튼을 밀어내지 않도록 결과는 짧게 표시하고 상세는 로그에 남깁니다.

## RUN/STOP의 실제 구현

| 동작 | 명령/확인 | 실패 처리 |
| --- | --- | --- |
| External RUN 1단계 | 2019 `2 ON` → 1046에서 ON 확인 | 다음 ON 취소, 두 채널 OFF 요청 |
| External RUN 2단계 | 2019 `1 ON` → 1045에서 ON 확인 | 두 채널 OFF 요청 |
| External STOP | 2019 `1 OFF`, `2 OFF`를 urgent queue에 제출 | 첫 오류 이후에도 다른 OFF 전송 |
| STOP 완료 | 두 결과가 confirmed이고 두 채널의 최신 조회가 OFF | 미확인은 unverified, 완료로 꾸미지 않음 |

CH2 추출 채널을 먼저 준비하고 CH1 주입 채널을 뒤에 켜는 묶음 순서는 이번 앱에서 정한 순서입니다.
원본의 개별 PC1/PC2 버튼에서 묶음 RUN 순서를 복원했다고 주장하지 않습니다.
채널 대응은 사용자 제공 `330A, Rev. A, Spitfire Pro User's Manual`의 인쇄 6-9쪽,
HV keyswitch/표시 구분은 4-3쪽, 시작 절차의 HV와 PC 버튼 분리는 6-1~6-2쪽을 참고했습니다.
해당 설명과 과거 분석 자료만으로 실제 전기 출력의 순서/안전성이 검증되는 것은 아닙니다.

RUN 시작에는 기존 External 보호 검사에 더해 Device HV ON, 신선한 양수 HV1/HV2,
현재 Key interlock clear, PC1/PC2 OFF, 다른 쓰기 완료가 필요합니다.
각 ON의 실제 전송 직전과 최종 확인 시점에도 조건을 재검사합니다.
진행 중 다른 설정 쓰기/중복 RUN은 차단하며 OFF는 허용합니다.

ACK 또는 일치하는 빈 응답은 적용 증거가 아닙니다. 해당 채널 조회가 맞아야 다음 단계로 갑니다.
명령/응답 유실, NACK, 빈/잘못된 조회, 조회 불일치, 조건 변경, 확인 기한 초과는 RUN을 중단합니다.
정리 OFF도 통신 실패할 수 있으므로 실패 시 OFF를 보장하지 않고 결과를 미확인으로 남깁니다.
연결 해제/앱 종료는 STOP을 대신하지 않으며 출력이 꺼졌다고 표시하지 않습니다.
재연결이나 정상 상태 회복만으로 RUN/ON을 재전송하지 않습니다.

External RUN/STOP에서 HV ON, 펌프 RUN/STOP, seed 명령을 보내지 않는 것을 패킷으로 확인했습니다.
Empower 모드의 기존 RUN/STOP 경로는 유지했습니다.

## Reset 및 기본 조회

Clear Faults는 1.4.0의 `2044 → 2049 → 2052 → 2050` 순서를 유지합니다.
HV OFF를 리셋 선행 조건으로 추가하거나 자동 HV/PC 쓰기를 삽입하지 않았습니다.
확인 창은 Keyswitch ON 상태의 리셋 이후 HV가 활성화될 수 있음을 설명합니다.

전역 RESET 후 fault 조회에 더해 HV, 측정 전압, Key interlock, PC 채널을 재조회합니다.
0.5 / 1.5 / 3.5 / 6초 지연 조회는 일반 polling과 독립입니다.
`RESET_BEFORE`/`RESET_AFTER` 감사 기록에는 원시값·갱신 시각·유효 여부가 포함됩니다.
Before는 명령 요청 시점의 캐시이며 측정을 새로 수행했다고 표현하지 않습니다.
After의 observed는 조회 완료를 뜻하고 fault 해제를 보장하지 않습니다.

일반 polling OFF에서도 기본 출력 상태 6개(1021,1042,1043,1039,1045,1046)를 계속 읽습니다.
External에서는 기존 보호용 18개와 합쳐 총 20개를 순환합니다. 전류 추가 조회는 기존 선택을 유지합니다.
기본 데이터 CSV 저장은 OFF, 명령 감사 CSV는 자동이라는 기존 정책은 변경하지 않았습니다.

## 재현한 실패와 경계 조건

26개 PC transaction 시험은 독립 Verifier와 실제 loopback UDP를 사용합니다.

- 첫 채널 접수만 되고 적용되지 않는 경우: 둘째 ON 차단, 두 채널 OFF 조회 확인.
- 두 번째 ON의 NACK: 이미 켠 첫 채널까지 OFF 정리.
- ON 요청 유실 / 적용 후 응답 유실: ON 재시도 없이 OFF 정리.
- 첫 STOP의 NACK / 응답 유실: 두 번째 OFF도 전송, 전체 STOP은 미확인 유지.
- 연결/HV/fault가 불명인 경우도 STOP 요청 허용.
- RUN 직후 STOP, 단계 사이 STOP, 반복 STOP, HV OFF에 의한 RUN 취소.
- 오래된 전압, 음수/0 전압, Key interlock, fault, 주파수/소스 불일치, 부분 ON 상태의 RUN 차단.
- 전송 직전 HV 변경, 마지막 확인 전 fault 발생, 확인 기한 만료, 연결 종료.
- Key/reset/HV 전환을 명시적으로 주입한 시나리오에서 PC 자동 ON 없음.
- 실제 Tk 버튼 클릭, 확인 취소, 상태 분리, 자동 polling OFF 상태의 HV 변화, 실패 표시, 화면 크기 검사.

Reset/HV 전환 fixture는 사용자 관찰을 시험 시나리오로 재현한 것입니다.
기기 펌웨어가 어떤 조건에서 자동으로 HV를 활성화하는지 규명한 모델이 아닙니다.
패킷 ID는 트랜잭션 번호가 아니므로 전송 후 늦게 도착한 동일 ID 응답의 근본적 모호성은 남습니다.

## 배포 및 재현

런타임 의존성 추가 없음: Python 3.10 이상, Tk, pySerial 3.5.
ZIP에 1.5.0 소스, wheel, pySerial wheel, 시험 코드, Verifier, 패킷 기록, 보고서, SHA256SUMS를 포함합니다.
기존 사용자 설정이나 1.4.0 폴더를 덮어쓰지 말고 새 폴더에 압축을 푸십시오.

제품 코드 차이는 `verification/source_changes_1_4_0_to_1_5_0.patch`에 있습니다.
시험 명령은 루트 README를 참조하십시오. 독립 설치 시험은 포함 wheel과 pySerial wheel만으로
새 가상환경을 만든 후 설치본의 External Simulator RUN/STOP 및 HV 분리 동작을 확인했습니다.
