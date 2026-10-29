# Empower 독립형 동작과 호환성

이 문서는 `feature/empower-independent`의 실행 동작을 설명합니다.
기존 GUI 재구현의 TDG·온도 제어·모터·TCP 기능을 바탕으로, Empower 장치와 상태에 대한 의존을 제거합니다.
원본 리소스와 명령 카탈로그는 분석 근거로 보관하며, 실제 실행에는 External 전용 정책·상태 모델을 사용합니다.

## Empower 제외 범위

| 경로 | External 동작 |
|---|---|
| 시작·재연결·주기 조회 | 보드·TDG·ECU·Head 조회만 수행. Empower 상태·전류·출력·버전·비밀 설정을 조회하지 않음 |
| Empower 명령 | `EMP:*` 조회·쓰기를 요청 접수와 송신 경계에서 차단 |
| 펌프·전역 명령 | MIL 펌프 명령, `2027 ON`, `2028 OFF`, 임의 raw 명령을 차단 |
| 오류 초기화 | `2049 ECU:RESETFAULTS → 2052 TDG:RESFAULT → 2050 RESET`. `2044 EMP:RESETFAULTS` 제외 |
| 보드 구성 | `1068 EMPOPTOUT?` 조회와 명시적 `2036 EMPOPTOUT 1` 적용 유지. opt-out을 0으로 되돌리는 쓰기는 차단 |
| 화면 | Empower Setup/Service 및 해당 상태·출력·Fault 표시 제거. 접근 단계가 바뀌어도 다시 표시하지 않음 |
| 연결·준비 상태 | Empower 통신 불능 비트가 남아 있어도 다른 장치 응답을 갱신. 실제 TDG·ECU·Head 고장과 미확인 상태는 유지 |

`EMPOPTOUT`은 Empower 장치에 보내는 명령이 아니라 Spitfire 보드의 구성 명령입니다.
연결이나 시작 조회는 이 값을 자동으로 쓰지 않습니다. 사용자가 HV OFF의 현재 조회값을 확인한 뒤
**Apply external pump opt-out**으로 적용하며, 송신 전에도 조건을 확인합니다.
장비가 이 구성을 지원하지 않거나 조회값이 미확인이라면 출력 준비 완료로 취급하지 않습니다.

## PC RUN / PC STOP

메인 화면의 PC RUN은 3초 연속 누르기로 시작합니다. 버튼을 떠나거나 포커스를 잃거나 누르기를 해제하면 취소됩니다.
실행에는 opt-out, 통신·보호·타이밍 상태의 현재값, Device HV ON, 양수의 측정 HV1/HV2,
정상 Key interlock과 PC1·PC2 OFF가 필요합니다. 누락·유효하지 않은 응답과 오래된 값은 허용 근거로 쓰지 않습니다.

동작 순서는 다음과 같습니다.

```text
PC RUN → PC2 ON 요청 → PC2 ON 조회 확인 → PC1 ON 요청 → PC1 ON 조회 확인
```

응답 수신 또는 쓰기 ACK만으로 출력 적용을 확정하지 않습니다.
중간 확인이 실패하면 다음 ON을 취소하고 PC1·PC2 OFF를 요청합니다.
상태는 채널 조회로 확인하며 실제 광출력이나 외부 펌프 동기 측정값이 아닙니다.

PC STOP과 Esc는 진행 중 RUN 및 아직 보내지 않은 ON을 취소하고 두 PC OFF를 우선 요청합니다.
첫 채널의 응답 유실·실패 때문에 두 번째 OFF를 생략하지 않습니다.
이미 송신된 요청의 처리나 응답 대기를 소급해 취소할 수는 없습니다.
PC OFF가 확인되지 않은 정리 상태는 재연결 시에도 유지하며, 두 채널 OFF 확인 전에는 새 RUN을 허용하지 않습니다.

외부 펌프·seed·HV ON은 PC RUN에서 제어하지 않습니다. PC STOP도 외부 펌프나 HV 전원을 끄는 명령이 아닙니다.
HV OFF는 Timing and High Voltage의 별도 조작입니다. 오류 초기화도 PC RUN을 자동 실행하지 않습니다.

## TCP 상태 조회

