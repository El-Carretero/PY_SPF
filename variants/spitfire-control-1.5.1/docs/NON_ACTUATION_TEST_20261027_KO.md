# 비가동 조회 시험과 1.3.1 수정 보고 — 2026-10-27

실제 장치에서는 **조회 명령만 전송**해 응답 형식과 통신 간격을 확인했습니다.
읽기 실패의 일부는 parser가 실제 firmware 문법을 처리하지 못한 문제였으며 1.3.1에서 수정했습니다.
빈 응답과 실제 보호·타이밍 조건 미충족은 그대로 남깁니다. 이번 시험은 출력 운전이나
광학 동기화의 검증이 아닙니다.

## 시험 범위와 비가동 근거

| 대상 | 수행한 작업 | 확인 범위 |
| --- | --- | --- |
| P04 실제 장치 연결 | 제한된 query-only probe, capability 조회, 간격별 응답 시험 | 송신 raw datagram의 모든 command ID가 2000 미만인지 확인, 쓰기 0건 |
| P04 실제 상태 | 1021 HV 상태 조회 | 새 시험의 경계에서 HV OFF readback 확인 |
| Python 1.3.1 | 실제 응답 replay, unit·parser·보호 정책 회귀, simulator GUI | 실제 출력 활성화 없이 소프트웨어 동작 확인 |
| XP 원본 EXE/UIR | 전압·전류 callback과 표시의 정적 분석 | 이번 실제 장치 시험에서 원본 프로그램을 실행하지 않음 |
| P07 기존 host-only 캡처 | 이전 XP→가상 controller 통신의 cadence 재분석 | 실제 장치 부하 시험이나 동일 조건의 완전 비교가 아님 |

새 실기 시험에서는 레이저 RUN, HV ON, 채널 ON, motor, opt-out, reset과 설정 쓰기를
수행하지 않았습니다. 2000번대 쓰기를 raw 송신 단계에서 제한했습니다.
원본 XP GUI는 시작 과정에 2047 또는 2030 INT→EXT 쓰기가 포함될 수 있어 실제 장치에
연결해 실행하지 않았습니다. 해당 쓰기 경로는 정적 분석으로 확인했습니다.

이전에 생성된 audit 로그에는 HV ON/OFF readback과 이전 HV OFF 전송 기록이 포함돼 있습니다.
이는 아래의 **기존 로그 분석 자료**이며 새 query-only 시험이 보낸 명령으로 합산하지 않습니다.
HV OFF readback만으로 펌프·seed의 광출력까지 꺼졌다고 판단하지 않습니다.

## 기존 1.3.0 로그에서 확인한 문제

분석 구간은 2026-10-27 11:14:44–11:19:44 UTC의 약 5분입니다.
전체 로그는 약 29분이며 연결 대기·재연결 등의 구간이 섞여 있어 같은 평균으로 비교하지 않습니다.

| 지표 | 마지막 약 5분의 관측값 |
| --- | ---: |
| TX | 3,692건 |
| 평균 TX | 약 12.31건/초 |
| 달력상 1초 bin의 최대 TX | 18건 |
| transport timeout | 15건, 각 약 3초 |
| 기존 parser가 거부한 RX | 654건 |
| 위 거부 중 내용이 있는 응답 | 489건 |
| 위 거부 중 빈 응답 | 165건 |

내용이 있는 거부 응답에는 `0.0 MHz`, `EXT CONT 1000.0`,
`DELAY 1 ON BWD NENA 85.82`, `DELAY 2 ON BWD NENA 990.25`가 포함됐습니다.
이들은 UDP 응답이 도착했지만 기존 parser가 유효한 state로 만들지 못한 사례입니다.
따라서 timeout 15건과 parser-invalid 654건은 서로 다른 문제로 구분합니다.

Audit CSV에는 목적지·transport·pump mode·process/session ID가 없어 정확한 세션 경계를
로그만으로 증명할 수 없습니다. 같은 command ID의 늦은 응답도 새 요청과 완전히 구별할 수 없습니다.
평균 전송률만으로 timeout의 원인이 controller 과부하라고 확정하지 않습니다.

## 새 실제 장치 조회 시험

전송 간격별 시험은 한 요청의 응답을 확인하는 query-only probe로 진행했습니다.
표의 건수는 measurement 요청이며 초기 identity·HV boundary 조회는 별도입니다.

