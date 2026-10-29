# Spitfire Python Control 1.3.3 — ARM 제거 및 fault reset 검증

2026-10-27 / P04 / SASC 1.5.0 / TDG-S 04.001.003/01.003.092.
이 보고서는 소프트웨어 수정 완료와 장비 오류 상태 해소 여부를 구분합니다.

## 결과

- 소프트웨어 ARM/DISARM 버튼, 상태, API와 전송 조건을 완전히 제거했습니다.
- 1.3.2에서 첫 TCU reset의 빈 응답을 쓰기 실패로 처리해 TDG reset을 취소하던 문제를 수정했습니다.
- 실장비의 Main comm와 Key 비트는 TDG reset 뒤에도 남았습니다. 정상으로 숨기지 않았으며,
  이 두 장비 상태의 원인은 이번 원격 시험만으로 확정하지 못했습니다.
- 출력 운전은 시험하지 않았습니다. 실제 장비에 보낸 쓰기는 HV OFF를 확인한 뒤의
  `2052 TDG:RESFAULT` 한 번뿐입니다. HV ON, 채널 ON, 펌프, 모터, opt-out, override,
  전역 RESET/CLEAR 명령은 보내지 않았습니다.

## 변경 내용

### ARM/DISARM 제거

연결 응답이 최신이면 명령별 조건과 기존 확인 절차를 거쳐 설정·초기화를 바로 요청합니다.
별도의 권한 latch는 없습니다. OFF/STOP 우선 처리, 이미 dequeue된 명령까지 취소하는
세대 번호 검사, timeout·연결 상실·명시적 쓰기 오류 시 대기 쓰기 취소를 유지했습니다.
통신 회복 후 새 요청을 보낼 수 있지만 취소된 요청을 자동 복원하거나 재전송하지 않습니다.
출력 활성화의 보호·타이밍 readback 검사와 외부 모드 reset의 최신 HV OFF 조건은 유지합니다.

### 빈 reset receipt 처리

설치된 1.3.2 기록에서 **12:53:37 UTC**에 `[2049]ECU:RESETFAULTS`를
보낸 뒤 `<2049>`를 INVALID_REPLY로 처리했습니다. 그 세션에 TDG reset 2052의 TX는 없었습니다.
이번 직접 조회에서는 실제 TDG reset도 `<2052>`라는 빈 응답을 반환했습니다.

1.3.3은 요청 ID와 일치하는 2049/2052의 빈 receipt만 `UNCONFIRMED_WRITE`로 기록합니다.
성공 ACK를 만들지 않고 후속 reset 및 fault 조회를 계속합니다. ERR/NACK/BUSY, 다른 쓰기의
빈 응답과 통신 timeout은 기존 실패 처리를 유지합니다.
TCU reset 뒤에는 GUI가 사용하는 canonical 1088을 조회하고, TDG reset 뒤에는
1066 fault, 1039 current status, 1089 COMSTATUS를 조회합니다. 값이 남으면 그대로 표시합니다.

### Fault 표시

Fault 화면에 PC 연결 응답과 장비 Main comm flag를 구분해 표시합니다.
TDG Key의 current/fault register 비트도 함께 표시하며, 오래된 값은 unknown/stale입니다.
`Clear Faults`는 reset을 요청하고 실제 상태를 다시 읽는 기능이며 표시를 강제로 끄지 않습니다.

## 실제 장비에서 확인한 값

RDC를 통해 진단 스크립트와 실제 소스 GUI를 실행했습니다. UDP 목적지와 읽기 명령을
허용 목록으로 제한하고, 단일 reset에는 횟수 제한과 송신 직전 HV OFF 확인을 적용했습니다.

| 항목 | reset 전 | reset 후 3회 | 해석 범위 |
| --- | --- | --- | --- |
| 1021 HV ON? | 0 | 모두 0 | HV OFF readback 유지 |
| 1089 COMSTATUS? | 5 | 모두 5 | Main bit 0x01과 Empower bit 0x04가 set |
| 1066 TDG fault | 0X00334408 | 모두 0X00334428 | Key bit 0x4000 유지 |
| 1039 TDG current | 0X00334428 | 모두 0X00334428 | 같은 Key bit 유지 |
| 1019 TDG module status | 0.000000 | reset 전 조회 | module 통신 bit 0x800 미검출 |
| 1087 fault override | 0 | reset 전 조회 | override를 켜지 않음 |
| 1068 Empower opt-out | 0 | 별도 초기 조회 | opt-out을 켜지 않음 |

