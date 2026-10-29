# Spitfire Python Control 1.4.0 — 변경·검증 보고서

작성일: 2026-10-28 KST. 기준 소스: Spitfire Python Control 1.3.4 (저장 버전 5).
이 배포본은 Python 소스와 wheel, 검증용 Twin Verifier 사본, 시험 코드, 원시 결과를 포함한다.
구버전 EXE를 포함하거나 1.4.0으로 재표기하지 않았다. 시작 스크립트는 이번 소스를 실행한다.

## 결론

사용자가 제공한 마지막 비가동 검토 기록과 그 보고서/송수신 근거를 읽고 수정했다.
Windows 11 / Python 3.13.9에서 제품 시험 350개가 전부 통과했다(실패 0, 오류 0, 생략 0).
여기에는 실제 Tk GUI 콜백, 비동기 controller, 독립 Twin Verifier 사이의 loopback UDP 시험이 포함된다.
Verifier 자체는 210개 중 209개 통과, 선택적 원본 EXE 직접 비교 1개 생략이다.
원본 EXE는 배포하지 않았으며 해당 생략을 통과로 계산하지 않았다. 저장된 명령 표 fingerprint 검사는 통과했다.
Linux/Python 3.12 교차시험은 350개 중 288개 통과, 화면이 필요한 62개 생략이다. Windows에서 이 항목도 실행했다.

이번 작업에서 실제 장비에 명령을 보내지 않았다. 04 PC의 유선 장비 연결은 전후 모두 Disconnected로 확인했다.
시험 실행기는 loopback 이외 주소로 나가는 소켓 송신을 차단했다. 원본 XP GUI를 새로 전수 조작한 시험은 아니다.
원본에 관한 근거는 이전 실제/가상 XP 기록, 원시 패킷, 바이너리 분석이며 새 실행 시험은 Python GUI와 Verifier다.

## 수정 사항과 확인

| 항목 | 1.3.4 문제 | 1.4.0 처리와 검증 |
|---|---|---|
| External Clear Faults | 2049/2052만 전송, 2050 차단 | 두 모드 모두 2044→2049→2052→2050. External의 EMP reset만 좁게 허용하며 EMP 제어/조회 제외 정책은 유지 |
| 빈 reset 응답 | 첫 EMP reset의 빈 응답에서 후속 쓰기 취소 | 동일 ID의 빈 receipt를 timeout과 구분. 4개 모두 송신되며 명시적 오류는 여전히 실패 |
| 지연 상태 변화 | 즉시 조회만으로 늦은 해제를 놓칠 수 있음 | RESET 후 즉시 및 0.5/1.5/3.5/6초 조회. auto-poll OFF에서 3.26초 지연의 5→4 fixture 반영 |
| EXT 두 소스 | OSC만 EXT, TRIG는 INT로 남을 수 있음 | 전체 요청 preflight 후 제출. 각각의 source readback이 EXT와 일치해야 확인됨 |
| 연속 HV 설정 | 첫 빈 응답 뒤 두 번째 설정 취소 | 3.3/3.1 kV 두 명령 송신, 3300/3100 V readback 검증. 실제 HV ON을 뜻하지 않음 |
| 전류 단위 | GUI A와 wire 값이 동일 | 17 A→170.00, 170.00→17 A. 측정/설정 전류 모두 환산; 음수 sentinel 보존; Programmer raw는 환산하지 않음 |
| 완료 판정 | 제출/ACK와 적용 확인 구분 부족 | queued/sent/receipt/acknowledged/confirmed/observed/unverified/rejected/mismatch/timeout/cancelled 구분 |
| 취소 추적 | 큐에서 제거된 명령별 기록 누락 | 각 명령에 토큰과 CANCEL 기록. OFF, 연결 손실, 명시적 오류, readback 불일치/실패에 취소 사유 기록 |
| Service 숫자 표기 | 숫자 문자열 표현 차이에 취약 | 45.00과 조회 45는 수치로 비교. NaN, 4_5, 단위/여분 문자열은 확인으로 인정하지 않음 |
| UDP 이전 패킷 | 이미 대기 중인 이전 응답이 새 요청에 사용될 수 있음 | 새 요청 전 수신 버퍼 정리. 잘못된 ID/송신자/프레임 거부와 함께 시험 |
| Verifier 기준 | delay 문법/공백, 전류/HV 기본 단위 불일치 | `<1045> DELAY 1 ...`, current wire 180=18 A, HV wire 0.65=650 V로 보정 |

## 시험 범위

