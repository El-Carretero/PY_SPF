# Native PY_SPF 1.3 Windows 설치 프로그램

`PY_SPF_1.3_Setup_x86.exe`는 현재 Windows 사용자 계정에 Native 프로그램을
설치한다. Python, Python 패키지, 원본 Native GUI 리소스와 전용 런타임이
프로그램 묶음에 포함된다. 설치할 PC에 별도로 Python을 설치하거나 venv를
만들거나 `pip`를 실행할 필요가 없고, 관리자 권한도 필요하지 않다.

이 최소 Windows 버전은 유니코드 사용자 이름과 경로를 처리하는 프로그램
전용 UTF-8 매니페스트를 지원한다. 시스템 로캘은 변경하지 않는다. 가능하면
일반적인 기본 설치 경로를 유지한다. 원본 Native 런타임은 파일 이름을 포함한
`PY_SPF.exe` 전체 경로에 UTF-8 기준 최대 258바이트 제한이 있다. 글자 수가 아닌
바이트 수 제한이다. 배포본은 Native 초기화 전에 이를 확인하며, 경로를 줄여야
하면 명확한 오류를 표시하고 중단한다. 임의로 긴 경로는 지원하지 않는다.

이 설치 파일은 Native PY_SPF 1.3을 묶어 배포한다. 설치 프로그램이 RUN,
리셋, 폴링 또는 opt-out 제어 로직을 바꾸지는 않는다.

## 설치와 실행

1. Windows 10 버전 1903(빌드 18362) 이상 또는 Windows 11에서 설치 EXE를
   실행한다.
2. 기본 설치 폴더를 유지하거나 비어 있는 새 폴더를 선택한다. 기본 경로는
   `%LOCALAPPDATA%\Programs\Native_PY_SPF_1.0`이다.
3. 설치를 마친다. 마지막 화면의 **Start Native PY_SPF** 실행 항목은
   기본적으로 선택되지 않는다.
4. 장비에 접속하지 않고 Native 화면을 확인하려면 시작 메뉴에서
   **Native PY_SPF 1.3 Demo (no equipment)**를 연다. 설정된 실장비에
   접속하려면 **Native PY_SPF 1.3**을 연다.

바탕 화면 바로가기는 선택 사항이며 기본적으로 만들지 않는다. 설치 화면은
영어이고, 설치 안내서는 영어와 한국어를 함께 제공한다.

실장비 연결에는 PC에 이미 구성된 장비, 케이블, 어댑터와 네트워크 설정을
사용한다. 설치 프로그램은 장비 검색, IP 주소 변경, 방화벽 포트 개방 또는
장비 제어 명령을 수행하지 않는다. 사용자가 Native 프로그램을 직접 열면
설정된 장비에 접속할 수 있다.

## 기존 환경과 분리되는 항목

| 항목 | 경로 또는 동작 |
|---|---|
| 프로그램과 전용 런타임 | 기본값 `%LOCALAPPDATA%\Programs\Native_PY_SPF_1.0` |
| 전용 설정 | `%LOCALAPPDATA%\PY_SPF_1.0\settings\config.sp` |
| 프로그램 데이터 | `%LOCALAPPDATA%\PY_SPF_1.0\data` |
| 세션 통신 로그 | `%LOCALAPPDATA%\PY_SPF_1.0\logs\<UTC>_<UUID>` |
| 기존 Python과 venv | 설치 대상으로 사용하거나 변경하지 않음 |
| `PATH`, 파일 연결, NI 등록 | 변경하지 않음 |
| 드라이버, 어댑터, 방화벽, 네트워크 설정 | 변경하지 않음 |

사용자 데이터는 프로그램이 실행될 때 설치 파일과 별도 위치에 만든다.
설치 프로그램은 기존 소스 폴더, `config.sp` 또는 통신 로그를 가져오거나
덮어쓰지 않는다. 실행 EXE는 함께 설치된 `_internal` 파일을 사용하므로
설치 폴더 전체를 함께 유지해야 한다. EXE 옆의 `cvirte` 리소스 폴더도 필요하다.
원본 제조업체 런타임은 시스템이나 레지스트리 경로보다 먼저 EXE 옆의
`cvirte\bin`, `cvirte\fonts`를 조회한다. bin 리소스 3개는 원본 그대로
제공한다. EXE 옆 `.ttf` 경로 2개에는 메모리 글꼴 로더임을 명시한 비글꼴
자리표시자 파일을 둔다. 실제 원본 TTF는 `_internal` 안에 변경 없이 보존하며,
NI 초기화 전에 `AddFontMemResourceEx`로 현재 프로세스에만 적재한다.
제조업체 런타임의 파일 존재 검사는 통과하지만, 자리표시자의 세션 전역 글꼴
등록 시도는 부작용 없이 실패한다. 다른 프로그램에 글꼴을 등록하지 않고,
종료 뒤 글꼴 파일 잠금이 남는 문제를 피하기 위한 구성이다. Native 자체
검사는 실제 선택된 GDI 글꼴 데이터의 해시를 원본 TTF와 비교한다.
제조업체 DLL은 수정하지 않는다.

