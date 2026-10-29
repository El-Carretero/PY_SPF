> 1.4.0 변경: CLEAR FAULTS는 외부 모드에서도 EMP reset → TCU reset → TDG reset → 전역 RESET을 보냅니다.
> 아래 1.3.x의 TCU/TDG만 리셋한다는 설명은 당시의 제한이며 현재 구현에는 적용되지 않습니다.
> 원본과의 차이가 확인되어 수정한 사항입니다. 최신 동작은 README와 VALIDATION_1_4_0_KO.md를 참조하십시오.

# External Pump 모드 사용 안내 — 1.3.0

기존 Spitfire Pro TDG와 seed oscillator를 사용하고, DM1-527-20은 전용 프로그램에서
별도로 제어하는 구성입니다. 이 앱이 확인하는 것은 TDG의 전기적 상태와 readback입니다.
DM1 광출력·실제 반복률·펌프와 seed의 광학 위상 관계는 측정하지 않습니다.

> **1.2.0 정정:** 1014 `EMP:FAULT?`를 공유 오류로 설명했던 내용은 잘못되었습니다.
> 원본 UIR의 저장 번호에 1을 더해야 실제 runtime control 번호가 됩니다.
> 재대조 결과 1014의 확인된 필드는 Empower 전용입니다. 1.3.0 외부 모드는 이 조회를 제외하고
> 1066·1088·1089·1039에서 TDG·TCU·통신·BWD 상태를 각각 읽습니다.

## 첫 실행

1. 배포 ZIP 전체를 새 폴더에 풉니다. 기존 버전 폴더와 기록은 보관합니다.
2. `start_external_demo.cmd`를 실행합니다. 포함된 `dist/SpitfirePythonControl.exe`를
   우선 사용하므로 Python을 설치할 필요가 없습니다.
3. SIMULATOR와 EXTERNAL PUMP 표시를 확인합니다. Empower는 N/A이며,
   나머지 상태는 합성 장치의 응답입니다.
4. `File > External timing...`에서 기준을 확인합니다. 기본 seed는 80 MHz ±1 MHz,
   예상 펌프 반복률은 10 Hz입니다. 모두 수정 가능하며 장비 사양을 확정한 값이 아닙니다.
5. HV OFF readback을 확인한 뒤 `APPLY EXT SOURCES`를 명시적으로 실행합니다.
   oscillator sync와 amplifier trigger의 readback이 각각 EXT인지 확인합니다.
6. `APPLY EMPOWER OPT-OUT`을 명시적으로 실행하고 opt-out readback을 확인합니다.
   데모는 합성 쓰기이며, 실제 UDP 쓰기는 최신 연결 응답과 명령별 상태 조건이 필요합니다.
7. seed 측정값과 보호 readback이 갱신되면 소프트웨어의 출력 활성화 조건을 확인할 수 있습니다.
   이는 실제 광학 동기화의 성공 판정이 아닙니다.

EXE가 없는 소스 실행에는 Python 3.10 이상과 Tk가 필요합니다. 이때만
`install_windows.cmd`로 `.venv`와 pySerial을 준비하십시오.

```powershell
.\.venv\Scripts\python.exe run_spitfire.py --simulator --pump-mode external
```

`TDG / HV` 버튼은 TIMING/HV 탭을 열며 그 자체로 출력을 활성화하지 않습니다.
데모는 실제 네트워크·COM·TTL·광펄스를 생성하지 않습니다.

## 실제 TDG 연결과 타이밍 기준

1. `start_external_pump.cmd`를 실행합니다. 이 스크립트는 `--udp --pump-mode external`을 선택합니다.
2. `File > Connection Settings`에서 실제 주소와 `Transport=udp`,
   `Pump configuration=external`을 확인합니다. 기본 remote는 `10.19.70.13:1024`,
   local은 `0.0.0.0:1024`입니다. 같은 UDP 포트를 사용하는 원본 GUI는 함께 실행하지 않습니다.
3. 출력을 켜지 않고 identity, HV 및 아래 필수 readback을 확인합니다.
4. `File > External timing...`에서 실제 구성에 맞는 예상 seed 주파수와 허용 편차를 입력합니다.
   `Expected pump rate`는 기록·표시를 위한 참고값입니다. 이를 10 Hz로 저장해도 DM1이나
   TDG의 펌프 반복률을 10 Hz로 설정하지 않습니다.
