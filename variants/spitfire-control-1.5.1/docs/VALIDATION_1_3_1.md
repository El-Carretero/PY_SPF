# 1.3.1 최종 검증 결과 — 2026-10-27

**소스 자동 시험 304개와 두 모드의 소스·EXE GUI 시험을 통과했습니다.** 실제 장치에서는
조회만 시험했으며, 10개 단계에서 전송한 2,397개 명령을 독립적으로 해석해 모두 등록된
조회 문자열과 일치하고 쓰기는 0건임을 확인했습니다. 전체 scheduler 조회에는 timeout이
남아 있어 통신 문제가 모두 해소됐거나 운전 준비가 끝났다고 판단하지 않습니다.

## 검증 범위

| 검증 | 결과 | 의미 |
| --- | --- | --- |
| 전체 소스 자동 시험 | 304/304 PASS, 실패 0, 오류 0, skip 0 | 오프라인 I/O 차단 환경. 실제 장치 쓰기 검증 아님 |
| Empower 소스 GUI | PASS | simulator, clipping 0, 입력값 보존·Q-switch 왕복, serial 미개방 |
| External 소스 GUI | PASS | simulator, clipping 0, startup 쓰기 0, 명시적 opt-out·EXT·HV ON/OFF 확인 |
| Empower·External EXE GUI | 두 모드 PASS | simulator, clipping 0, 외부 I/O 차단, 저장 설정 미접근 |
| 소스·wheel 무결성 | PASS | Python 46개 AST 검사, wheel 17개 모듈이 소스와 byte 단위 일치 |
| 실제 장치 직접 probe 6단계 | 측정 465건, 전체 TX 511건, timeout 0 | 제한된 query-only 목록의 해당 실행 결과 |
| 실제 장치 scheduler 4단계 | 전체 TX 1,886건, timeout 9건 | 제품 scheduler 기반 각 약 60초 조회. 세부 결과는 아래 표 |
| 실제 응답 capability replay | 60건 중 내용 있는 53건 해석, 빈 응답 7건 unknown 유지 | firmware 형식 호환성 확인 |
| 설정 파일 | 전후 내용·SHA-256 동일 | 저장된 설정 변경 없음 |
| 종료 시 연결 | UDP 1024 endpoint 없음, 기존 GUI disconnected | 종료 확인 시점의 상태 |

GUI의 opt-out·HV ON/OFF는 **합성 장치 시험**입니다. 실기에서는 레이저 RUN, HV ON,
채널 ON, motor, opt-out, reset과 설정 쓰기를 수행하지 않았습니다.
원본 XP 프로그램은 startup에 2047 또는 2030 쓰기가 포함될 수 있어 이번 실기 시험에서
실행하지 않았습니다. 원본 EXE/UIR 정적 분석과 이전 P07 host-only 캡처는 별도 근거입니다.

## 실제 조회의 비가동 근거

`aggregate_final.json`은 완료된 10개 진단 단계만 집계합니다. 이전 사용자 GUI 로그나
해당 디렉터리에 없는 후속 단독 조회는 포함하지 않습니다.
송신 `data_hex`를 독립적으로 decode하고 command ID뿐 아니라 본문도 원본 조회 목록과
정확히 대조했습니다. 2,397개 모두 조회이며 쓰기·목록 밖 명령은 0건입니다.

이 단계들에서 기록한 1021 HV 응답은 **176건 모두 0**입니다.
집계에 포함된 마지막 HV 응답은 2026-10-27 **20:49:16.991 KST**의 `<1021> 0`입니다.
이는 관측 시점의 HV OFF이며 펌프·seed의 광출력을 측정한 결과가 아닙니다.
raw RX 기록은 프로그램 socket의 `recvfrom` 관측이며 별도 NIC packet capture는 아닙니다.

## 직접 probe 6단계

전체 TX에는 preflight·boundary·postflight 조회를 포함하며 측정 건수와 구분합니다.