| 범위 | 실제 수행한 소프트웨어 시험 | 해석 범위 |
|---|---|---|
| 연결/전송 | UDP 실제 loopback, 90개 조회 슬롯 송수신, framing/ID/source 검사, timeout, request/reply loss, 이전 패킷 처리 | 펌웨어가 모든 조회를 지원한다는 뜻은 아님 |
| 설정 | 전류, PRF, pulse width/source, motor speed, 분주비, 온도, HV setpoint, OSC/TRIG, 주파수, opt-out, operation mode, monitor, 서비스 설정의 target readback | Verifier가 모델링한 설정과 통신 계약 검증 |
| 딜레이 | 채널 1~5 각각 값/ON/OFF/BWD/NBWD/ENA/NENA 변경 후 baseline 복귀 | 물리 펄스의 시간·게이팅 성능은 제외 |
| Faults | 원본 bit mapping, unknown/stale/invalid, KEY/EMP 유지, MAIN만 5→4, 네 reset의 전송 순서 | 실제 MAIN 비트 생성 원인이나 필수 reset 단일 명령은 아직 분리 확정하지 않음 |
| GUI | Windows 실제 Tk에서 두 모드, Clear Faults, EXT 소스, 전류 A/raw 구분, 편집값 유지, 레이아웃, 단축키와 설정창 회귀 | 가상 XP 마우스 입력 문제의 해결을 주장하지 않음 |
| 중단/복구 | OFF 우선, 대기 writes 취소, dequeued command generation 무효화, 자동 쓰기 재전송 없음, readback deadline | 이미 전송한 명령을 취소/되돌릴 수 있다는 뜻은 아님 |
| 반복 시험 | 40 ms 응답 지연에서 6종 설정 ×20회=120 writes, 각 readback 확인, 미완료 watch/queue 잔류 없음 | 수일 운전 안정성이나 광학 동기 성능 시험은 아님 |
| 데이터/기타 | 기존 protocol/state/config/serial mock·loopback/로그/보호 정책 회귀시험 전체 | 실제 serial 장치나 레이저 출력 시험 제외 |

## 완료 상태를 읽는 방법

- `confirmed` / 설정 조회 일치: 지원되는 readback이 요청값과 일치함. 실제 광 출력/전압 계측을 대신하지 않는다.
- `observed` / 상태 재조회 완료: reset 후 해당 상태를 읽었음. 모든 fault가 해제되었다는 뜻이 아니다.
- `unverified` / 적용 미확인: 대응 readback이 없거나, 프로필에서 제외되거나, 제한 시간 내 확인하지 못함.
- `timeout`: 장치가 이미 실행했을 수도 있으므로 자동으로 같은 write를 재전송하지 않는다.
- `cancelled`: 해당 대기 명령은 전송하지 않았다. 앞선 명령의 부분 적용 여부는 원시 로그와 readback을 확인한다.

External의 EMP reset은 수신 기록까지만 남을 수 있다. 이 모드는 EMP:FAULT?를 조회하지 않기 때문이다.
전역 RESET은 fault를 제한된 기간 재조회하고 결과를 남긴다. reset이 key/interlock을 강제로 정상화하지 않는다.
Readback 수치 비교 기본 허용 오차는 relative/absolute 1e-6이다. 실장비 양자화·반올림 허용폭을 임의로 확대하지 않았다.

## 남은 제한

1. 실제 레이저 발진, HV, 모터 이동, TEC, 출력 활성화, 보호 회로, 80 MHz 동기/광펄스는 미검증이다.
2. Verifier의 일부 서비스/모션/global 명령 효과는 원래부터 모델링되지 않았다. ACK만으로 효과를 확인했다고 표시하지 않는다.
3. legacy UDP ID는 거래 번호가 아니라 명령 번호다. 새 요청 이후 도착하는 같은 ID의 아주 늦은 과거 응답은 완전히 구별할 수 없다.
4. 네 reset 중 MAIN 해제에 반드시 필요한 단일 명령은 실제 조건 분리 시험 없이는 확정하지 않았다.
5. 이 버전은 소스 배포본이다. Python/Tk가 필요하며 이전 EXE를 대신 실행하지 않는다.

## 증거·재현

- `verification/results/windows_control_release/`: 350개 시험 상세 결과와 UDP JSONL.
- `verification/results/windows_verifier_final/`: Verifier 자체 시험 결과와 1개 생략 사유.
- `verification/results/linux_control_release/`, `linux_verifier/`: 교차시험과 display 관련 생략 기록.
- `verification/results/tested_source_sha256.json`, `source_identity_check.json`: Windows에서 시험한 68개 코드/시험 파일과 배포 사본의 동일성. 제품 소스 전체 포함.
- `verification/reference/`: 이전 부분 검토, 원본 current 변환 역어셈블, 실제 XP reset 발췌, 수정 전 실패 재현 결과.
- `verification/source_changes.patch`: 1.3.4 대비 제품 소스 변경.
- `verification/run_tests.py`: 전체 시험 재실행. 설정은 임시 폴더, 네트워크는 loopback으로 제한.
- `SHA256SUMS`: 배포 파일 체크섬.

사용자 데이터, 기존 설치본과 VM 설정을 교체하지 않았다. 04 PC에는 분리된 검증 폴더만 사용했다.
