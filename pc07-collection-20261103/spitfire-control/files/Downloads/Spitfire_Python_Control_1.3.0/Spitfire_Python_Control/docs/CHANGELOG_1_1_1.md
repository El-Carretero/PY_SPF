# 1.1.1 — 원본 대조 검토 반영

수정 근거는 제공된 Python 1.1.0 ZIP과 Spitfire GUI 1.6.0 ZIP이다.
원본 실행 파일은 정적으로 분석했으며 실제 컨트롤러에서 검증한 버전은 아니다.

## 수정 내역

| 문제 | 1.1.1 동작 |
|---|---|
| Q-switch 주파수 단위 불일치 | 일반 GUI Hz 입력을 10으로 나눠 전송하고, 비음수 PRF 조회 응답은 10배하여 Hz로 표시한다. 원문 응답은 그대로 보존한다. |
| ARM 해제 후 대기 ON 전송 | DISARM/OFF가 미전송 쓰기 명령을 취소한다. 이미 큐에서 꺼낸 명령도 세대 번호를 확인하여 차단한다. 실제 전송과 권한 확인을 같은 짧은 lock 안에서 수행한다. |
| STOP이 일반 큐 뒤에서 대기 | OFF/HV OFF/motor STOP/TEC OFF를 우선 큐로 처리하고 위험 쓰기를 취소·DISARM한다. 이미 전송된 명령과 현재 진행 중인 응답 대기는 취소할 수 없다. |
| 입력값 덮어쓰기 | 사용자 편집값과 readback을 별도 변수로 관리한다. 입력 중에는 새 응답이 와도 편집값을 유지한다. 숫자 입력 옆의 USE READBACK으로 장비 값을 다시 불러온다. |
| Delay 복합 응답 미해석 | ON/OFF, BWD/NBWD, ENA/NENA와 숫자값을 분리한다. 읽은 모드는 선택란에도 반영하며, 모르는 상태를 임의의 기본값으로 표시하지 않는다. |
| 잘못된 통신 녹색등 | 소켓을 연 상태와 정상 응답을 받은 상태를 분리한다. 모듈별 최근 status 응답과 원본의 통신 오류 mask 0x800을 사용한다. 오래된 상태는 UNKNOWN으로 표시한다. |
| 오류 ACK를 동작 성공으로 처리 | 어떤 write ACK도 HV/laser 상태를 직접 바꾸지 않는다. OK/ACK만 명령 수신 확인으로 취급하고, 오류·미확인 ACK는 경고 및 DISARM한다. write 뒤에는 대응 query를 자동 실행한다. |
| 다른 UDP 송신자 응답 수용 | 설정한 원격 IP와 포트를 모두 확인한다. 현재 요청 ID와 다른 reply도 상태에 적용하지 않는다. |

## 조작과 API

- 일반 GUI의 Q-switch 주파수는 **Hz**이다. 1,000 Hz 입력의 wire argument는 `100.00`이다.
- **Programmer console과 `LaserController.submit()`은 raw wire 단위**를 유지한다.
  여기서 `[2004]EMP:QSW:PRF 100`은 일반 GUI의 1,000 Hz와 대응한다.
- `engineering_argument()`는 GUI 값을 wire 값으로 바꾸는 명시적 함수다.
- 편집값은 해당 readback과 일치하거나 USE READBACK을 누를 때까지 유지된다.
- 연결 대상을 바꾸거나 다시 연결하면 이전 장비의 편집값·readback을 초기화한다.
- 모드/override 변경을 취소하면 즉시 동작하는 선택란은 확인된 값으로 돌아간다.
- write 이후 query는 자동 polling을 꺼 놓아도 실행한다.
- Timeout 또는 오래된 통신 상태는 자동 DISARM한다. 통신이 회복되어도 자동 ARM하지 않는다.
- 무응답 소켓에는 ARM할 수 없다. 먼저 정상 조회 응답이 있어야 한다.
- transport API `exchange()`는 `send_guard=`를 받는다. 사용자 정의 transport는
  실제 send 동작을 guard에 전달해야 하며, 응답 대기를 guard 안에서 수행하면 안 된다.

## 원본 근거

- `_slideqswprf`, `0x40AD10`: float 입력 / 10.0 → `%5.2f` → write ID 2004.
  10.0 상수의 VA는 `0x436770`이다.
- PRF reply handler, `0x40DBB6`: 정상 readback × double 10.0 (`0x436738`).
- Delay query handler, `0x40CE42`: `NBWD`, `NENA`, `OFF` 검색.
- `_decodenum`, `0x40FE1E`: 여섯 개의 선행 공백 구분 필드 뒤에서 숫자 추출.
- 모듈 status decoders: `_ecu_stb_decode`, `_mil_stb_decode`, `_tdg_stb_decode`,
  `_empower_stb_decode`에서 `MSB(status) & 8`을 통신 오류로 처리한다.
- 기존 146개 command ID/문자열은 변경하지 않았다.

## 검증 및 남은 한계

- 단위·스레드 경쟁·UDP loopback·Tk GUI 회귀 테스트를 포함한다.
- 원본 주파수 변환, DISARM/재ARM 이후 취소 유지, dequeue/send 사이 권한 회수,
  OFF 우선순위, ACK와 readback 분리, 입력 보존, 모드 동기화, 모듈 freshness를 검사한다.
- GUI 테스트는 Tk display가 있는 환경에서 실행한다. 화면 없는 환경에서는 해당 테스트가 skip된다.
- 시뮬레이터 Delay 응답은 원본 파서 구조를 검증하기 위한 **합성 fixture**이다.
  실제 장비에서 캡처한 응답이라고 간주하면 안 된다. firmware가 다른 형태를 반환하면
  raw log를 바탕으로 파서를 추가해야 한다.
- UDP는 인증되거나 암호화된 프로토콜이 아니다. 주소 검증은 다른 endpoint의 패킷 혼입을 막는다.
- 같은 endpoint/명령 ID의 지연 패킷을 새 응답과 완전히 구분할 transaction nonce는
  이 legacy wire format에 없다. 한 번에 한 명령만 보내는 제약을 유지한다.
- 실제 장비 및 Windows 단일 EXE 검증은 하지 않았다. 소프트웨어 STOP은 물리적 E-stop이 아니다.