| 단계 | 설정 간격 | 측정 요청 | 전체 TX | timeout |
| --- | ---: | ---: | ---: | ---: |
| baseline | 1,000 ms | 30 | 35 | 0 |
| step | 500 ms | 60 | 67 | 0 |
| capability | 1,000 ms | 60 | 64 | 0 |
| step | 200 ms | 120 | 131 | 0 |
| recovery | 1,000 ms | 15 | 19 | 0 |
| step | 100 ms | 180 | 195 | 0 |
| 합계 | — | 465 | 511 | 0 |

Capability의 응답 도착 60건과 상태 해석 성공 53건은 서로 다른 수치입니다.
빈 응답도 transport 관점에서는 응답이 도착한 것이며 정상 상태값을 받은 것은 아닙니다.

## 제품 scheduler 기반 실제 조회

각 조건은 약 60초 동안 한 번씩 실행했습니다. 모든 단계에 query-only 송신 제한을 적용했습니다.
100/200 ms 조건의 대기는 **시험용 transport에만** 추가했으며 제품 scheduler·polling 정책은
변경하지 않았습니다. 전체 TX에서 각 preflight 2건을 제외한 본 실행 요청 수를 따로 표시합니다.
본 실행에는 초기 조회가 포함됩니다.

| 조건 | 전체 TX | 본 실행 요청 | timeout | `INVALID_REPLY` | `PARSE_ERROR` |
| --- | ---: | ---: | ---: | ---: | ---: |
| 추가 대기 없음 | 670 | 668 | 5 | 30 | 0 |
| 시험용 100 ms 대기 | 533 | 531 | 2 | 26 | 0 |
| 시험용 200 ms 대기 + RX 기록 | 288 | 286 | 1 | 16 | 0 |
| Automatic polling OFF + RX 기록 | 395 | 393 | 1 | 34 | 0 |
| 합계 | 1,886 | 1,878 | 9 | 106 | 0 |

106건의 `INVALID_REPLY`는 모두 **1044·1069의 빈 응답**입니다.
내용이 있는 응답을 새 decoder가 거부한 `PARSE_ERROR`는 이 4개 단계에서 0건입니다.
Automatic polling을 꺼도 identity heartbeat와 외부 모드의 **18개 필수 조회**는 계속됐습니다.
OFF 조건의 본 실행은 초기 조회 40건, 필수 조회 300건, heartbeat 53건으로 구성됐습니다.

200 ms 조건의 1039 timeout과 Automatic polling OFF 조건의 1019 timeout에서는
각 약 3초 대기 동안 socket RX datagram이 기록되지 않았습니다.
이는 parser가 받은 값을 거부한 사례와 다르지만, firmware 응답 지연·물리적 packet 손실·OS/network
중 어디에서 발생했는지를 확정하지는 못합니다.
조건별 요청 수와 명령 구성도 다르고 비무작위 단일 실행이므로 5→2→1→1이라는 timeout 건수만으로
전송 속도가 원인이라고 판단하지 않습니다. 장기 반복 시험이나 동일 조건 비교의 결과가 아닙니다.

## 수정한 동작과 로그 구분

실제 firmware의 `MHz`, `KV`, `EXT CONT ...`, `DELAY ...`, `NEG DUAL ON` 형식을
명령별로 처리하고 원문을 보존합니다. GUI 전압은 V, raw 2025/2026은 kV로 송수신을 맞췄습니다.
**GUI 3399 V는 원본의 kV 소수 둘째 자리 포맷으로 `3.40` kV, 명목상 3400 V로 반올림**됩니다.
실제 전압 설정을 써서 확인한 결과는 아닙니다. 전류 `MA`는 단위·배율 근거가 부족해 원문을 표시합니다.

Audit CSV는 기존 5열 구조와 RX 원문을 유지하고 진단 행을 다음처럼 구분합니다.

| 구분 | 기록 대상 |
| --- | --- |
| `ERROR` | exchange/timeout 등 통신 실패 |
| `INVALID_REPLY` | payload가 비어 상태값이나 ACK를 얻지 못함 |
| `PARSE_ERROR` | 내용은 있으나 상태 decoder 또는 ACK 형식 검사를 통과하지 못함 |
| `DEVICE_ERROR` | 장치가 `ERR`·`NACK`·`FAIL` 계열 응답을 반환 |