5. `SAVE & RECONNECT`는 소프트웨어 기준만 저장하고 다시 연결합니다.
   저장에는 최근 HV OFF 또는 연결 해제가 필요합니다.
6. 실제 타이밍 source 변경이 필요하면 최근 HV OFF 확인 후 `APPLY EXT SOURCES`를 누릅니다.
   `[2030] TDG:OSC:MODE EXT`와 `[2031] TDG:TRIG:MODE EXT`를 보내며,
   각각 `[1050]`, `[1051]`의 readback으로 확인합니다. 두 쓰기는 원자적 작업이 아니므로
   일부만 완료되면 양쪽 readback을 다시 확인합니다.
7. opt-out이 1로 확인되지 않았다면 최근 HV OFF 상태에서 `APPLY EMPOWER OPT-OUT`을 누릅니다.
   `[2036] EMPOPTOUT 1` ACK 후 `[1068] EMPOPTOUT?`가 1인지 확인합니다.
8. 아래의 출력 활성화 조건이 모두 확인된 구성에서 개별 TDG 제어를 사용합니다.
   DM1 발진과 광학 타이밍 검증은 전용 제어기와 실제 측정으로 별도 수행합니다.

연결·모드 선택·프로파일 저장만으로 timing, opt-out, HV ON, 채널 ON, 펌프 RUN을
자동 전송하지 않습니다. 모드 변경은 최근 HV OFF 또는 연결 해제가 필요합니다.
`Connection Settings`의 `DISCONNECT`를 사용할 수 있으며 재연결 후 출력을 복원하지 않습니다.

## 출력 활성화 전 확인

HV ON, 채널 ON 및 output mode 명령은 다음 조건을 확인합니다.

- 최근 통신과 opt-out=1 readback.
- oscillator sync와 amplifier trigger의 최근 EXT readback.
- `[1065]`에서 측정한 양수·유한 seed 주파수가 설정한 범위 이내일 것.
- TDG·TCU·head module 통신이 최근 상태에서 정상이고, HV·fault override·PC1/PC2·BWD·TCU·통신 및 보호 옵션 readback이 유효할 것.
- TDG fault override=0, TCU opt-out=0, head/compressor opt-out=0, humidity override=0, PC1/PC2 복합 응답의 BWD와 ENA 활성 상태.
- TDG fault, BWD 검출·latch 오류, 확인된 TCU 오류 또는 Empower 외 통신 오류가 없을 것.

이는 **출력 명령의 소프트웨어 허용 조건**입니다. 광학 위상 잠금, 실제 펌프 반복률,
펄스 도달 시점 또는 증폭 성능의 확인 조건은 아닙니다.
필수 조회의 실패·오래된 값은 정상으로 처리하지 않습니다. 통신 손실로 대기 중 쓰기가 취소되더라도
이미 켜진 HV나 외부 펌프가 물리적으로 꺼졌음을 뜻하지 않습니다.

## 필수 readback

일반 Automatic polling을 꺼도 다음 **18개** 조회를 순환합니다. 연결 heartbeat는 별도입니다.

| ID | 조회 | 확인 내용 |
| --- | --- | --- |
| 1068 | `EMPOPTOUT?` | Empower opt-out |
| 1019 | `TDG:STB?` | TDG module 상태, decimal |
| 1066 | `TDG:STBHFLT?` | TDG fault register, hexadecimal |
| 1021 | `TDG:HV:ON?` | HV ON/OFF |
| 1087 | `TDG:FAULTOVERRIDE?` | fault override |
| 1045 | `TDG:DEL1?` | PC1 지연과 ON/OFF·BWD·ENA 복합 상태 |
| 1046 | `TDG:DEL2?` | PC2 지연과 ON/OFF·BWD·ENA 복합 상태 |
| 1039 | `TDG:STBH?` | BWD latch·검출 상태, hexadecimal |
| 1050 | `TDG:OSC:MODE?` | seed oscillator sync source |
| 1051 | `TDG:TRIG:MODE?` | amplifier trigger source |
| 1065 | `TDG:READ:OSCQUEST?` | 실제 seed oscillator 주파수, MHz |
| 1088 | `ECU:STBH?` | TCU 상태, decimal |
| 1089 | `COMSTATUS?` | 장치별 통신 상태, decimal |
| 1033 | `ECUOPTOUT?` | TCU opt-out이 0인지 확인 |
| 1044 | `ECU:HUMOVERRIDE?` | humidity override가 0인지 확인 |
| 1028 | `ECU:STB?` | TCU module 통신 상태 |
| 1015 | `HED:STB?` | head/compressor module 통신 상태 |
| 1069 | `HEDOPTOUT?` | head/compressor opt-out이 0인지 확인 |