기존 NI 프로그램이 설치돼 있어도 전용 리소스가 없거나 자리표시자가 예상
내용과 다르면 사전 검증에서 거부한다. 전용 런타임 DLL은 `_internal` 아래에
유지하며, NI 등록이나 시스템 런타임 교체는 수행하지 않는다. 포함된 타사
고지는 `_internal\THIRD_PARTY_NOTICES.md`에 보존한다.

## 업데이트와 제거

이 설치 프로그램의 업데이트는 같은 전용 AppId와 이전에 등록된 설치 경로를
사용한다. 다른 파일이 들어 있는 무관한 폴더는 설치 대상으로 거부하며, 기존
소스 폴더를 삭제하거나 새 설치 폴더로 편입하지 않는다. 업데이트나 제거 전에
이 프로그램을 직접 종료한다. 이 배포본이 실행 중이면 전용 뮤텍스로 설치와
제거를 차단한다. 설치 프로그램은 장비 제어 프로그램을 자동으로 종료하거나
재시작하지 않는다.

1.3 업데이트는 이전 AppId 등록을 확인한 뒤 1.0·1.2 계열 각각의 정해진 시작 메뉴 바로가기 2개와 바탕 화면 바로가기 1개를 정리한다. 이전 시작 메뉴 폴더는 비어 있을 때만 제거하며 다른 파일은 남긴다. 제품 표시명은 1.3으로 바뀌지만 기존 설치·설정 경로의 `1.0` 이름은 호환성을 위해 유지한다. [최신순 패치노트](https://github.com/El-Carretero/PY_SPF/blob/main/CHANGELOG.ko.md)에 버전별 변경을, [통신 확인 안내](https://github.com/El-Carretero/PY_SPF/blob/main/docs/communication-monitor.md)에 새 로그 기반 패널 사용법을 기록한다.

Windows의 **설치된 앱** 또는 **앱 및 기능**에서 제거한다. 설치 프로그램이
관리하는 프로그램 파일, 바로가기와 전용 제거 등록 정보가 삭제된다. 전용
설정, 프로그램 데이터와 세션 로그는 기본적으로 남는다. 다른 Python, venv와
프로그램은 유지된다. 제거 프로그램에는 별도 사용자 데이터 폴더를 삭제하는
명령이 없다.

## 빌드 계약

빌드 단계에서 다음 형태의 완전한 x86 PyInstaller onedir 묶음을 제공한다.

```text
packaging/windows/dist/PY_SPF/
  PY_SPF.exe
  cvirte/
    bin/cvirte.rsc
    bin/msgrte.txt
    bin/cvierror.txt
    fonts/ni7seg.ttf     # 로더 자리표시자
    fonts/nisystem.ttf  # 로더 자리표시자
  _internal/
    ... Python, 패키지, Native GUI 리소스와 전용 런타임 ...
```

`installer.iss`는 Inno Setup 6.4 이상으로 컴파일한다. 설치 파일 컴파일러는
빌드 환경의 의존성이고, 설치 대상 PC에 추가로 설치하는 프로그램이 아니다.
`PayloadDir`에는 EXE 하나가 아닌 전체 onedir 폴더의 경로를 반드시 지정한다.
컴파일할 때 전용 Python 라이브러리, Native UIR, NI 런타임·리소스와 GUI
원본 글꼴을 확인하며, EXE 옆의 bin 리소스 3개와 글꼴 자리표시자 2개도 확인한다. EXE만 있거나 파일이 부족하면 설치 파일 생성을 거부한다.
`AppVersion` 기본값은 `1.3.0`이다. `InstallerOutputDir` 기본값은
`installer.iss` 기준 `dist\installer`, 즉 저장소의
`packaging/windows/dist/installer`이다.

```powershell
& $InnoCompilerPath `
  "/DPayloadDir=$PayloadDir" `
  "/DInstallerOutputDir=$InstallerOutputDir" `
  "/DAppVersion=1.3.0" `
  "packaging\windows\installer.iss"
```

생성 파일은 `PY_SPF_1.3_Setup_x86.exe`이다. 바로가기 인수는 다음과 같다.

- Native: `--backend native`
- Demo: `--demo --tcp-port 0 --local-port 0`

설치는 선택한 프로그램 폴더 아래에 파일을 복사하고, 현재 사용자 계정의
바로가기와 Inno Setup의 전용 제거 항목만 만든다. Python 설치 프로그램,
패키지 관리자, 등록 스크립트, 공유 DLL 등록, 방화벽·어댑터 변경 명령이나
광범위한 삭제 규칙은 사용하지 않는다. 기본 설치와 무인 설치에서는 프로그램을
실행하지 않는다. 대상 PC 검증에서는 설치된 Demo와 Native GUI 리소스의
실행을 확인해야 한다. 설치 파일이 생성됐다는 사실만으로 실행 검증이 끝나는
것은 아니며, 실장비 동작 확인은 별도 시험이다.
