Spitfire XP — USB 1회 자동시험 / 패킷 수집 v1.1

실행 방법
1. ZIP 압축을 풀어 폴더 전체를 USB에 복사합니다.
2. XP에서 평소 사용하던 원본 Spitfire가 이미 실행되고 통신 중이며,
   원본의 메인 화면만 열린 상태에서 USB 폴더의 START.cmd를 더블클릭합니다.
   시험 중 마우스/키보드 조작을 멈춥니다. 설정 창이나 서비스 창이 이미 열려
   있으면 해당 창을 자동으로 닫지 않고 이름을 기록해 중단합니다.
3. 보통 2~5분 뒤 완료 창의 '결과 폴더 열기'를 누릅니다.
4. C:\SpitfireLogs\run-... 폴더 전체를 USB에 복사합니다.
   REPORT.html을 열면 화면별 결과, 송수신 수, 주기 통신 집계를 볼 수 있습니다.
   capture\adapter-*.pcap은 Wireshark에서 바로 열 수 있습니다.

인터넷, Python, PowerShell, VMware Tools, 별도 Wireshark 설치는 필요하지 않습니다.
Windows XP SP3 32비트용입니다. 시스템 드라이브에 최소 500 MB 여유 공간이 필요합니다.
설정이나 장비 주소는 바꾸지 않습니다. 실제 NIC와 통신 상대는 패킷으로 찾습니다.
실행 파일은 먼저 시스템 드라이브의 SpitfireLogs 폴더에 복사됩니다.
드라이버가 없으면 포함된 공식 WinPcap 4.1.3 설치를 자동 진행합니다.
새 드라이버 설치에는 관리자 계정이 필요합니다. 이미 사용 가능한 WinPcap은 그대로 씁니다.
불완전하거나 호환되지 않는 기존 설치를 자동 교체하거나 삭제하지 않습니다.

시험 전 조건
- 원본 프로그램은 자동으로 시작/종료/재시작하지 않습니다.
  검증된 원본은 시작/재접속 과정에서 EMP:LBOBREAK 1 명령을 보낼 수 있기 때문입니다.
- Empower Opt-out이 이미 ON인 경우에만 화면 자동시험을 수행합니다.
  OFF이거나 상태를 읽지 못하면 변경하지 않고 캡처 및 점검 결과만 남깁니다.
- 아래 검증된 버전/리소스/창 모양과 일치해야 자동 입력합니다.
  다른 버전, 통신 경고창, 화면 밖으로 벗어난 창, 두 개의 원본 프로세스,
  여러 상대가 관찰되거나 한 방향만 기록되는 경우는 자동 입력을 중지합니다.
- 실행 중 Caps Lock/Shift/Ctrl/Alt/Windows 키를 누르지 마세요.
  원본과 창을 사용자가 동시에 조작하면 가드가 시험을 중지할 수 있습니다.

한 차례 수행할 동작
- 현재 화면, 원본 버전, Opt-out/접속/표시 모드를 읽고 기준 화면을 저장합니다.
- UDP 1024 양방향 패킷을 수집하며 초기 주기 통신을 관찰합니다.
- View: Temperature Control, Timing and High Voltage, Active Faults, Empower Setup.
- Help/About 표시.
- 메뉴 폭을 VM의 고정 픽셀 값과 비교하지 않습니다. 검증된 원본의 메뉴/항목 ID,
  콜백, 라벨과 실제 항목 경계를 읽어 확인하고, 선택 직전에 다시 검사합니다.
  항목이 다르거나 위치가 바뀌면 누르지 않고 중단합니다.
- 현재 사용자/서비스 표시 모드를 유지한 채 한 차례 실행합니다.
  이미 서비스 모드이면 확장 조회 화면을 수집합니다. 모드 전환용 문자 입력은 하지 않습니다.
  Opt-out ON + 사용자 모드에서 비활성화되는 Empower Setup은 누르지 않고 생략합니다.
- 새로 연 보조 창은 검증된 HidePanel 콜백으로 닫습니다.
  시작 때부터 보조 창이 열려 있으면 자동시험을 중단하고 그대로 둡니다.
  원본 프로그램은 계속 실행됩니다.
- 마지막 주기 통신을 저장하고 캡처를 닫은 뒤 PCAP 구조를 다시 읽어 검증합니다.

실행하지 않는 항목
Laser RUN/ON/OFF, 방출/발진, HV, 온도/전압/지연/모터/파라미터/설정 편집,
Opt-out 변경, fault reset, interlock/오류 우회, 원본 시작/종료/재시작,
재접속 경고 확인, regensvc/user 문자 입력, Escape, 공장/프로그래머 모드, 미검증 버튼.
CONTROLS.csv에 조사한 컨트롤별 정책을 기록했습니다.
화면을 보았다는 사실과 그 안의 개별 컨트롤을 실행했다는 사실은 구분됩니다.
본 버전은 검증된 표시 기능만 자동 실행하며 모든 미확인 기능을 클릭하지 않습니다.