| 단계 | 요청 간격 | 측정 요청 수 | 관측 timeout |
| --- | ---: | ---: | ---: |
| 초기 저속 조회 | 1,000 ms | 30 | 0 |
| 중간 속도 조회 | 500 ms | 60 | 0 |
| capability 목록 조회 | 1,000 ms | 60 | 0 |
| 빠른 조회 | 200 ms | 120 | 0 |
| 회복 확인 조회 | 1,000 ms | 15 | 0 |
| 100 ms 조회 | 100 ms | 180 | 0 |

이 결과는 해당 명령 집합과 시험 시간의 응답 성공입니다. 더 긴 운전, 다른 상태, 자동 polling을
포함한 전체 traffic의 안정성을 보증하지 않습니다. 원래 scheduler를 사용하는 60초 조회 시험과
전체 소스/GUI/EXE 회귀의 최종 수치는 [최종 검증 보고서](VALIDATION_1_3_1.md)를 참조하십시오.
이번 수정에서는 제품 scheduler와 polling 간격을 변경하지 않았습니다.

## 실제 응답과 parser 수정

Capability 응답 60건을 수정한 parser에 replay한 결과 내용이 있는 53건을 해석했고,
빈 응답 7건은 유효값을 만들지 않았습니다. 이 replay는 저장된 응답을 사용한 오프라인 시험입니다.

| 명령·원문 예 | 수정한 해석 | 의미의 한계 |
| --- | --- | --- |
| 1065 `0.0 MHz` | measured seed = 0 MHz | 파싱 성공과 seed 준비는 다름. 양수·설정 범위 조건 미충족 |
| 1040 `3.399 KV` | HV1 setpoint = 3399 V | 실제 측정 HV가 아니라 설정 readback |
| 1041 `3.139 KV` | HV2 setpoint = 3139 V | 설정 readback |
| 1042 `0.008 KV`, 1043 `0.007 KV` | 각각 8 V, 7 V | HV OFF digital 상태와 구분되는 아날로그 readback |
| 1051 `EXT CONT 1000.0` | source = EXT | 숫자 1000.0을 외부 펌프 실제 Hz로 간주하지 않음 |
| 1080 `EXT CONT 1000.0` | operation = CONT | source 조회와 operation 조회의 상태를 분리 |
| 1045 `DELAY 1 ON BWD NENA 85.82` | channel 1, ON, BWD, NENA, delay 85.82 | NENA를 ENA로 바꾸지 않음 |
| 1052 `DELAY 0 3100.0` | delay 0 = 3100.0 | 별도 형식으로 처리 |
| 1027/1054 `NEG DUAL ON` | 원문 mode 보존 | 보호가 정상이라는 임의 boolean으로 바꾸지 않음 |
| 1055 `0.008 MA`, 1056 `0.009 MA` | 숫자 크기와 원문 suffix 보존 | A/mA의 의미·배율 미확정 |

빈 응답이 관측된 ID는 **1017, 1020, 1022, 1044, 1069, 1079, 1083**입니다.
이들을 unsupported라고 확정하지 않고 unavailable/unknown으로 둡니다.
특히 필수 보호 조회 1044와 1069의 빈 응답은 출력 활성화 조건을 충족하지 못합니다.

알 수 없는 단위나 문법, channel 불일치, 중복·상충 flag와 뒤에 추가된 임의 문자열은
정상으로 받아들이지 않습니다. wire 원문은 정규화된 숫자와 함께 보존합니다.

## 전압의 읽기·쓰기 단위

원본 XP callback 2025/2026은 UI 숫자를 추가 배율 없이 `%5.2f`로 전송합니다.
실기 readback의 `KV`와 원본 읽기·쓰기 scale=1을 대조하면 raw wire 전압 단위는 kV입니다.
Python GUI는 V를 사용하므로 다음처럼 대응시켰습니다.

| 경로 | 예 |
| --- | --- |
| 읽기 | wire `3.399 KV` → GUI `3399 V` |
| 일반 GUI 쓰기 | 입력 `3399 V` ÷ 1000 → `3.399 kV` → wire `3.40` |
| 반올림 결과 | wire `3.40 kV`는 명목상 `3400 V` |
| Programmer | raw kV를 입력. GUI V→kV 변환을 적용하지 않음 |

**3399 V를 넣으면 3399 V 그대로 전송되는 것이 아닙니다.** 원본의 kV 소수 둘째 자리 형식으로
반올림합니다. 읽은 setpoint를 다시 적용할 때도 이 차이가 생길 수 있습니다.
단위 없는 voltage reply도 legacy kV로 해석하고, 명시적 `V` reply는 V로 처리합니다.

