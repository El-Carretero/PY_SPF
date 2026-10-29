# 1.3.2 ARM / Clear Faults 수정 및 부분 검증

2026-10-27. 사용자 요청에 따라 ARM 유지, Clear Faults 및 관련 표시만 수정·시험했습니다.
1.3.1의 전체 304개 시험을 이번 버전에서 재실행하지 않았습니다.

## 변경 내용

- 외부 모드 필수 조회에 빈 값·해석 불가 응답이 와도 제어 ARM을 유지합니다.
- 해당 readback은 계속 미확인으로 남으며 출력 활성화의 기존 조건을 충족하지 못합니다.
- 이미 대기 중이던 HV ON·채널 ON·출력 mode 요청은 취소합니다. 정비 reset 요청은 보존합니다.
- timeout·오래된 통신·연결 종료·잘못된 쓰기 ACK는 계속 DISARM하며 해제 이유를 보존합니다.
- 버튼은 다음 동작을 표시합니다. DISARM 상태에서 `ARM`, ARM 상태에서 `DISARM`입니다.
- 상단 `CONTROL ARMED/DISARMED` 줄은 제어 권한과 차단/해제 이유를 보여줍니다.
- Clear Faults는 최근 통신, ARM, 외부 모드의 최근 HV OFF를 먼저 확인하고 사용자 확인을 받습니다.
  제출 실패 시 나머지 reset 요청을 이어서 제출하지 않습니다. 실제 송신 시에도 기존 조건을 다시 검사합니다.

HV key fault의 실제 출력 허용 조건, fault bit 해석, polling 목록·주기, UDP protocol,
전압 변환과 외부 펌프 정책은 변경하지 않았습니다. 소프트웨어 ARM은 실제 HV ON이 아닙니다.

## 시험 결과

| 시험 | 결과 |
| --- | --- |
| ARM/reset 관련 회귀 | 38개 통과, 실패·오류·skip 0 |
| 실제 readback을 사용하는 GUI 자동 시험 | 16개 확인 항목 통과 |
| ARM 유지 | 새 빈 1044·1069 응답을 받으며 6.36초 유지 확인; 총 ARM 구간 약 7.69초 |
| Clear Faults | ARM 재요구 없이 확인 단계 진입; 2049·2052 두 요청이 실제 송신 직전 검사를 통과 |
| 실기 reset | 두 요청 모두 시험용 transport에서 송신 직전 취소. 실제 reset 쓰기 0 |
| 성공한 실기 GUI 시험 송신 | 조회 90건, 실제 쓰기 0, HV readback 5건 모두 0 |
| 종료 | 수동 DISARM 성공, 버튼 ARM 복귀, 연결 종료, 저장 설정 동일 |
| EXE 시작 확인 | `--help` 실행 종료 code 0. EXE의 전체 GUI 시험은 이번 범위에서 재실행하지 않음 |
| EXE·wheel | 빌드 완료. EXE 내 포함된 15개 모듈의 코드가 소스와 일치, wheel 17개 모듈 byte 일치 |

회귀시험은 실제 ARM 검사를 거치는 비네트워크 fixture와 실제 Tk GUI를 사용합니다.
빈/오류 응답에서 ARM 유지, 출력 차단, 대기 출력 명령 취소, Clear Faults 두 명령 처리,
HV ON·미확인·stale 상태의 reset 차단, 송신 직전 재검사, timeout·수동 DISARM·잘못된
쓰기 ACK의 권한 해제, 사용자 취소 및 버튼 표시를 확인했습니다.

실기 GUI 시험은 소스 GUI의 실제 버튼 콜백과 controller를 실행했습니다. 최종 실행은
화면 좌표 클릭이 아닌 자동 시험입니다. 시험용 송신 간격은 200 ms이며 제품 scheduler는
변경하지 않았습니다. `recvfrom` 기록은 NIC 선로 capture가 아닙니다.

## 시험 중 발견한 조건

첫 화면 제어 실행에서는 창 선택 지연으로 ARM 조작을 완료하지 못했습니다.
첫 자동 시험에서는 빈 응답 후 ARM 유지에 성공했으나, 시험용 감속으로 마지막 HV
readback이 6초보다 오래되어 Clear Faults가 진행되지 않았습니다. 이 기록은 실패로 보존했습니다.
최종 시험에서는 HV를 명시적으로 재조회한 뒤 Clear Faults를 눌러 해당 경로를 통과했습니다.
프로그램은 오래된 HV OFF를 새 값처럼 사용하지 않습니다.

실제 사용 중 Clear Faults가 HV OFF 재조회를 요청하면 새 HV OFF 표시를 확인한 뒤 다시
누르십시오. 실제 timeout으로 DISARM되면 통신 회복 후 다시 ARM해야 합니다.
이번 결과는 timeout의 원인 해결, fault의 실제 해제 또는 실제 출력 운전을 검증한 것이 아닙니다.

## 기록

`validation_1_3_2/targeted_tests_132.*`와
`validation_1_3_2/live_gui_automated_run02/summary.json`이 최종 시험 결과입니다.
최초 미완료/실패 실행과 raw TX/RX, 변경 diff, 송신 packet 독립 대조도 함께 보존했습니다.
`build_verification.json`에 EXE·wheel hash와 코드 대조 목록이 있습니다.
기존 `validation_1_3_1`은 이전 버전의 기록입니다.