중단과 기록의 의미
- '수집 / 자동시험 중지'는 로거와 이후 UI 입력만 중지합니다.
  레이저나 원본 프로그램을 정지시키는 비상 정지 기능이 아닙니다.
- 상태 변경 명령이 관찰되거나 캡처 오류가 생기면 이후 UI 입력을 멈춥니다.
  수신 전용 캡처는 이미 전송된 명령을 가로막을 수 없습니다.
- 기존 숫자 편집 컨트롤, 열려 있던 설정 창, 불명확한 입력 포커스는 자동 클릭을 막습니다.
  원본 내부 컨트롤 상태를 읽기 전용으로 확인하며 입력값을 강제로 확정하거나 포커스를 해제하지 않습니다.
- 시간은 XP 자체 시계의 UTC입니다. 외부 시간과 동기화했다고 주장하지 않습니다.
- 캡처 필터는 UDP port 1024입니다. 전체 PC의 모든 네트워크 트래픽을 수집하지 않습니다.
  원본 Ethernet/IP/UDP 프레임 바이트를 변경하지 않은 classic PCAP 2.4를 저장합니다.
- WinPcap이 보고한 드롭과 파일 구조/레코드 수를 검사합니다.
  운영체제 밖에서 발생한 손실까지 없다는 보증은 아닙니다.
- 통신 상대가 시뮬레이터면 응답은 시뮬레이터 응답입니다.
  응답 값만으로 실제 레이저/HV/온도/보호 동작을 확인했다고 해석하지 않습니다.

주요 결과 파일
REPORT.html             사람이 읽는 시험 결과와 실제 중단 사유/증거 링크
result.json             전체 성공/부분 수행/차단 결과와 동작별 상태
timeline.jsonl          실행기 동작의 시작/종료 UTC
capture\adapter-*.pcap  어댑터별 원본 송수신 프레임
capture\packets.jsonl   패킷 시각, 방향, 페이로드 원본 hex
capture\summary.json    송수신/태그/주기/드롭/구조 검증 결과
actions\...\*.bmp       화면 캡처
actions\...\windows-*.jsonl  창/컨트롤 조사
actions\...\original-state*.json  버전 및 읽기 전용 상태 확인
actions\...\heading-layout-*.json 메뉴 제목의 실제 글꼴과 위치 확인
actions\...\menu-layout-*.json    실제 메뉴/항목 신원과 위치 확인
driver-*.json / driver-install\...  드라이버 확인/설치 기록

원본 버전 고정
경로: C:\Program Files\Spectra-Physics\Spitfire\Spitfire.exe
Spitfire.exe SHA256:
8a87bcad1709f93358cba5f5588647999524ba8b481c2f38cc6cc82a96623e9b
SPITFIRE.UIR SHA256:
1c5b82a8cf528934bffffe0989a73312059b07a15fc3056df8fbeb41607bd67b
로드된 cvirte.dll SHA256:
d4151c53a2ecee4431ba88cd90d88db575f8ad18a6e48484501ff10a83c0db6d
다르면 클릭 좌표를 추정하지 않고 자동시험을 건너뜁니다.

코드/빌드
src/의 C 소스, runner.js, report.js, START.hta, RUN.hta를 포함합니다.
XP에서 소스를 컴파일할 필요 없이 bin/의 실행 파일을 사용합니다.
재빌드는 Linux의 Zig 0.13, Python 3, objdump로 가능합니다.
  DRIVER_ZIG=/path/to/zig sh build_ui.sh
  DRIVER_ZIG=/path/to/zig sh build_proof_publish.sh
  CAPTURE_ZIG=/path/to/zig sh src/build_passive_capture.sh
  DRIVER_ZIG=/path/to/zig sh src/build_provision.sh
모든 실행 파일은 PE32 x86이며 .NET/UCRT가 필요 없습니다.
C 런타임이 필요한 도구는 XP의 msvcrt를 사용합니다.
공식 드라이버 출처, 라이선스, 무결성 정보는 이 폴더의 provenance/라이선스 파일을 봅니다.
실제 p07 VM 검증과 아직 검증하지 않은 실물 장비 범위는 VALIDATION.txt에 구분합니다.

개발자 회귀 검사(USB 실행 시에는 필요 없음):
  node tests/test_runner.js
  node tests/test_report.js
  python3 tests/test_ui_guard.py
  python3 tests/test_focus_guard.py
  python3 tests/test_context_policy.py
  python3 tests/test_menu_guard.py
  python3 tests/test_revision_review_menu.py
  python3 tests/test_revision_review_heading.py
  python3 tests/test_proof_publisher.py
  python3 tests/verify_run.py 저장된_한_회차_결과_폴더
캡처 파서 재생 검사는 별도 기존 original.pcap 및 original.audit.json을 필요로 합니다.
  python3 src/test_capture_protocol.py /path/to/original.pcap
