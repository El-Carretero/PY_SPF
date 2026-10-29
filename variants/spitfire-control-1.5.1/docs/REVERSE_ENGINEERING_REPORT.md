# Spitfire GUI 1.6.0 분석 보고서

> **1.3.0 정정 안내:** 이 문서는 초기 정적 분석 기록입니다. UIR 저장 ID와 runtime ID의
> +1 차이로 인한 오류 매핑과 타이밍 해석을 다시 대조했습니다. `EMP:FAULT?`(1014)를
> TDG·TCU 공유 오류로 취급한 이전 설명은 폐기합니다. 현재 구현과 근거는
> [XP 대조 검토 1.3.0](XP_PARITY_REVIEW_1_3_0.md)을 기준으로 하십시오.
> 원본 파일은 편집 가능한 C 소스가 아니라 EXE/UIR 설치 배포물입니다.

## 분석 대상과 무결성

| 파일 | 크기 | SHA-256 |
|---|---:|---|
| user-supplied ZIP | — | `bd35c7b4ffe8bc2cb663c3914bd37217fb04f67abf8ef3730f0bfd49dd8b59d8` |
| `SPITFIRE.EXE` | 271,360 B | `8a87bcad1709f93358cba5f5588647999524ba8b481c2f38cc6cc82a96623e9b` |
| `SPITFIRE.UIR` | 152,636 B | `1c5b82a8cf528934bffffe0989a73312059b07a15fc3056df8fbeb41607bd67b` |
| `SERVER.UIR` | 5,946 B | `75188db518d04a27e729ca01532695c618f64b3cff49f25b6f774e8311170d55` |

ZIP은 `Spitfire.msi`, `DistFile.cab`, bootstrap installer 및 MSI runtime
installer를 포함했습니다. CAB에서 실행 파일과 UIR resource를 정적으로
추출했습니다. 원본 파일은 수정하거나 새 배포물에 포함하지 않았습니다.

## 원본 구조

- 2005년 빌드된 32-bit Windows PE
- National Instruments LabWindows/CVI runtime 사용
- embedded symbol table에서 229개 함수 이름과 주소 복원
- `SPITFIRE.UIR`에서 다음 9개 panel 확인

| Panel ID | tag | title |
|---:|---|---|
| 1 | `WdSECRETS2` | Empower Service |
| 2 | `WdHELP` | Help |
| 3 | `PROG` | Programmer |
| 4 | `WdSECRETS` | Compressor |
| 5 | `WdFAULTS` | Active Faults |
| 6 | `WdMAIN` | Spitfire |
| 7 | `WdCCU` | Temperature Control |
| 8 | `WdINFO` | Timing and High Voltage |
| 9 | `WdSETUP` | Empower Setup |

Python GUI는 중복 close/escape control과 숨겨진 access-level panel을 정리해
7개 tab으로 통합했습니다. Service tab은 별도 문구로 잠급니다.

1.1.0에서는 원본의 밝은 CVI 계측 패널, subsystem 통신등, 큰 STOP/RUN
조작부와 panel 이름을 디자인 기준으로 다시 반영했습니다. 정상 제어와
분리된 raw RS-232 점검 창은 `Ctrl+Shift+R`로 열 수 있습니다.

## 핵심 통신 발견

원본은 문자열과 global 변수에 `COM1`, `19200`, 8-N-1로 보이는 값을
설정하지만 serial open 함수를 호출하지 않습니다. 실제 경로는 다음과
같습니다.

1. `Open_Udp_Port2(0x400)`으로 local UDP 1024 bind
2. `Spectra-Physics:CMD_ECLIPSE,` header 작성
3. `[command_id]SCPI-like-command` line을 LF로 구분
4. `10.19.70.13:1024`로 최대 1,400-byte datagram 전송
5. `REPLY_ECLIPSE` header와 `<command_id>value` line 해석

원본의 두 FIFO, outstanding-reply count, 10초 오류 판정과 자동 update
sequence도 확인했습니다. 자세한 wire 예제는 `PROTOCOL.md`에 있습니다.

## 복원 범위

- Query ID 1000–1089: 90개
- Write ID 2000–2055: 56개
- 초기 ECU/MIL/TDG/Empower query sequence
- 정상 polling 및 별도 HV polling sequence
- fault update sequence
- 원본 TCP/1001 status-server command 이름 4개
- main/Empower/TDG/TCU/fault/service control tag 및 label

모든 146개 command는 `command_catalog.csv`와 `commands.py`에 있습니다.

## 구현상 의도적인 차이

- 첫 설치는 network를 열지 않는 simulator가 기본입니다.
- 실제 UDP write는 ARM phrase와 위험 동작별 확인을 요구합니다.
- STOP, motor STOP, HV OFF, TEC OFF만 disarmed 상태에서도 허용합니다.
- service 초기화 sequence에 섞여 있던 write ID 2047은 자동 재생하지
  않습니다.
- 인증 없는 TCP/1001 server는 공격 표면을 줄이기 위해 제공하지 않습니다.
- 정확성이 확인되지 않은 firmware status bit를 이름 있는 fault로 억지로
  변환하지 않고 raw 값을 보존합니다.

## 1.1.0에 포함되어 있던 검증 기록

- protocol/catalogue/controller/state/simulator/UDP/RS-232 회귀 테스트 34개
- 1,400-byte packet split 및 malformed/non-ASCII input 차단
- hardware write ARM 및 disarmed safe-off test
- deterministic set/write/readback simulator test
- package wheel build/import/CLI test
- 1440×900 및 1024×768 GUI render smoke test
- pySerial `loop://`를 통한 NUL/CR/LF 포함 raw byte 왕복 test

실제 controller는 이 환경에 없으므로 hardware-in-the-loop 검증은 수행하지
않았습니다. 최초 연결 절차는 `COMMISSIONING.md`에 분리했습니다.

## 1.1.1 수정 검증

이전 테스트 통과 기록만으로 실제 장비 호환성을 보장할 수 없다. 원본과의 추가
대조에서 Q-switch 주파수 변환 누락, 복합 Delay 응답 처리 누락 및 GUI/스케줄러
결함이 발견되었다. 1.1.1에서 수정했으며 자세한 변경·원본 근거는
`CHANGELOG_1_1_1.md`, 실행 결과는 `VALIDATION_1_1_1.txt`에 기록한다.
