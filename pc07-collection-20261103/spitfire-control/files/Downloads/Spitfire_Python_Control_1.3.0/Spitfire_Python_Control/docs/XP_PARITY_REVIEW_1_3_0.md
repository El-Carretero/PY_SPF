# XP 1.6.0 원본 대조와 1.3.0 구현 범위

제공한 XP ZIP은 **설치 배포물과 컴파일된 EXE/UIR**이며 편집 가능한 C 소스는 아닙니다.
이번 ZIP은 이전 분석 파일과 SHA-256이 같습니다. 원본 실행 파일이나 installer를 실행하지 않고
PE 문자열·심볼 주소·reply dispatch·짧은 x86 명령 블록·UIR resource를 정적으로 대조했습니다.
이 보고서는 소프트웨어 구현과 확인한 근거를 구분하며 실제 firmware나 광학 동작의 인증은 아닙니다.

## 무엇을 어느 정도 구현했는가

명령 문자열은 **90개 조회 + 56개 쓰기 = 146개**가 원본 table과 일치합니다.
이는 명령 목록의 대조 결과이며 전체 동작을 100% 복제했다는 뜻은 아닙니다.
원본과 같은 장치군을 제어하는 주요 화면·통신·readback 경로를 구현했고,
외부 펌프 운전에 필요한 별도 정책을 추가했습니다. 의미를 확인하지 못한 기능은 아래에 구분합니다.

| 영역 | 1.3.0 구현 상태 | 원본 대응·남은 제한 |
| --- | --- | --- |
| 명령 목록·packet framing | 구현 | 146개 문자열 일치, ECLIPSE UDP framing 복원. 전체 firmware 의미는 미확인 |
| 기본 통신 | 구현 | legacy remote 10.19.70.13:1024, local 1024. 주소·포트 설정 가능 |
| reply 상관관계 | 구현·보강 | peer IP/port와 command ID 확인. protocol에 요청별 sequence 번호가 없어 늦은 동일 ID 응답을 완전히 구별할 수 없음 |
| 비동기 scheduler | 구현·재설계 | worker thread, timeout, 한 번에 한 요청, 별도 heartbeat, OFF 우선. 원본 FIFO batch 구조와 동일하지 않음 |
| 설정과 readback | 구현 | 입력값 분리, write 후 재조회, pending/stale/invalid, alias 무효화. ACK를 측정값으로 사용하지 않음 |
| Empower 제어 | 구현 | 전류·Q-switch·LBO·RUN/STOP. GUI Hz/raw wire 배율 구분. 실제 firmware 동작은 실기 대조 필요 |
| TDG/HV·지연 채널 | 구현 | HV·채널·분주·mode·지연 및 복합 BWD/ENA readback. 숫자만 있는 응답에서 보호 flag를 추정하지 않음 |
| TCU·head/motor | 구현 | 온습도·TEC·motor 표시와 개별 제어. DM1 펌프 제어와 별개 |
| 오류 표시 | 1.3.0 정정 구현 | 1014 Empower, 1066 TDG, 1088 TCU, 1089 COM, 1039 BWD를 분리 |
| External Pump 구성 | 추가 구현 | Empower 전용 조회·쓰기를 제외. 실제 TDG 보호·타이밍 readback을 유지 |
| 외부 타이밍 기준 | 추가 구현 | seed 기대값·편차, 펌프 참고 반복률, 명시적 EXT 설정. 광학 phase lock이나 actual pump Hz는 측정하지 않음 |
| 출력 명령 제한 | 추가 구현 | opt-out·보호·EXT·seed 범위를 제출/송신 시 확인. 자동 재시작 없음 |
| Programmer | 구현·제한 | 원본 명령 ID 접근, 인자 검증. 외부 모드의 전역·raw·우회 명령 차단 |
| Raw RS-232 | 별도 서비스 기능 | 확인된 원본 주 통신은 UDP. serial은 독립 기능이며 외부 모드에서는 차단 |
| 원본 TCP server | 의도적으로 미구현 | 원본 port 1001 remote server를 새 앱에서 열지 않음 |
| 원본 자동 INT→EXT 초기화 | 의도적으로 미구현 | 1067 handler의 자동 2030 쓰기를 startup에 복사하지 않음 |
| simulator·검증 도구 | 구현 | fault·미지원·missing Empower·timing 합성 시나리오. 실제 TTL·광학·firmware 모델 아님 |
| 제조사 서비스 비공개 의미 | 부분 복원 | 문자열과 일부 callback만 확인. 비공개 명령 의미·범위·장비별 호환성은 미검증 |
| 실제 DM1/TDG 10 Hz·광학 동기화 | 미검증 | 전기 사양·펄스 도달·지터·저반복률 동작을 실기에서 확인해야 함 |

