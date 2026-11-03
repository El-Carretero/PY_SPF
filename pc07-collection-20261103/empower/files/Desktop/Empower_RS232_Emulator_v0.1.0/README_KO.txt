Empower RS-232 Emulator 0.1.0

Empower FW 1.2 실제 캡처의 바이너리 프레임을 바탕으로 만든 요청-응답형 피어.
캡처 원문에 없는 설정 변경·시간 경과는 합성 모델이며 로그 source로 구분한다.
레이저 광출력·하드웨어 보호 회로를 모델링하지 않는다.

실행 모드

1. RS-232 피어
   Python 3.10 이상 및 pyserial 필요.
   python emulator.py --serial COM번호 --output runs/serial_test --duration 3600
   19200 baud, 8N1, 흐름 제어 없음.
   이 모드는 선택한 직렬 포트에서 명령을 받고 Empower 응답을 전송한다.
   장비별 핀 배치, null-modem/직결 배선 및 Spitfire 본체가 실제로 사용하는
   직렬 프로토콜은 이 VM 시험으로 확인되지 않았다.

2. 가상 XP Spitfire 시험
   python emulator.py --udp-bind 10.19.70.13 --client 10.19.70.2 --output runs/xp_test
   같은 폴더를 재사용하면 로그에 이어 쓰므로 매번 새 output을 사용한다.
   Start-Virtual-XP-Test.ps1은 새 실행 폴더를 자동으로 만든다.

   실제 시험 경로:
     VMware XP의 원본 SPITFIRE.EXE
       -> host-only UDP 10.19.70.13:1024
       -> 합성 SASC/TDG/TCU/Head 어댑터
       -> loopback TCP 127.0.0.1:19200 안의 Empower 바이너리 프레임
       -> Empower 에뮬레이터

   원본 Spitfire PC 프로그램은 Empower의 RS-232에 직접 접속하지 않는다.
   따라서 원본을 VM에서 시험하기 위해 합성 제어부 어댑터를 제공한다.
   어댑터의 ASCII<->바이너리 대응은 원본 PC 디코더와 Empower 캡처를 근거로
   한 구현이며 실제 SASC 펌웨어를 복구한 것이 아니다.
   실제 Spitfire 본체의 RS-232 포트와 전기적으로 연결한 시험은 별도이다.

출처
  Empower_Python_Control_v1.0.6.zip의 다음 자료:
    docs/REVIEW_CAPTURE_1_0_5.md
    tests/test_capture_regression.py
    tests/test_current_capture_regression.py
    tests/test_v105_capture_review.py
  이 패키지에는 위 자료의 실제 캡처 프레임 11개를 직접 보존한다.
  전체 JSONL 6개를 확보하거나 다시 재생했다는 의미가 아니다.
  vendor/empower의 framing.py, responses.py, commands.py는 같은 배포본에서
  가져온 원본 분석 기반 코드이다.
  spitfire_catalog.json은 PY_SPF의 원본 1.6.0 명령표에서 가져왔다.

동작
  캡처 기반: 펌웨어 0x62, STOP 상태 0x12, Q-switch 0x75,
  서비스 0x70, Reset의 불투명 응답 0x18, LBO 0x1A, 출력 0x72.
  상태 모델: 전류/반복률/펄스폭 쓰기, Q-switch 변경, RUN/COUNTDOWN/STOP,
  softstart 및 underfrequency 설정. 상태 변경은 합성임을 기록한다.
  Reset만으로 현재 Key/Communication 오류를 지우지 않는다.
  서비스 쓰기의 인증·수락 정책은 구현하지 않고 캡처의 기존 값을 유지한다.
  실제 광출력 값은 합성하지 않으며 캡처의 0 W 응답을 유지한다.
  모르는 opcode에는 응답을 만들어 주지 않는다.

기록과 종료
  output/ready.json: 피어 주소·실행 PID·검증 범위.
  output/traffic.jsonl: XP ASCII 요청·응답과 실제 처리한 바이너리 hex.
  output/summary.json: 종료 시 요청 종류별 횟수.
  output 폴더에 STOP이라는 빈 파일을 만들면 종료한다.
  가상 시험의 TCP 피어는 loopback에만 바인딩하고, UDP는 지정한 XP 주소의
  요청만 처리한다. 실제 COM 포트는 --serial로 명시할 때만 연다.

시험
  python -m unittest test_emulator -v
  POSIX 및 pyserial 설치 환경에서는 test_serial_endpoint도 실행 가능하다.
  python -m pytest test_emulator.py test_serial_endpoint.py -q
  자세한 실측 결과는 RESULT_20261030.txt 및 evidence/에 기록한다.
