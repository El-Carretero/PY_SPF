Spitfire용 VMware / Windows XP 설치 준비 도우미 v0.1.0

이 파일은 Windows PC에서 실행하는 설치 준비 도구입니다.
현재 ChatGPT 실행 환경에서 사용자 PC에 VMware나 XP를 설치한 것은 아닙니다.
도우미가 하는 일: VMware 설치 프로그램 실행(필요할 때), 새 가상머신 생성,
XP ISO 연결, VMware 실행. VMware 설치 창과 XP 설치 화면은 직접 진행합니다.

준비물
- x64 Windows 10/11 PC 및 해당 PC를 지원하는 VMware Workstation Pro 버전
- 공식 VMware Workstation Windows 설치 파일(EXE). 이미 설치했다면 불필요
- 정당하게 사용할 수 있는 Windows XP Professional SP3 32비트 설치 ISO와 제품 키
- 최대 20GiB까지 늘어날 가상 디스크를 저장할 여유 공간
설치 파일, XP ISO, 제품 키는 이 패키지에 포함되어 있지 않습니다.
XP ISO의 실제 버전, 부팅 가능 여부, 라이선스는 도우미가 판별하지 않습니다.

실행 순서
1. ZIP 전체를 로컬 폴더에 압축 해제합니다. ZIP 내부에서 바로 실행하지 마세요.
2. Run-Setup.cmd를 두 번 클릭합니다. PowerShell을 별도로 설치할 필요는 없습니다.
3. 파일 선택 창에서 XP Professional SP3 32비트 ISO를 선택합니다.
4. VMware가 없다면 공식 VMware-workstation*.exe 설치 파일을 선택합니다.
   설치 파일이 없다면 취소하면 공식 다운로드 페이지가 열립니다.
   파일을 내려받은 뒤 Run-Setup.cmd를 다시 실행하세요.
   Windows UAC와 VMware 설치 창은 직접 진행합니다.
   설치 프로그램이 재부팅을 요구하면 재부팅 후 도우미를 다시 실행하세요.
5. 새 가상머신이 생성되고 VMware 창이 열립니다.
   이동/복사 여부를 물으면 "I Copied It"을 선택합니다.
6. XP 설치 화면에서 Enter → 사용권 계약 확인 → F8을 누릅니다.
   새로 만든 약 20GB의 가상 디스크를 선택하여 파티션을 만들고
   NTFS 빠른 포맷으로 설치합니다. 실제 PC의 디스크를 연결하는 구성은 없습니다.
7. 첫 재부팅 이후에는 "Press any key to boot from CD"에서 키를 누르지 않습니다.
   지역, 이름, 제품 키 등 설치 화면의 항목을 입력하여 XP 바탕화면까지 진행합니다.
   제품 키는 XP 설치 화면에만 입력하세요. 채팅이나 도우미에는 입력하지 않습니다.
8. XP를 종료하고 VMware에서 초기 상태 스냅샷을 저장합니다.
   이후 작업은 NEXT_STEPS_KO.txt를 참고하세요.

가상머신 구성
- XP Professional 32비트, BIOS, 가상 하드웨어 버전 10
- CPU 1개 / 메모리 1GB / 빈 20GiB IDE 가상 디스크
- CD/DVD: 선택한 ISO / 네트워크: Host-only (기본 VMnet1), Vlance
- 3D 가속, USB, 공유 폴더, 복사/붙여넣기 비활성화
기본 저장 위치: 사용자 프로필의 Virtual Machines 아래 Spitfire-XP-날짜-고유번호 폴더
매번 새 VM을 만듭니다. 기존 VM이나 디스크를 덮어쓰지 않습니다.
이미 만든 VM을 계속 사용하려면 해당 폴더의 Spitfire-XP.vmx를 여세요.
XP 설치 후 ISO를 이동하려면 먼저 VMware의 CD/DVD 설정에서 연결을 해제하세요.

상태 및 오류
- setup-status.json은 도우미 실행 당시의 기록입니다. XP 설치 완료를 감지하지 않습니다.
- 종료 코드 0: VM 준비 완료 / 1: 오류 / 2: 필수 파일 미선택 / 3: 재부팅 필요
- 설치 파일/프로그램의 Windows 디지털 서명 확인에 실패하면 실행을 중단합니다.
  공식 파일과 PC 날짜를 확인하세요. 검사를 끄는 우회 방법은 제공하지 않습니다.
- VMware가 CPU 가상화 관련 오류를 표시하면 PC BIOS/UEFI의 Intel VT-x 또는
  AMD-V/SVM 설정을 확인하세요. 이 도우미가 펌웨어 설정을 변경하지는 않습니다.
- 가상 디스크 호환성이나 가상 하드웨어 오류가 발생하면 오류 문구를 확인해야 합니다.
  모든 VMware 버전에서 XP가 작동한다는 보장은 없습니다.
- 조직의 실행 제한 정책이 있는 PC에서는 해당 정책이 도우미 실행을 제한할 수 있습니다.

고급 실행(Windows PowerShell 5.1)
  .\Setup-SpitfireXP.ps1 -ValidateOnly
  .\Setup-SpitfireXP.ps1 -XpIso 'C:\ISO\WindowsXP.iso' -NoLaunch
ValidateOnly는 실행 환경과 템플릿만 검사하며 설치하지 않습니다.
NoLaunch는 VM 생성 후 VMware를 열지 않습니다. VMware가 없으면 설치 절차는 진행합니다.
Run-Setup.cmd의 ExecutionPolicy 옵션은 해당 프로세스에만 적용됩니다.

검증 범위
패키지의 디스크/설정 구조를 확인하고 PowerShell 소스를 정적으로 검토했습니다.
실제 Windows에서 PowerShell 실행, VMware 설치/부팅, XP 설치는 검증하지 못했습니다.
상세 내용: VALIDATION.txt

공식 안내
VMware Workstation:
https://www.vmware.com/products/desktop-hypervisor/workstation-and-fusion
Host-only 네트워크:
https://knowledge.broadcom.com/external/article?legacyId=1006480