TDG reset은 **13:03:38 UTC / 22:03:38 KST**에 한 번 송신했습니다.
단순히 PC UDP 응답이 있다는 이유로 COMSTATUS의 Main 비트를 무시할 근거는 없습니다.
Key 비트가 남는 원인을 물리적 키, 접점, 배선 또는 firmware 중 하나로 확정할 근거도 없습니다.
현장에서는 장비 표시와 실제 키 입력 상태를 함께 확인하고, 제조사 정보로 COMSTATUS 의미와
지속 원인을 대조해야 합니다. 이번 수정은 물리적 인터록 우회나 오류 정상화 기능을 추가하지 않습니다.

원본 XP 실행 파일의 정적 분석에서도 1089의 bit 0x01은 MAIN_COM,
1066의 bit 0x4000은 TDG_KEY 컨트롤에 전달됩니다. 이는 복원된 표시 경로의 근거이며,
이번 시험에서 XP 프로그램을 장비에 동시에 연결해 동작 동등성을 검증한 것은 아닙니다.
기존 근거는 [XP 대조 보고서](XP_PARITY_REVIEW_1_3_0.md)를 참조하십시오.

## 검증

| 시험 | 결과 | 범위 |
| --- | --- | --- |
| 전체 회귀 시험 | 316 / 316 PASS, skip 0 | 외부 장비 I/O 차단, UDP는 loopback만 |
| 신규 no-ARM/reset 회귀 | 전체 시험에 포함 | 빈 reset receipt 연속 처리, HV 변경·stale·timeout, 잘못된 ACK, 실제 fault 재현 |
| 실제 응답 GUI 시험 | 10 / 10 PASS | 읽기 65패킷, 쓰기 0, reset 2개는 송신 직전 검사 후 보류 |
| EXE external GUI | PASS | 시뮬레이터만, 외부 I/O 차단, 화면 잘림 0 |
| EXE Empower GUI | PASS | 시뮬레이터만, 외부 I/O 차단, 화면 잘림 0 |
| EXE/소스 대조 | 15 모듈 일치 | 테스트한 소스와 내장 코드 일치 |
| wheel/소스 대조 | PASS | 패키지 Python 원문 일치 |

실제 GUI 시험에서는 빈 1044/1069 응답이 반복돼도 ARM 단계 없이 Clear Faults 확인창에
도달했고, 2049/2052 모두 실제 전송 직전 검사를 통과했습니다. 이 GUI 시험의 reset은
전송하지 않았습니다. 앞의 단일 실제 TDG reset 시험과 구분해야 합니다.
운영자 설정 파일은 변경하지 않았습니다.

EXE의 HV on/off 검사는 **합성 시뮬레이터 내부 시험**입니다. 실제 장비에서의 HV ON,
발진, 10 Hz 운전, 광학 동기화, 물리적 인터록 검증 결과로 해석하면 안 됩니다.

## 근거 파일

- [전체 시험](validation_1_3_3/full_tests_133.json), [상세 출력](validation_1_3_3/full_tests_133.txt)
- [1.3.2 reset 기록 발췌](validation_1_3_3/previous_132_reset_excerpt.json)
- [초기 조회](validation_1_3_3/fault_query_baseline.json), [실제 단일 TDG reset](validation_1_3_3/tdg_reset_once.json)
- [실제 응답 GUI 검사](validation_1_3_3/live_no_arm_gui/summary.json)
- [EXE GUI 검사](validation_1_3_3/exe_gui_results.json), [빌드 대조](validation_1_3_3/build_verification.json)

배포 ZIP의 `dist/SpitfirePythonControl.exe`와 `start_external_pump.cmd`를 사용합니다.
이전 버전 실행 파일을 덮어쓰지 않도록 ZIP 전체를 별도 폴더에 해제하십시오.