RX 행과 진단 행이 함께 기록되므로 행 수를 서로 다른 packet 수처럼 합산하지 않습니다.
이 구분은 원인 분석을 위한 기록이며 빈 응답을 정상으로 바꾸는 처리가 아닙니다.

## 남아 있는 실제 상태와 한계

Capability에서 빈 응답이 나온 ID는 **1017, 1020, 1022, 1044, 1069, 1079, 1083**입니다.
특히 1044 humidity override와 1069 head/compressor opt-out은 필수 보호 상태를 확인하지 못했습니다.
기록된 seed 0 MHz, PC1/PC2 NENA, Empower opt-out 0,
TCU humidity latch·TDG key·main communication 상태도 출력 활성화 조건을 충족하지 못합니다.
이를 해소하기 위한 reset·override·opt-out 쓰기는 수행하지 않았습니다.

소프트웨어 regression 통과와 실기 read-only 응답은 실제 HV 활성화·광출력·DM1 운전·
10 Hz 지원·광학 위상·지터 검증을 대신하지 않습니다. P07의 기존 XP host-only capture도
현재 외부 모드 실기와 동일한 조건의 전체 cadence 비교는 아닙니다.
제품의 polling 속도는 이번 릴리스에서 바꾸지 않았습니다.

설정 파일은 전후 SHA-256 `357fd2282997a31d13731da4ef478f5ff023d1444f620a2e7b9a5269549f5e53`으로 동일합니다.
최종 NIC snapshot은 link Up, 100 Mbps, error/discard counter 0이지만 단일 시점의 값이며
baseline 차이가 없어 손실 없는 경로의 증거는 아닙니다. UDP 1024 endpoint는 비어 있었고
기존 GUI는 연결 해제 상태로 확인했습니다.

## EXE 검증

배포 EXE를 Empower와 External 각각 simulator로 실행해 두 모드 모두 PASS, 종료 code 0을 확인했습니다.
두 모드의 clipping은 0이며 외부 I/O는 차단했고 사용자 설정을 읽거나 저장하지 않았습니다.
External의 startup 쓰기 0, 명시적 opt-out readback=1, EXT source 및 합성 HV ON/OFF를 확인했습니다.
이 실행 결과는 실제 장치 쓰기나 Windows XP에서의 실행 검증이 아닙니다.

| 배포 검사 | 결과 |
| --- | --- |
| Python AST | 46개 파일 PASS |
| wheel ↔ 소스 | 17개 Python 모듈 byte 단위 일치 |
| EXE SHA-256 | `376c27ce51aa35973eb67a3f9e8f6d5b8c5000b9b7c391ea2e2a28a596a99e6a` |
| wheel SHA-256 | `692d9639fb174445513c0ab08dd380dff3fe1775ab7ea758984460e990e6c8a3` |

## 근거 파일

배포본의 `docs/validation_1_3_1`에 수집한 자료를 기준으로 합니다.

| 자료 | 내용 |
| --- | --- |
| `full_tests_131.json` | 304개 오프라인 자동 시험 결과 |
| `gui_source_empower_131.json`, `gui_source_external_131.json` | 소스 simulator GUI 결과 |
| `gui_exe_empower_131.json`, `gui_exe_external_131.json`, `gui_exe_runs_131.json` | EXE 두 모드 결과·실행 파일 hash |
| `package_source_checks.json` | AST·wheel 모듈 일치 검사와 wheel hash |
| `aggregate_final.json` | 10개 실기 조회 단계의 독립 TX 검증·분모·오류·HV 집계 |
| 각 probe/scheduler 디렉터리의 raw TX/RX와 summary | 개별 명령과 시간, 응답 원문 |
| `capability_parser_replay_131_final_units.json` | 60개 실제 응답 replay |
| `original_hv_voltage_units.json`, `original_hv_current_units.json` | 단위 정적 분석 |
| `config_preservation.json`, `network_snapshot.json` | 설정 보존 및 종료 상태 |

기존 로그 분석과 응답 예시는 [비가동 시험 상세 보고](NON_ACTUATION_TEST_20261027_KO.md),
수정 목록은 [1.3.1 변경 사항](CHANGELOG_1_3_1.md)을 참고하십시오.
