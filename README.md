# PY_SPF_1.0

원본 Spectra-Physics **Spitfire GUI 1.6.0**의 NI 화면과 통신 규칙을 바탕으로 만든 Python 제어 프로그램입니다.
이 프로젝트의 배포 버전은 **1.0.0**입니다. 원본 NI GUI 1.6.0이나 장치가 응답하는 펌웨어 버전과는 별개입니다.

## Windows 설치형 EXE

[검증된 설치 파일](output/native-installer/PY_SPF_1.0_Setup_x86.exe) 또는
[Portable ZIP](output/native-installer/PY_SPF_1.0_win32_portable.zip)을 사용합니다.
Windows 10 1903 이상·Windows 11에서 Python·pip·venv를 별도로 설치하지 않고 Native GUI를 실행합니다.
앱 전용 Python·NI DLL·리소스를 포함하며 기존 Python/NI 등록, PATH, 파일 연결, 네트워크 설정을 바꾸지 않습니다.
사용자 설정·데이터·진단 기록은 `%LOCALAPPDATA%\PY_SPF_1.0`에 보관합니다.
[설치·제거 및 격리 범위](packaging/windows/README.ko.md)와
[해당 설치 파일의 검증 기록](output/native-installer/install-validation.json)을 함께 확인하세요.

아래 배치 파일 절차는 기존 소스 배포를 직접 실행할 때의 방법입니다.


Windows에서는 `PY_SPF_1.0.zip`을 풀고 다음 순서로 실행합니다.

```bat
install.bat
run_native.bat
```

설치기는 원본 NI 화면에 필요한 32비트 Python과 `.venv-native`를 준비합니다. 기존 Python 등록이
이전 폴더를 가리키면 실제 위치를 찾고, 필요한 경우 공식 서명이 확인된 설치기로 한 번 복구합니다.
설치 중에는 앱이나 장비에 접속하지 않습니다. 실행 오류는 창과 `logs/native-launch.log`에 남습니다.

장치에 쓰지 않고 조회만 하려면 `run_readonly.bat`, 장치 없는 시뮬레이터는 `run_demo.bat`을 실행합니다.
일반 모드는 시작·재연결 시 Empower Opt-out ON을 요청하며 HV OFF 확인 조건을 두지 않습니다.
읽기 전용 모드는 자동 Opt-out을 포함한 모든 장치 쓰기를 차단하고 실제 설정을 조회합니다.

실장비 UDP에는 최소 0.25초의 송신 간격을 적용하고, 대기 요청과 다른 태그·중복 응답을 구분합니다.
프로토콜에 거래 고유번호가 없어 늦은 동일 태그 응답을 완전히 식별할 수 있는 것은 아닙니다.

Native 실행은 기본으로 `logs/native/`에 응답·진행 상태와 진단 스택을 저장합니다.
`heartbeat.json`에는 프로세스·버전·루프 진행·마지막 NI 작업·통신 카운터가 있습니다.
10초 동안 메인 루프가 진행하지 않으면 스택을 남기며, 이 기록만으로 멈춤 원인을 확정하지 않습니다.

- [자세한 설치·실행](README.ko.md)
- [1.0 변경과 검증 범위](RELEASE.ko.md)
- [원본 복구의 역사적 분석](ANALYSIS.ko.md)
- [원본 NI 런타임과 리소스 출처](THIRD_PARTY_NOTICES.md)
- [전체 배포 ZIP](output/PY_SPF_1.0.zip)
- [설치용 wheel](output/spitfire_gui_reconstruction-1.0.0-py3-none-any.whl)

이번 버전은 응답 태그 상관·중복 처리와 유한한 조회 재시도·송신 간격을 보강하고,
실제 제어부의 읽기 전용 모드와 진행 진단을 추가합니다. 장시간 실장비 관측과
원본 코드 대조·시뮬레이터 시험의 범위는 릴리스 문서에서 구분합니다.

실제 후보 시험에서는 메뉴 루프와 모달 통신 경고가 폴링을 멈추는 조건을 재현했습니다.
같은 UI 스레드의 타이머와 비모달 복구로 수정한 뒤 최종 소스의 실제 Native 읽기 전용 실행을
30분 관측했고, 메뉴를 열어 둔 동안에도 조회가 이어졌습니다. 재연결·최종 조회 timeout·새 Fault 변화는
0회였습니다. 제어 쓰기와 모든 NI 모달 동작을 검증한 것은 아니며 자세한 범위는 릴리스 문서에 있습니다.
