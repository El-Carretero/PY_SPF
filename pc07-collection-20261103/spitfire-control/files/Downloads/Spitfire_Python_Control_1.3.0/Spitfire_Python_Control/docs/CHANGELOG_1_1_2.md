# 1.1.2 — 자동 검증 추가

- `validate_spitfire.py`, `spitfire-validate`: offline/hardware 검증 CLI.
- `validate_windows.ps1`: Python 선택, 명시적 장비 IP, 포트/IDN 및 선택 EXE 점검 래퍼.
- 장비 검증은 기존 제어 큐와 분리. 고정 48개 query ID와 정확한 문자열만 허용하고 송신 직전 다시 검사.
- 장비 소켓은 오프라인 필수 검사 통과 후 열며, saved GUI config는 읽거나 저장하지 않음.
- 초기 HV/출력/전류 readback 이상, IDN 불일치, 연속 통신 실패 및 시간 초과 시 중단.
- read-only 검증은 OFF/RESET/CLEAR 등의 종료 명령도 보내지 않음.
- 송신 전에 trace 기록, 장비 원문 reply와 parsed value 기록, HTML/JSON 결과와 종료 코드.
- GUI 및 회귀 검사는 별도 process에서 장비 통신/COM 열기를 차단. 회귀 테스트 UDP는 loopback만 허용.
- EXE에 simulator 전용 `--self-test-report` 추가. UDP 옵션 동시 사용을 config load 전에 거부.
- Windows 빌드에 SHA-256 sidecar 생성과 build step 종료 코드 확인 추가.
- Windows UDP bind에 SO_EXCLUSIVEADDRUSE 적용하여 원본 GUI와 수신 포트 공유 차단.
- 1.1.1의 수정 사항과 146개 command catalogue는 유지.

사용법과 자동 검증의 범위는 [AUTOMATED_VALIDATION.md](AUTOMATED_VALIDATION.md)에 있습니다.
개발 환경의 검증 결과는 [VALIDATION_1_1_2.txt](VALIDATION_1_1_2.txt)에 기록합니다.
실제 Windows/하드웨어에 접속하여 검증했다는 의미는 아닙니다.