필수 조회는 2초/18 간격을 기준으로 순환하며 각 응답 대기 시간이 더해집니다.
조회 주기는 Windows 프로그램과 응답 시간의 영향을 받습니다. 전기 인터록이나 실시간 광펄스 감시는 아닙니다.

## 오류와 상태 표시

| 출처 | 1.3.0 해석 |
| --- | --- |
| 1014 `EMP:FAULT?` | 네 decimal 필드의 Empower 오류. 외부 모드에서는 조회하지 않고 N/A 표시 |
| 1066 TDG fault | hex. 알려진 system/head/user/key/relay 비트와 미식별 nonzero 값도 오류로 유지 |
| 1088 TCU 상태 | decimal. 알려진 TEC overtemperature `0x04`, humidity latch `0x10`을 오류로 표시 |
| 1089 통신 상태 | decimal. main `0x01`, TDG `0x02`, Empower `0x04`, TCU `0x08`; 미식별 비트도 보존 |
| 1039 BWD 상태 | hex. 검출기·latch 조건 `0x00330000`을 확인 |

TDG·TCU·head module 통신은 원본 decoder의 `0x800` 오류 bit와 최근 응답으로 확인합니다.
이전 session에서 남은 TCU·head opt-out과 humidity/TDG override는 0, Empower opt-out은 1로 확인해야 합니다.

TCU 상태 register의 모든 nonzero 값을 고장으로 단정하지 않습니다. 원시값을 보존하며
확인된 비트만 의미를 부여합니다. 통신 상태의 Empower bit는 외부 구성과 opt-out 확인에
따라 제외하지만 main/TDG/TCU와 미식별 통신 비트는 남깁니다.

`FAULTS` 화면은 TDG·TCU·COM·BWD 원시 응답을 별도로 표시합니다. 확인하지 못한 값을
정상으로 꾸미지 않습니다. Empower의 checksum 표시에는 확인된 1014 매핑이 없으므로
임의 비트를 연결하지 않습니다.

`CLEAR FAULTS`는 외부 모드에서 제한된 TCU/TDG reset 경로를 사용합니다.
TCU/TDG fault reset(`[2049]`, `[2052]`)에는 HV OFF 전제조건이 없습니다.
BWD reset(`[2018]`)과 opt-out(`[2036]`)에는 최근 HV OFF가 필요합니다. 타이밍 source(`[2030]`, `[2031]`), 분주(`[2020]`),
내부 반복률(`[2032]`), oscillator 기준 갱신(`[2046]`)도 같은 조건을 요구합니다.
전역 BWD 쓰기(`[2033]`)와 보호 우회 활성화는 외부 모드에서 차단합니다.
시뮬레이터에 주입된 지속 고장도 reset만으로 없어진 것처럼 표시하지 않습니다.

## 주파수와 버튼의 의미

| 화면·명령 | 의미와 제한 |
| --- | --- |
| Measured seed / 1065 | 원본 GUI가 MHz로 표시한 seed oscillator 측정값 |
| Expected pump rate | 사용자가 입력한 참고값. actual pump rate는 미측정 |
| `TDG:OSC:FREQ?` / 1024 | 원본에서 internal amplifier rate 표시와 연결된 값. 별도 seed 측정값으로 해석하지 않음 |
| `TDG:TRIG?` / 1079 | 원본 reply handler가 값을 사용하지 않음. Hz 측정 의미를 부여하지 않음 |
| Oscillator to measured / 2046 | 1065의 MHz 숫자를 별도 단위 배율 없이 전달. 1024가 함께 갱신된다고 가정하지 않음 |
| `TDG / HV` | 제어 탭 이동 |
| `HV OFF` | TDG HV OFF 요청과 대기 중 쓰기 취소. DM1·seed 정지는 별도 |
| `APPLY EXT SOURCES` | 두 source를 EXT로 명시적 설정. HV나 펌프를 켜지 않음 |

XP 원본의 1067 초기 조회에는 INT→EXT를 자동으로 쓰는 경로가 있으나 1.3.0은 복사하지 않습니다.
그 동작의 목적·부작용은 firmware에서 확인되지 않았습니다.