## 오류 매핑 정정의 근거

**1.2.0에서 1014를 TDG·TCU까지 포함한 공유 오류로 취급한 해석을 폐기합니다.**
UIR resource의 저장 control ID가 실제 runtime ID보다 1 작은데, 이전 매핑이 이 보정을 하지 않았습니다.
예를 들어 runtime INFO 34는 stored 33 `HV_ON`, runtime INFO 7은 stored 6 `OSC_ST`입니다.
같은 방식으로 fault 화면을 대조하면 1014 decoder의 확인된 대상은 모두 Empower입니다.
공통 fault 화면에 여러 장치의 표시가 모여 있어도 데이터가 한 reply에서 오는 것은 아닙니다.

| 응답 | 정적 근거 | 1.3.0 처리 |
| --- | --- | --- |
| 1014 | `_decode_faults` VA `0x40a5c5`, 네 decimal `atoi` 필드 | Empower 전용. 네 번째 LBO stability scalar 전체 보존 |
| 1066 | reply `0x40cb4b`, `sscanf("%x")`; `_decode_tdg_stbh_nom` `0x410053` | TDG fault를 unsigned 32-bit hex로 해석 |
| 1039 | reply `0x40cb20`, `sscanf("%x")`; `_decode_tdg_stbh` `0x41023e` | BWD/PD 상태를 hex로 해석 |
| 1088 | `_ecu_stbh_decode_fault` `0x4099d9` | decimal TCU register의 확인된 fault bit 사용 |
| 1089 | reply `0x40c343`, decimal `atoi` | main·TDG·Empower·TCU 통신 bit 분리 |
| 1019 | `_MSB`와 `_tdg_stb_decode` | module 통신 오류 bit `0x800` 유지 |

TDG fault bit는 system `0x0800`, head `0x1000`, user `0x2000`, key `0x4000`, relay `0x8000`입니다.
BWD/PD에서 확인한 비정상 조건은 mask `0x00330000`입니다. 이 값들은 광학 위상 잠금 측정이 아닙니다.
TCU는 TEC overtemperature `0x04`, humidity latch `0x10`이 확인됐습니다.
1088은 상태 register이므로 다른 nonzero bit까지 임의의 고장으로 해석하지 않습니다.
COM은 main `0x01`, TDG `0x02`, Empower `0x04`, TCU `0x08`입니다.
Empower의 communication 표시는 1014와 1089의 근거를 함께 반영합니다.

1014에 확인되지 않은 checksum label을 임의 bit에 연결하지 않습니다.
잘못된 응답·미식별 fault 값은 정상값으로 대체하지 않으며 원문을 보존합니다.
외부 모드는 1014 조회 자체를 제외하고 Empower 표시를 N/A로 둡니다.

## 타이밍·주파수 대조

| 명령 | 원본에서 확인한 내용 | 적용 |
| --- | --- | --- |
| 2030 / 1050·1067 | `_osc_mode` `0x40e913`; oscillator sync INT/EXT | 독립 source 설정과 readback 유지 |
| 2031 / 1051 | `_trig_mode` `0x40ea14`; amplifier trigger INT/EXT | 독립 source 설정과 readback 유지 |
| 1065 | reply `0x40dd8f`; `atof` → runtime INFO 7; UIR label measured oscillator MHz | 측정 seed MHz의 근거 |
| 2046 | `_cmd_osc_to_meas` `0x4124db`; INFO 7을 `%5.2f`로 보내고 1065 재조회 | MHz 숫자를 추가 단위 배율 없이 전달 |
| 2020 / 1025 | divisor callback과 reply `0x40c4a4` | 정수 분주. 실제 firmware 허용 범위는 미확인 |
| 1010 | reply `0x40d94e`가 외부 pump rate 표시를 갱신 | 원본 표시의 출처는 Empower Q-switch telemetry |
| 1079 | reply 주소 `0x40e38a`가 handler epilogue | 실제 pump Hz decoder나 표시 의미가 없음 |
| 1024 | reply `0x40c207`가 INFO 28 internal amp rate와 계산에 사용 | 별도 measured seed 80 MHz로 간주하지 않음 |
| 1053 | reply `0x40c0ae`도 INFO 28 사용 | 1024 의미의 모호성을 유지, 이름만으로 확정하지 않음 |

