이 패키지는 사전 점검 및 진단 캡처 결과입니다. 원본 Spitfire 화면 순회 시험 완료본이 아닙니다.
기존 시뮬레이터의 EMPOPTOUT? 값0을 실제 조회해, 원본 시작을 차단했습니다.

저장 위치
p07: C:\Users\Fluke\Desktop\Spitfire_Capture_20261101
XP: C:\SPFCAP_20261101b (실행파일 및 run 증빙)

재실행: p07에서 관리자 PowerShell
cd C:\Users\Fluke\Desktop\Spitfire_Capture_20261101
.\Run-Preflight.ps1

호스트 확인 및 제한된 임시 캡처/응답기가 준비되면 XP의 시작 -> 실행:
mshta http://10.19.70.13:18978/bootstrap.hta

VMware Tools 부재 때문에 이 최초 실행은 게스트에서 수동으로 필요합니다.
그 뒤 XP 내부 코드가 조사, 네트워크 가드, EMPOPTOUT? 한 번 조회, 파일 업로드를 수행합니다.
새 실행별 디렉터리를 생성합니다. 원본/기존 증빙을 덮어쓰지 않습니다.
호스트는 완료 또는 제한시간 뒤 자체 리스너, 필터, 방화벽 규칙을 정리하고 ETL을 변환합니다.
IP/VMX/브리지/ICS/포워딩/포트 소유자/원본 실행 여부가 다르면 중단합니다.
기존 응답 파일을 변경하지 않습니다. Opt-out이1이어도 이 진단 프로그램은 원본을 시작하거나 UI를 클릭하지 않습니다.

XP에서 네트워크 송신 없이 inventory만 다시 실행:
C:\SPFCAP_20261101b\guest_probe.exe inventory C:\SPFCAP_20261101b\inventory_new
출력 폴더는 없어야 합니다. 화면, 창/메뉴/컨트롤 목록, 프로세스, 네트워크, 타임라인을 저장합니다.

종료 코드: 0=점검 성공 또는 Opt-out1 읽음(원본 미실행), 20=Opt-out0/후속시험 차단,
21=응답 불명/포트 사용중 등, 22=게스트 격리실패, 23=호스트 증빙 누락, 기타=점검오류.

캡처 파일 다시 검증 (Python3, 호스트/클라우드, 추가 패키지 불필요):
python pcap_audit.py evidence\preflight.pcapng verify-new.pcap --provenance diagnostic
출력 파일이 이미 있으면 중단합니다. 진단 트래픽에 original 레이블을 붙이지 마세요.

도구 다운로드 및 검증만 실행:
.\Fetch-CaptureTools.ps1
XP 설치는 이번 작업에서 하지 않았습니다. 선택한 Pktmon 방식은 별도 설치가 필요 없습니다.

파일 안내
REPORT.ko.txt: 범위·제약·결과·출처·무결성
control_review.json, reviewed-controls.csv: 정적 허용/제외 검토; 모두 원본 UI 미실행
host_service.py: .13에만 bind하는 불변 진단 응답/파일 전송기
Prepare-Host.ps1: p07 VM/호스트 격리 가드
Run-Preflight.ps1: 재실행용 호스트 오케스트레이션(전체 재실행 검증은 미실시)
bootstrap.hta: 실제 성공 실행한 로컬 부트스트랩 래퍼
bootstrap-local.hta: 내장 게스트 HTA 코드
build_guest_probe.sh, guest_probe.c, xp_msvcrt.def: XP 실행파일 재빌드 소스
verify_guest_pe.py, guest_probe.pe-validation.json: PE32/XP DLL 정적 검증
research/: 공식 출처 조사 및 변환기 검증 메모

evidence/preflight.pcap: 실제 진단 송수신 2패킷, classic pcap
evidence/preflight.pcapng: 변경하지 않은 원본 변환 결과
evidence/preflight.audit.json: 형식/양방향/페이로드 검증
evidence/preflight.independent-dpkt.json: 독립 판독기 재열기 결과
evidence/timeline.csv: 게스트/호스트 시계를 구별한 UTC/KST 타임라인
evidence/guest-desktop.png: XP 내부 GDI 캡처(BMP 원본은 원시 증빙)
evidence/p07-raw-evidence.zip: 원본 ETL2개, 원본 BMP, 게스트 로그, 호스트 격리 증빙,
  실제 전달한 실행파일/HTA 및 공식 다운로드 무결성 기록

게스트 network.jsonl의 일부 어댑터 설명은 XP ANSI(cp949) 문자열입니다.
그 밖의 JSON 식별자/경로/시간은 ASCII 또는 UTF-8입니다. 원시 파일은 변환하지 않았습니다.
배포 ZIP에는 컴파일러와 공식 설치 실행파일은 넣지 않았습니다.
공식 설치파일은 p07 official-downloads에 있으며 스크립트로 다시 받을 수 있습니다.

소스 재빌드(Linux/클라우드, Python3와 objdump 필요; XP에서 빌드하지 않음):
python3 -m pip install --target build-tools ziglang==0.13.0
sh build_guest_probe.sh
생성된 PE 헤더/DLL 검사 결과만으로 XP 호환성을 단정하지 마세요.
제공 실행파일은 이번 XP에서 실제 inventory/preflight를 실행해 검증했습니다.