## 동기화 배선의 출발점

330A Rev. A Spitfire Pro 매뉴얼의 기본 구조입니다.

| 기존 신호 | 연결 |
| --- | --- |
| 펌프 동기 | Empower SYNC OUT → TDG AMPLIFIER TRIGGER INPUT |
| Seed 동기 | Seed 지정 출력 → TDG OSCILLATOR SYNC INPUT |
| TDG 제어 | PC Ethernet ↔ TDG 10BaseT |
| Empower 통신 | TDG PWR SUPPLY COMM ↔ Empower RS-232 |

첫 대체 후보는 **DM1의 적합한 동기 출력 → TDG AMPLIFIER TRIGGER INPUT**입니다.
외부 TTL 입력 지원만으로 DM1에 필요한 동기 출력이 있다고 단정할 수 없습니다.
동기 출력이 없거나 시점이 맞지 않으면 공통 트리거 등 별도 구성이 필요합니다.

실제 연결에는 출력 단자·의미, 전압·극성·종단·펄스폭, 전기 에지와 실제 광펄스 사이의 지연·지터,
seed 주입과 Pockels cell 추출 타이밍, 트리거 상실 시 동작을 확인해야 합니다.
TDG의 10 Hz 지원 범위와 opt-out이 유지하는 보호도 실제 firmware에서 확인해야 합니다.
이 앱은 배선, DM1 trigger delay, 펌프 광펄스 또는 Pockels cell 위상을 자동 보정하지 않습니다.
분주로 증폭 출력 반복률을 낮추는 것과 펌프 반복률을 바꾸는 것은 별개입니다.

## 근거와 검증 범위

- Spitfire Pro User's Manual 0000-330A Rev. A: 3-10쪽, 4-5쪽, Figure 5-1/5-5,
  6-9쪽의 기존 제어·배선 구조. 6-13쪽의 공통 오류 화면이 단일 reply source를 뜻하지는 않습니다.
- Empower User's Manual 0000-332A Rev. A, 4-2쪽: SYNC OUT은 Q-switch에 동기화된 TTL이며
  실제 광검출기 측정값이라고 설명되지 않습니다.
- 제공된 XP 1.6.0 설치 배포물의 EXE/UIR 정적 분석:
  [명령·상태 대조 보고서](XP_PARITY_REVIEW_1_3_0.md).

제공 파일은 C 소스가 아니며 원본 binary는 실행하지 않았습니다.
소프트웨어 경로·parser·정책·합성 시나리오의 구현과 실제 장비 검증은 구분합니다.
1.3.0의 최종 시험 결과는 별도 `VALIDATION_1_3_0.md`를 확인하십시오.
이전 버전 시험 결과나 시뮬레이터 성공으로 실제 opt-out·10 Hz·광학 동기화를 주장하지 않습니다.


## 1.3.3 직접 조작과 Clear Faults

- 소프트웨어 ARM/DISARM 버튼, 상태와 전송 조건을 제거했습니다.
- 1.3.4의 Clear Faults는 최신 연결 응답과 사용자 확인 후 TCU·TDG reset만 요청합니다. HV OFF 조건은 없습니다.
- SASC 1.5.0의 빈 reset receipt는 성공 ACK가 아닙니다. 후속 reset을 취소하지 않고
  TCU health, TDG fault/current status와 COMSTATUS를 재조회합니다.
- ERR/NACK/잘못된 ACK와 통신 timeout은 계속 대기 중 쓰기를 취소합니다.
  통신 회복 후에는 새 요청을 직접 실행하며, 취소된 요청은 되살리지 않습니다.
- Fault 화면의 PC link는 네트워크 응답, Main comm는 장비 COMSTATUS bit 0x01입니다.
  Key는 TDG current/fault register bit 0x4000입니다. PC 응답이나 HV OFF만으로 이 비트를
  정상으로 바꾸지 않습니다. stale 값은 unknown/stale로 표시합니다.
- 후속 사용자 기록에서는 키를 켠 상태에 대응해 Key bit가 해제되고 HV readback이 1로
  바뀌었습니다. Main comm는 계속 5였고 Empower opt-out은 0이었습니다. 이 둘의 인과관계는
  확정하지 못했습니다. [1.3.4 검증 결과](VALIDATION_1_3_4.md)를 참조하십시오.