원본 mode handler는 `INT`가 없으면 EXT처럼 처리하지만, 새 상태 해석은 미인식 값을
유효한 source 확인으로 사용하지 않습니다. 1067 handler가 INT가 아닌 응답 뒤에
2030 INT→2030 EXT를 보내는 경로도 확인했습니다. 재잠금 목적일 수 있으나 이는 추정이며
자동 startup 쓰기로 재현하지 않았습니다.

1.3.0 외부 타이밍 프로파일의 기본 seed 80 MHz ±1 MHz는 수정 가능한 소프트웨어 기준입니다.
expected pump 10 Hz는 참고값이며 장비가 10 Hz로 설정됐거나 측정됐음을 뜻하지 않습니다.
외부 펌프의 실제 반복률은 현재 근거로 검증할 수 없고, 광학 phase detector도 구현하지 않았습니다.
두 source가 EXT이고 seed 측정값이 범위 안에 있어도 펌프 광펄스와 seed/PC의 위상 관계는 미확인입니다.

## 외부 모드의 구현 구조

`config.py`의 transport와 pump mode는 독립적입니다. `profiles.py`가 조회·쓰기 정책을 정의하고
`controller.py`가 제출 및 실제 송신 직전에 확인합니다. GUI만 숨겨서 제한하는 구조가 아닙니다.
`state.py`는 원시 응답과 해석값·유효기간·pending·alias를 관리하며,
`external_enable_reason()`에서 알려진 readback 조건을 판단합니다.

18개 필수 조회는 `1068, 1019, 1066, 1021, 1087, 1045, 1046, 1039, 1050, 1051, 1065, 1088, 1089, 1033, 1044, 1028, 1015, 1069`입니다.
일반 polling을 꺼도 순환하고 별도의 identity heartbeat로 연결을 확인합니다.
필수 조회 간격은 2초/18을 기준으로 하며 각 응답 시간이 더해지므로 고정 실시간 감시가 아닙니다.
HV/채널 ON 등은 Empower opt-out=1, TDG fault override=0, TCU opt-out=0,
head/compressor opt-out=0, humidity override=0, TDG·TCU·head module 통신 정상, PC1/PC2 BWD·ENA,
EXT source·seed 범위와 실제 보호/통신 상태를 요구합니다.

타이밍 source·분주·내부 반복률·oscillator 기준, opt-out와 latch reset은 최근 HV OFF를 요구합니다.
`APPLY EXT SOURCES`와 `APPLY EMPOWER OPT-OUT`은 명시적 동작이며 시작 시 자동 쓰기가 없습니다.
STOP/OFF는 대기 쓰기를 취소하고 우선 처리합니다. 현재 진행 중인 reply 대기나 이미 송신된
명령을 되돌리지는 못합니다. PC 제어는 전기적 인터록이나 실제 펌프 정지 기능이 아닙니다.

## Python 안정성 검토와 반영

