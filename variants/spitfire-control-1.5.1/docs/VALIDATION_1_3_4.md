# Spitfire Python Control 1.3.4 — fault reset 조건 수정

2026-10-27. 실제 장비의 사용자 조작 로그를 읽고 XP 원본 callback과 대조했습니다.
이번 작업에서는 장비에 읽기/쓰기 명령을 보내지 않았습니다. 시험은 오프라인입니다.

## 수정 이유와 내용

1.3.3에는 TCU/TDG fault reset 전에 `TDG:HV:ON?`의 최신 값이 0이어야 한다는
소프트웨어 조건이 있었습니다. 키를 켠 뒤 Key bit는 해제되고 HV readback은 1이 된
사용자 기록에서 이 조건이 reset을 막았습니다. 원본 reset callback에 없는 제약을
추가했던 것이며 1.3.4에서 제거했습니다.

- GUI Clear Faults의 HV OFF 검사 제거.
- 2049 ECU:RESETFAULTS 및 2052 TDG:RESFAULT의 controller 제출·송신 전 HV OFF 검사 제거.
- 최신 연결 응답과 사용자 확인은 유지. HV OFF/ON 명령을 자동으로 추가하지 않음.
- BWD reset 2018, 타이밍 설정·opt-out 등의 별도 HV OFF 조건은 이번 변경 대상이 아님.
- timeout, 연결 상실, 잘못된 쓰기 응답 시 대기 쓰기 취소 및 송신 직전 연결 검사는 유지.
- 기존의 빈 reset receipt 처리와 후속 readback, 실제 fault bit 표시를 유지.

## 사용자 로그에서 확인한 상태

설치된 1.3.3 audit의 read-only snapshot을 사용했습니다. 아래 시각은 한국시간(KST)입니다.

| 시각 | 항목 | 값 |
| --- | --- | --- |
| 22:33:54 | 최초 COMSTATUS 응답 | 5 |
| 22:34:10 | 이 세션 최초 transport timeout | HED:STB? |
| 22:34:11–12 | 사용자 Clear Faults | 2049와 2052 모두 송신, 빈 receipt 기록 |
| 22:34:14 | TDG fault | 0X00334428 → 0X00330428: Key bit 0x4000 해제 |
| 22:34:15 | TDG fault | 0X00330429 |
| 22:34:16 | TDG current | 0X00330429: Key bit 해제 |
| 22:34:21 | HV readback | 0 → 1 |

조회 주기와 timeout 때문에 이 표는 실제 스위치 변화의 정확한 동시성을 뜻하지 않습니다.
해당 기록의 소프트웨어 TX에는 HV ON 명령이 없고 2049/2052 reset만 있었습니다.
키를 켰다는 사용자 설명과 위 readback 변화를 함께 판단했습니다.

## Main comm: 확인된 사실과 미확인 원인

- COMSTATUS는 기록 내 모든 유효 응답에서 5입니다. 복원된 XP mapping에서는
  Main bit 0x01과 Empower bit 0x04가 set된 값입니다.
- Key bit가 해제된 뒤에도 값이 5이므로 이 기록에서 두 표시는 별개입니다.
- 이 세션의 첫 timeout 이전부터 5였습니다. 그렇다고 이전 통신 실패의 latch나
  polling 영향까지 배제할 수는 없습니다.
- EMPOPTOUT?는 0입니다. PC GUI의 External 모드 선택과 장비의 Empower opt-out 적용은
  서로 다른 단계입니다. 이 로그에서는 장비 opt-out이 꺼져 있습니다.
- 이것만으로 Empower 미연결이 Main bit까지 발생시킨다고 단정할 수 없습니다.
  Main bit의 firmware 내부 발생·해제 조건은 아직 규명하지 못했습니다.
- Main comm가 PC 연결 전체 단절, 장비 고장 또는 polling 과속 때문이라는 확정 진단은 없습니다.
  다음 대조 대상은 실제 opt-out 상태별 COMSTATUS 변화 및 같은 조건의 XP/Python 통신입니다.

Main comm를 없앴다고 주장하거나 해당 비트를 0으로 덮어쓰지 않았습니다.
1.3.3 보고서의 'reset 후 Key bit가 남음'은 당시 상태의 기록입니다.
이번 사용자 조작 기록에서는 Key bit가 해제됐으므로 Key 오류가 계속 남는다는 결론은 갱신합니다.

## XP 원본 근거

제공된 원본 EXE의 `_cllbckcmd_reset`(0x412428–0x4124DA)은 UI commit event를 확인한 뒤
2044, 2049, 2052, 2050을 queue에 넣고 fault 조회를 요청합니다.
이 callback에는 HV/key 상태에 따른 조건 분기가 없습니다.
이는 PC callback의 근거이며 HV ON 상태의 firmware 동작을 실험으로 보장한 결과는 아닙니다.
외부 모드는 기존처럼 TCU/TDG reset 2049/2052만 요청합니다.

## 검증

- 전체 회귀 시험: **319개 통과**, 실패·오류·skip 0. 외부 장비 I/O 차단, UDP는 loopback만.
- HV=1, HV unknown/stale에서 연결이 최신이면 reset 확인·queue·송신 검사 통과.
- 실제 Key 해제/HV=1 로그를 메모리 fixture로 재생해 동일 조건 확인.
- reset 직전 연결이 오래되면 전송 취소. HV readback alias 오류는 fault reset을 막지 않되,
  BWD reset과 opt-out의 기존 조건은 유지.
- EXE External·Empower GUI: 둘 다 시뮬레이터 검사 PASS, 화면 잘림 0, 외부 I/O 차단.
- EXE 15개 runtime 모듈이 테스트 소스와 일치하고 wheel Python 원문도 일치.

**실장비의 HV ON 상태에서 fault reset을 실행한 시험은 하지 않았습니다.**
이번 검증에 포함된 HV on/off는 시뮬레이터 내부 동작입니다. 운영자 설정과 설치된 1.3.3은 변경하지 않았습니다.

## 근거 파일

- [전체 시험](validation_1_3_4/full_tests_134.json), [상세 결과](validation_1_3_4/full_tests_134.txt)
- [사용자 로그 변화 발췌](validation_1_3_4/operator_transition_evidence.json)
- [XP reset callback 바이트와 호출 ID](validation_1_3_4/xp_reset_callback_evidence.json)
- [EXE 시험](validation_1_3_4/exe_gui_results.json), [빌드 대조](validation_1_3_4/build_verification.json)
