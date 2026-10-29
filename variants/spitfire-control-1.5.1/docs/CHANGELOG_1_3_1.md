# 1.3.1 변경 사항

2026-10-27 실제 SASC/TDG의 비가동 조회 응답을 바탕으로 parser와 HV 단위를 수정했습니다.
새 실기 시험은 조회 명령만 사용했습니다. 출력·motor·opt-out·reset·설정 쓰기는 실기에서
수행하지 않았고 관련 회귀는 합성 장치에서 확인했습니다.

## 실제 firmware 응답 형식

1.3.0은 일부 정상 형식의 문자열을 해석하지 못했습니다. 1.3.1은 확인된 문법을 명령별로 처리합니다.

| 응답 예 | 1.3.1 처리 |
| --- | --- |
| `0.0 MHz` | 1065의 seed MHz 숫자와 원문 보존. 0은 읽을 수 있는 값이지만 출력 허용 조건은 충족하지 않음 |
| `3.399 KV` | 1040–1043의 전압을 GUI/model의 3399 V로 정규화 |
| `EXT CONT 1000.0` | 1051에서 source EXT, 1080에서 operation CONT 해석. 실제 pump Hz로 사용하지 않음 |
| `DELAY 1 ON BWD NENA 85.82` | 해당 channel의 지연과 ON/BWD/NENA를 각각 해석 |
| `DELAY 0 3100.0` | 1052의 delay 0 숫자 해석 |
| `NEG DUAL ON` | BWD mode 문자열 보존. 임의의 0/1 보호 판정으로 바꾸지 않음 |
| `0.008 MA` | 숫자 0.008과 원문 suffix 보존. A/mA로 추정 환산하지 않음 |

완전한 응답 문법을 검사하며 잘못된 channel, 중복·상충 flag, 알 수 없는 suffix,
뒤에 붙은 임의 문자열을 정상으로 취급하지 않습니다. 이전 합성 응답 형식도 유지합니다.
빈 응답은 계속 unavailable/unknown입니다. 실제 capability 조회의 빈 응답 7개를 0으로 채우지 않습니다.

## HV 표시·설정 단위 정정

원본 XP EXE의 2025/2026 callback은 전압 숫자를 추가 배율 없이 kV wire 값으로 전달하고
소수 둘째 자리로 포맷합니다. Python GUI는 V 단위이므로 송수신을 대칭으로 수정했습니다.

- 읽기: wire `3.399 KV` → GUI `3399 V`. 단위 없는 voltage 숫자도 legacy wire의 kV입니다.
- 일반 GUI 쓰기: 입력 V를 1000으로 나눈 뒤 kV 소수 둘째 자리로 전송합니다.
- **GUI 3399 V → wire `3.40` kV → 명목상 3400 V**입니다. 기존 설정을 그대로 복사해도
  원본의 0.01 kV 포맷 때문에 반올림될 수 있습니다.
- Programmer는 raw kV 입력을 유지하며 GUI용 V 환산을 적용하지 않습니다.
- simulator의 전압 상태도 raw kV와 정규화된 V를 구분하도록 맞췄습니다.

이 수정은 원본 정적 분석과 오프라인 회귀로 확인했습니다. 실기 HV 설정 쓰기는 하지 않았으며,
실제 전압 정확도·허용 범위·출력 동작을 검증한 결과가 아닙니다.

## HV 전류 표시

원본은 1055/1056의 숫자 부분을 배율 없이 표시하며 unit label이 확인되지 않았습니다.
관측 문자열 `MA`를 A·mA·메가암페어 중 하나로 확정할 근거가 없어 I1/I2에는 원문을 표시합니다.
예를 들어 `0.008 MA`를 `8 mA` 또는 `0.008 A`로 자동 변환하지 않습니다.

## Audit 진단 구분

기존 RX 원문과 5열 CSV 구조를 유지하면서 `ERROR`(exchange/timeout),
`INVALID_REPLY`(빈 payload), `PARSE_ERROR`(내용이 있으나 decoder/ACK 검사 실패),
`DEVICE_ERROR`(ERR·NACK·FAIL 응답)를 구분해 기록합니다.
RX와 진단 행을 함께 남기며 이를 별도 packet으로 중복 계산하지 않습니다.

## 통신 시험과 변경 범위

기존 로그의 timeout과 parser-invalid를 분리해 분석했습니다. 실제 조회 간격별 시험,
capability 조회 및 full scheduler 조회 시험을 수행했으며 결과는
[비가동 시험 보고서](NON_ACTUATION_TEST_20261027_KO.md)와 `validation_1_3_1` 자료에 기록합니다.
기존 XP host-only 캡처는 참고 비교이며 동일 조건의 전체 cadence 검증은 아닙니다.

**이번 릴리스는 제품 scheduler나 polling 주기를 변경하지 않습니다.**
최종 전체 시험 수, full scheduler 및 EXE 결과는 [최종 검증 보고서](VALIDATION_1_3_1.md)를 참조하십시오.
1.3.0 시험 수를 새 릴리스 결과로 재사용하지 않습니다.

실기에서 seed 0, NENA, opt-out 0, TCU humidity latch·TDG key·main communication 상태와
미확인 readback이 관측됐습니다. parser 개선은 이를 정상으로 바꾸지 않습니다.
운전 준비 완료나 10 Hz 광학 동기화 검증을 의미하지 않습니다.