| 발견한 문제 | 반영한 동작 |
| --- | --- |
| 저장된 timeout·port 등의 잘못된 타입이 startup 예외로 이어짐 | 설정 전체 타입·범위·유한값 검증, 잘못된 저장 파일은 기본 simulator 설정으로 복구 |
| 동시 저장이 같은 `.tmp` 파일을 사용 | 고유 임시 파일, flush/fsync, atomic replace, 실패 시 정리와 기존 파일 보존 |
| serial handle 생성 후 DTR/RTS 설정 오류로 handle 누수 | 초기화 실패 시 local handle 닫기 |
| 포트 open 후 control line을 바꾸는 순서 | unopened handle에 DTR/RTS 적용 후 open. driver 전기 glitch 여부는 별도 |
| alias 오류 뒤 canonical readback이 계속 fresh | 관련 readback family의 유효성 무효화 |
| HV ON 중 타이밍 source 변경 가능 | source·분주·내부 반복률·oscillator 기준 변경에 fresh HV OFF를 제출/송신 시 요구 |
| `--simulator --udp` 동시 허용 | CLI 상호 배타 옵션 |
| 조회 인자로 command separator 전달 가능 | 모든 구성에서 separator/control character 거부, 1026 channel 외 조회 인자 차단 |

전체 시험 결과는 최종 `VALIDATION_1_3_0.md`가 기준입니다. 이 문서는 일부 regression 결과를
전체 통과 수로 확대하지 않으며, 1.2.0의 결과를 새 버전 결과로 사용하지 않습니다.

## 아직 검증하지 못한 부분과 개선 순서

| 항목 | 다음에 확인할 내용 |
| --- | --- |
| 실제 TDG firmware | read-only packet capture로 18개 응답, hex/decimal 형식, compound flag, opt-out 지원을 대조 |
| opt-out의 실제 영향 | 제거되는 Empower 의존성과 남는 인터록, latch·오류 반응을 해당 firmware에서 확인 |
| DM1 전기 동기 | SYNC 출력 존재·정의, TTL 전압·극성·종단·펄스폭, trigger 상실 동작 확인 |
| 10 Hz 동작 | TDG 및 펌프 최소 반복률·저주파 보호·pulse drop·BWD 반응 확인 |
| 광학 타이밍 | 실제 pump pulse/seed/PC 신호를 측정하여 지연·지터·phase 관계 확인 |
| 미확인 명령·status bit | vendor 문서나 packet evidence를 확보한 뒤 의미와 범위를 추가 |
| 동일 ID 지연 UDP reply | protocol에 sequence token이 없는 한 완전한 replay 식별 불가. 필요시 firmware/proxy 설계 검토 |
| audit log 실패 표시 | OFF를 막지 않는 현재 동작은 유지하되 log 파일 저장 실패를 운영자에게 표시하는 개선 가능 |

위 항목을 마치기 전에는 소프트웨어의 enable 조건 통과를 실제 광학 운전 검증으로 표현하지 않습니다.
시뮬레이터는 TTL이나 광펄스를 생성하지 않고, 원본 EXE의 모든 callback을 동적으로 비교한 것도 아닙니다.

## 분석 파일의 무결성과 재현 근거

| 파일 | 크기 | SHA-256 |
| --- | ---: | --- |
| 제공 XP ZIP | 12,823,803 B | `bd35c7b4ffe8bc2cb663c3914bd37217fb04f67abf8ef3730f0bfd49dd8b59d8` |
| `SPITFIRE.EXE` | 271,360 B | `8a87bcad1709f93358cba5f5588647999524ba8b481c2f38cc6cc82a96623e9b` |
| `SPITFIRE.UIR` | 152,636 B | `1c5b82a8cf528934bffffe0989a73312059b07a15fc3056df8fbeb41607bd67b` |

명령 table은 EXE file offset `0x30b70`(query), `0x315fc`(write)의 30-byte slot입니다.
`_gextHandleReceivedMsg` `0x40ba24`의 dispatch는 command 1000–1089에 대해
VA `0x40ad30 + 4 × command_id`의 DWORD를 사용합니다.
복원된 CVI symbol record는 name VA·function/data VA·flag의 12-byte 구조입니다.
완전한 disassembler에 의한 전체 함수 검증이 아니라 필요한 짧은 instruction block의 정적 대조입니다.

배포물의 `docs/xp_1_6_0_evidence/`에 `timing_findings.md`, `fault_findings.md`,
`python_stability_findings.md`, `fault_binary_evidence.json`, `reply_handler_addresses.json`을
포함했습니다. 주소·마스크·해석 한계를 추적할 수 있으며 설치 실행에 필요한 파일은 아닙니다.
원본 vendor binary·UIR·installer는 새 배포물에 포함하지 않습니다.