기본 `127.0.0.1:1001/TCP`에서 단일 클라이언트 조회 서버를 실행합니다.
TCP는 읽기용이며 장치 명령을 전달하지 않습니다. 외부 인터페이스 사용은 `--tcp-host`로 명시합니다.
질의는 기존처럼 대소문자를 구분하고 LF 종료를 사용합니다. 기존 CR/LF 처리 특성도 유지하므로
`FAULTS?\n`과 같은 한 질의씩 보내는 사용법을 권장합니다.

| 질의 | External 응답 |
|---|---|
| `*IDN?` | 제품을 `Spitfire External`로 표시, Empower 버전 필드는 `Empower N/A (external)` |
| `FAULTS?` | 현재 앱의 관련 Fault/미확인 상태 표시를 반영한 기존 0/1 형식 |
| `TDG_STATUS?` | 기존 PC·지연·BWD·주파수 필드 형식 유지 |
| `TEMP_STATUS?` | `nan, nan, nan, nan, -1` |
| `ECU_STATUS?` | 새 질의. `crystal_temperature_C, humidity_percent, TEC_temperature_C, TEC_enabled` |

기존 `TEMP_STATUS?`의 이름과 달리 그 네 수치 필드는 Empower 전류·LBO 온도·반복률을 참조합니다.
External에서는 이 값을 제공할 수 없으므로 필드 수를 유지하고 `nan` / `-1`로 명시합니다.
기존 클라이언트는 이를 미지원 값으로 처리해야 하며 0이나 정상 상태로 변환하면 안 됩니다.

`ECU_STATUS?` 예시:

```text
21.500, 35.250, 19.750, 1
```

순서대로 crystal 온도(1030), 습도(1031), TEC 온도(1084), TEC enabled(1028의 bit 0)입니다.
수치는 컨트롤러가 공개한 유효·최신 readback snapshot에서 읽습니다. 누락·오래된 수치는 `nan`,
TEC 상태 미확인 또는 ECU 통신 고장은 `-1`입니다. TCP worker는 GUI 객체를 읽어 이 측정값을 만들거나
자체 장치 조회를 수행하지 않습니다. `TDG_STATUS?`의 기존 필드는 GUI의 마지막 표시값이므로
그 응답 자체를 PC 출력 허용 판단에 사용하지 않습니다.

## 원본·첨부본과의 관계

- 원본 재구현은 `main`과 그 분석 자료에서 확인할 수 있습니다.
- 이전 첨부 `Spitfire Python Control 1.5.1`은 별도 Tk 앱이며, 이 브랜치는 그 앱으로 루트 코드를 대체한 버전이 아닙니다.
- 이 브랜치에는 Empower 모드를 선택하는 CLI 옵션이 없습니다. 원본의 전역 RUN/OFF 및 Empower 서비스 운용이 필요하면 원본 재구현 브랜치를 별도로 사용합니다.
- `analysis/`, 원본 리소스 및 원본 명령표의 Empower 문자열은 출처 근거입니다. 이 파일에 문자열이 남아 있다는 사실이 실제 Empower 송신을 뜻하지는 않습니다.

## 응답 확인의 범위

새 요청을 보내기 전에 수신 큐에 남아 있는 UDP 응답을 비우고, 설정된 송신자와 요청 ID가 일치하는 응답을 처리합니다.
프로토콜의 ID는 요청마다 새로 부여되는 거래 번호가 아닙니다. 따라서 새 요청을 보낸 **뒤** 도착한 이전 요청의
동일 ID 응답은 구별할 수 없는 한계가 있습니다. 조회 확인은 관측된 장치 상태를 나타내며 광출력 측정을 대신하지 않습니다.

## 검증 범위

회귀 시험은 Empower가 응답하지 않는 시뮬레이터와 loopback 통신을 사용합니다.
초기화·폴링에서의 금지 명령 부재, raw 우회 차단, 응답 일치·신선도, PC 순서·취소·실패 경로,
GUI 제한과 TCP 미지원 값 처리를 확인합니다. 관련 시험은 `tests/test_external_*.py`에 있습니다.

이번 변경으로 실제 Spitfire 장비, 펌웨어별 opt-out 동작, 외부 펌프·광학 동기,
Windows NI 화면 엔진을 검증한 것은 아닙니다. 과거 원본 코드 대조나 화면 캡처도 이번 External 동작의
실장비 검증 결과로 합산하지 않습니다.
