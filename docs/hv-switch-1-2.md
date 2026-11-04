# Native PY_SPF 1.2 — HV ON/OFF 표시

프로젝트 패키지 버전은 **1.2.0**이다. 원본 NI GUI 리소스 버전 1.6.0 및 장치 펌웨어 버전과 구분한다.

## 변경

Timing and High Voltage 패널의 숨겨진 `HV_switch`(패널 5, 컨트롤 34)를 표시한다. 원래 위치에서는 MODE의 STANDBY 글자와 겹치므로 중앙 공간으로 이동하고 `HV ON/OFF` 라벨을 붙인다. 측정 OSC 주파수와 Divisor 표시는 함께 33픽셀 내려 간격을 확보하고, Divisor는 오른쪽으로 8픽셀 이동한다. MODE와 다른 제어의 위치·기능은 유지한다.

원본 UIR·DLL을 수정하지 않고, Native 패널을 불러온 뒤 콜백 연결 전에 표시·좌표·라벨 속성을 적용한다. Qt 미리보기의 좌표도 같은 배치를 사용한다.

## 제어 동작

기존 `HV_switch` 콜백을 그대로 사용한다. OFF는 `2016 TDG:HV:OFF`, ON은 `2017 TDG:HV:ON`이며 조작 후 `1061 TDG:HV:ON?`를 조회한다. 정기 조회 `1021`도 같은 스위치 값을 갱신한다. 스위치를 보이게 하거나 옮기는 동작만으로 HV 명령을 보내지 않는다. 접속 준비 전과 읽기 전용 모드에서는 기존 제어 차단 정책이 적용된다.

2019·1045·1046·RES12·MODE·RUN·STOP·Empower Opt-out 및 기존 폴링의 동작은 이번 변경 범위에 포함하지 않는다. 1.0.1의 Internal 10 Hz 지원은 유지한다.

## 검증

소스에서 컨트롤과 라벨의 전체 영역을 대조하고, Windows x86 Native 실행에서 실제 NI 경계를 읽어 User·Service·Factory·Programmer 표시 범위와 겹침을 검사한다. User·Service Timing 화면을 BMP로 보존해 글자와 배치를 눈으로 확인한다. 이 자동 GUI 검사는 실제 장비 소켓을 금지한 시뮬레이터에서 수행하며, HV 스위치의 실장비 ON/OFF 조작은 수행하지 않는다.

Windows 배포 검증은 설치·실행·제거 및 환경 격리 시험을 포함한다. 01번에서는 검증된 설치 파일의 해시와 설치 파일들을 대조하고, 설치된 EXE로 Native 자체 검사를 수행한다. 구체적인 결과와 해당 소스 커밋은 배포 검증 기록에 남긴다.

2026-11-05(한국 시간) 검증 결과: 로컬 시험 309개와 하위 시험 7개, Windows 설치·실행·제거·격리 검사 63개가 통과했다. 실제 NI 경계를 네 접근 등급에서 검사했고, Windows 설치본과 01번 PC 설치본의 User·Service 캡처를 각각 눈으로 검토했다. 변경한 스위치·라벨·숫자 표시의 겹침이나 잘림은 발견되지 않았다. 01번은 1.0.1에서 1.2.0으로 업그레이드했으며, 배포 파일 57개의 해시와 설정·PATH 보존을 확인했다. HV 스위치의 실장비 조작은 하지 않았다.

- [01번 설치·검증 기록](../analysis/release_1_2_pc01.json)
- [Windows 빌드·설치 검증](https://github.com/El-Carretero/PY_SPF/actions/runs/41881966179)
- [설치본 User 화면](../output/native-installer/installed-timing-user.bmp) / [Service 화면](../output/native-installer/installed-timing-service.bmp)

검증 후 일반 Native 창을 다시 띄웠다. 실장비 연결은 업그레이드 전후 모두 `OFFLINE - no live data` 상태여서, 이번 결과에는 실장비 통신 또는 HV 출력 검증을 포함하지 않는다.

## 업데이트 호환성

제품 표시명과 배포 파일명은 1.2로 바뀐다. 기존 AppId·뮤텍스와 사용자 데이터 위치 `%LOCALAPPDATA%\PY_SPF_1.0`은 유지한다. 기존 설치는 등록된 경로를 사용해 업데이트하며 기본 설치 경로도 `%LOCALAPPDATA%\Programs\Native_PY_SPF_1.0`을 유지한다. 기존 설정·데이터·로그와 다른 Python·NI 환경을 변경하지 않는다. 이전 앱의 정해진 바로가기와 비어 있는 이전 시작 메뉴 폴더만 정리한다.
