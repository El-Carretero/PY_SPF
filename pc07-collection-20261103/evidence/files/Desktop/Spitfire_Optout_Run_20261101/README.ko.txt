XP 원본 Spitfire 통신 수집 결과 — 2026-11-01

먼저 REPORT.ko.txt와 analysis/protocol-observations.txt를 읽으세요.

주요 파일
- spitfire-udp.pcap: Spitfire UDP 40,296프레임만 추출한 보기용 파일.
  보존한 프레임과 시각 레코드는 original.pcap의 바이트 그대로입니다.
- original.pcap: 전체 원본 캡처 46,666프레임. 초기 HTA 전달용 TCP 등도 포함합니다.
- original.pcapng / original1.etl / original2.etl: 원래 캡처·변환 자료.
- udp-original.jsonl: 원본 요청과 시뮬레이터 응답의 원본 hex 및 처리 내역.
- analysis/action-timeline.csv: 호스트·게스트 시각을 구분한 전체 타임라인.
- analysis/action-intervals.csv: 호스트 기준 동작별 시작·완료 구간.
- analysis/query-summary.csv: 조회별 관찰 횟수·간격.
- screens-tested.csv / controls-allowlist.csv: 실제 시험 결과와 제외 항목.
- screenshot-index.csv / screenshots/: 56개 원본 BMP와 33개 PNG의 대응.
  PNG는 원본 프로그램 창 영역을 원래 픽셀 크기로 추출했습니다. 크기 변경 없음.
  원본 BMP는 index에 적힌 p07 경로에 그대로 보존됩니다.
- received/: XP 내부 코드가 기록한 프로세스·창·상태·동작 증거.
- verification/: tcpdump와 dpkt의 실제 파일 재열기·로그 대조 결과.
- code/: XP 실행 파일, C 소스, 호스트 수집/분석/재실행 코드.
- code/tools-docs/: XP 호환 Wireshark·WinPcap 공식 출처, 버전, 검증·설치 방법.
- SHA256SUMS.txt: 이 최종 묶음의 파일 무결성 목록.
  capture-export-manifest.json은 최초 원격 내보내기 시점의 역사적 목록입니다.
  이후 보완한 분석 문서는 최종 SHA256SUMS.txt를 기준으로 확인하세요.

Wireshark에서 여는 방법
spitfire-udp.pcap 또는 original.pcap을 File > Open으로 엽니다.
전체 파일의 표시 필터: ip.addr == 10.19.70.2 && udp.port == 1024
두 파일 모두 classic PCAP 2.4 / Ethernet 형식입니다.

다시 실행하는 방법
1. p07의 관리자 PowerShell에서 이 묶음의 code 폴더로 이동합니다.
2. 원본 프로그램을 종료하고 해당 XP VM만 실행 중인 상태에서:
     .\Start-NewRun.ps1
   기본값은 Opt-out OFF이면 중단합니다.
3. 격리된 XP 사본에서 Empower Opt-out ON 변경까지 허용하는 실행만:
     .\Start-NewRun.ps1 -EnableOptOut
4. 호스트가 준비 완료를 표시하면 XP의 시작 > 실행에서 한 번 실행합니다.
     mshta http://10.19.70.13:18979/bootstrap.hta
   이후 화면 동작은 XP 내부 guest_driver.exe가 수행합니다.
5. 각 실행은 새 호스트/게스트 폴더를 사용하며 이전 증거를 덮어쓰지 않습니다.

자세한 조건·옵션: code/RERUN-README.txt 및 code/DRIVER_README.txt.
개별 XP 동작 예(새 출력 폴더를 지정):
  guest_driver.exe inventory C:\SPF_Check_01
  guest_driver.exe temperature C:\SPF_Check_02 C:\경로\host-isolation-proof.txt
proof 파일은 같은 실행의 호스트 격리 검사로 생성해야 합니다.
재실행은 Start-NewRun.ps1을 사용하세요. 다른 세션 정리 스크립트는 역사적 실행 자료입니다.

검증 범위
최종 guest_driver.exe는 실제 XP에서 사용했습니다. 파일 메뉴 종료와 마지막 SC_CLOSE 종료,
조회 화면 탐색, 연결 경고의 OK 재시도는 실제 실행 증거가 있습니다.
이번 Opt-out 전환은 사용자가 직접 수행했습니다. 수정된 자동 ON 경로의 OFF→ON 성공과
새 Start-NewRun/Run-ReadOnlyScenario 전체 무인 실행은 검증 완료로 주장하지 않습니다.
새 래퍼는 PowerShell 구문·생성 HTA 검사와 코드 검토를 통과했습니다.
메뉴가 비활성화되거나 관찰한 컨트롤 구조가 달라지면 임의 클릭 없이 중단합니다.

빌드(선택, XP에서 컴파일할 필요 없음)
Linux의 Python3 및 Zig0.13.0 환경에서:
  python3 -m pip install --target build-tools ziglang==0.13.0
  DRIVER_ZIG="$PWD/build-tools/ziglang/zig" sh build_guest_driver.sh
기본 제공 EXE는 XP SP3에서 실행 확인한 PE32, OS/subsystem5.1 파일입니다.
원본 Spitfire EXE는 수정하지 않았습니다.

p07 보존 위치
C:\Users\Fluke\Desktop\Spitfire_Optout_Run_20261101
원본 실물 제어 PC는 접근하지 않았으며, 모든 응답은 격리 시뮬레이터가 만들었습니다.