이 변환은 정적 분석·formatter·simulator 회귀로 확인했습니다. 실제 HV setpoint를 쓰거나
전압을 올려 시험하지 않았습니다. 원본의 수치 입력 범위나 실제 출력 허용 범위는 확인하지 못했습니다.

1055/1056의 원본 handler는 숫자 부분을 배율 없이 표시하고 unit label은 확인되지 않았습니다.
`MA`를 대소문자 관례만으로 A 또는 mA로 해석할 근거가 없어 I1/I2에 원문을 표시합니다.
매뉴얼의 검색 가능한 본문에서도 해당 HV current 단위 정의를 찾지 못했습니다.

## 관측된 출력 활성화 조건

| 관측 | 해석 |
| --- | --- |
| 1021 = 0 | 조회 시 HV OFF 확인 |
| 1065 = `0.0 MHz` | 현재 readback의 seed 주파수가 출력 허용 범위 밖 |
| PC1/PC2 = `ON BWD NENA` | BWD는 있으나 ENA 확인 조건 미충족 |
| 1068 = 0 | Empower opt-out 확인 조건 미충족 |
| 1088 = 3089 | 알려진 humidity latch bit `0x10`이 포함됨 |
| 1066 = `0X00334408` | 알려진 TDG key bit `0x4000` 및 다른 nonzero bit 포함 |
| 1089 = 5 | main `0x01`과 Empower `0x04` 통신 bit 포함 |
| 1044·1069 빈 응답 | humidity override와 head opt-out 상태 미확인 |

전달된 실제 응답을 바탕으로 한 소프트웨어 해석이며, 장치 내부 원인을 물리적으로 진단한 결과는 아닙니다.
위 값들을 reset하거나 override/opt-out을 써서 해소하지 않았습니다.
현재 상태는 외부 모드의 출력 활성화 조건을 충족하지 않습니다.
parser 수정 이후에도 이 조건을 우회하거나 0·정상으로 가공하지 않습니다.

## 기존 XP host-only 캡처 비교의 한계

P07에서 이전에 기록한 XP 원본→격리된 가상 controller의 일부 구간은 약 10.1–11.2 datagram/s였습니다.
그 캡처는 UI 조작·재연결과 가상 응답 조건의 영향을 받습니다. 이전 Python baseline도
Empower 모드였고 외부 시나리오는 짧은 `auto_poll=False` 정책 확인이었습니다.
따라서 이번 실제 장치의 외부 모드 전체 traffic과 같은 조건의 cadence 비교가 아닙니다.

XP와 Python의 전체 polling 목록·상태·응답 지연·화면 조작을 맞춘 장기 비교는 아직 완료하지 않았습니다.
그 비교 없이 원본과 완전히 같은 속도라거나 기존 timeout 원인이 속도 때문이라고 단정하지 않습니다.
이번 원본 분석은 저장된 캡처와 binary를 사용했으며 새로 XP 프로그램을 실기에서 실행하지 않았습니다.

## 결과 자료와 남은 확인

최종 검증 수치와 raw 자료는 `docs/validation_1_3_1` 수집본 및 [최종 검증 보고서](VALIDATION_1_3_1.md)를 기준으로 합니다.
전체 소스 304개와 두 모드의 소스·EXE GUI 시험은 통과했습니다. 실기 scheduler에는 timeout이 남아 있으며
세부 분모와 오류·HV 집계는 위 최종 보고서를 기준으로 합니다.

| 근거 파일 | 내용 |
| --- | --- |
| `live_audit_analysis_20261027.json` | 기존 로그 전송률·timeout·parser-invalid 및 분석 한계 |
| `capability_parser_replay_131_final_units.json` | 실제 60개 응답의 parser replay |
| `original_hv_voltage_units.json` | 원본 HV read/write callback, raw 단위·소수 자리 근거 |
| `original_hv_current_units.json` | 전류 단위 미확정과 원문 보존 근거 |
| `xp_previous_capture_cadence.json` | 이전 P07 host-only capture의 cadence 분석 |
| 새 query-only probe·scheduler raw TX/RX | 실제 시험의 전송 ID·HV 경계·응답·오류 기록 |

작업 원본은 `tmp/live_review_20261027`에 있으며 배포용 근거는 `docs/validation_1_3_1`에 수집합니다.
확인된 변경은 응답 처리와 단위 변환입니다. 실제 opt-out 지원·효과, 빈 보호 응답의 의미,
보호 fault 원인, seed 입력, DM1 동기 출력·지연·지터, 10 Hz 운전과 광학 위상은 별도 확인 사항입니다.
