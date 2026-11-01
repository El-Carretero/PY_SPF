# 원본 재구현 1.6.0.post2

기준: `main`의 `78d3f447b1ca3dea35c5a737b75569a882bc0650` (`1.6.0.post1`).
별도 브랜치: `release/reconstruction-1.6.0-post2`.

## 변경

성공한 시작·재연결의 세 번의 identity 조회 뒤, 원본 초기 큐에서
`[1068]EMPOPTOUT?` 직전에 `[2036]EMPOPTOUT 1`을 한 번 추가합니다.
초기 요청은 43개에서 44개로 늘고, 나머지 원본 순서는 유지됩니다.

HV OFF 선행 조회, HV 상태 검사, 사용자 확인창은 없습니다. 원본 post1에도 이 검사 자체는
없었으며 External 2.0.0에서 추가한 정책을 가져오지 않았습니다.
쓰기 ACK만으로 설정을 켠 것으로 표시하지 않습니다. 원본 조회 응답이 상태와 화면을 갱신합니다.
보드가 0을 반환하면 0을 표시하며, 기존 재연결·응답 대기 동작을 사용합니다.

원본 Empower 조회·초기 쓰기(`EMP:LBOBREAK 1`)·Reset·RUN/OFF·접근 단계·수동 Opt-out ON/OFF를
유지합니다. 수동 OFF 후에는 다음 연결에서 다시 ON을 요청합니다.
External 버전의 명령 필터·PC2→PC1 시퀀스·오류 비트 마스킹은 추가하지 않았습니다.
UIR·NI DLL·명령표·응답 디코더·콜백은 post1 그대로입니다.

Windows `install.bat`은 `.venv`를 만들고 선택한 백엔드의 의존성과 앱을 설치합니다.
자동 선택은 64비트 Qt / 32비트 NI native이며, 모드와 Python 경로를 명시할 수도 있습니다.
`run_demo.bat`과 `run_native.bat`은 이 환경을 사용합니다. 설치는 앱을 실행하지 않습니다.
출력 폴더의 post1 ZIP/wheel은 post2 배포물로 교체하고, 재생성 도구와 SHA256을 제공합니다.
wheel에도 NI 런타임의 중첩 `bin/`·`fonts/` 리소스를 포함하고 원본 바이트와 대조합니다.

## 사용자 통신 로그 대조

자료: 지정된 `run-2010-10-9-20-46-32-11363` 폴더 안의 동명 하위 폴더.
이름의 2010년은 XP guest 시각이며 실제 수집 날짜로 해석하지 않습니다.
약 63.453초, 요청/응답 각각 1,073개, 쓰기 0개, 캡처 누락·잘린 프레임 0개입니다.

- 원본 프로세스 상태: `emp_optout=1`, 접근 단계 0.
- `TDG:HV:ON?` 응답은 37회 모두 1. 이미 Opt-out ON인 상태에서 HV ON 조회가 관측됩니다.
- Opt-out ON이어도 원본은 `EMP:STB?`, 전류·출력·LBO 온도 조회를 계속합니다.
  전류·출력·LBO 원문은 `-99`, EMP 상태는 `0.000000`입니다. 이 처리를 그대로 유지합니다.
- 초기화·Opt-out 쓰기/전환·Reset·RUN/STOP·HV 쓰기는 기록되지 않았습니다.
  `1068`, `2036`, `1089 COMSTATUS?`도 없습니다. 따라서 HV ON 중 Opt-out 쓰기의
  펌웨어 동작 또는 post2 실장비 운용을 이 로그로 검증했다고 해석하지 않습니다.

개인 경로·주소를 제외한 15종 요청/응답 UDP payload 표본, 첫 29개 조회 순서,
태그별 발생 횟수와 원본 JSONL/PCAP/EXE SHA256은
`analysis/optout_post2_capture.json`에 기록했습니다. 전체 원문이나 모든 변화 표본을 복제하지는 않았습니다.

오프라인 재생은 socket 생성을 금지하고 수행했습니다.
실제 컨트롤러의 15종 요청 payload 바이트 일치, 29개 폴링 순서의 순환 위치 일치,
37주기·1,073개 요청의 태그별 집계, 실제 응답 표본 15개의 파싱·디코딩을 확인했습니다.
또한 표본 15개 모두 원본 EXE x86 디코더의 결과와 일치했습니다.
결과: `analysis/optout_post2_replay_results.json`.

## 검증

- post2 회귀시험: 67 passed, 7 subtests passed.
- 기본 Opt-out: HV OFF / ON / 미조회 상태에서도 초기 쓰기, 응답 기반 표시,
  보드가 설정을 거부하는 경우, 수동 OFF와 재연결 기본 ON을 시뮬레이터로 확인.
- 원본 x86 콜백 대조 395개, 디코더 338개, 추가 디코더 23개: 총 756개 통과.
- 원본 통신 캡처 표본의 x86 디코더 추가 대조: 15개 통과.
- Linux Qt offscreen 10개 패널 렌더와 headless 데모 연결·230개 컨트롤 갱신 통과.
- Windows 11 / Python 3.13.9 x64: `install.bat qt` 신규 설치·재설치,
  pip 의존성 검사, 설치 패키지와 `run_demo.bat`의 headless 시뮬레이터 실행 통과.
  연결과 230개 컨트롤 갱신, PySide6 6.12.0 import를 확인했습니다.
  잘못된 모드 및 x64에서 native 설치 요청은 올바른 오류로 종료했습니다.
  [Windows 설치 결과](analysis/post2_windows_install.json)에 실행 결과와 배치 파일 해시를 기록했습니다.
  Windows에는 동일 Python 소스·설치 파일·GUI 명세만 전송했으며 NI DLL/UIR/이미지는 제외했습니다.
  이 확인은 Windows NI 화면·Qt 렌더 및 전체 배포 ZIP의 Windows 시험이 아닙니다.
- 최종 Linux wheel을 새 가상환경에 설치해 headless 데모를 확인하고,
  포함된 리소스 526개를 소스와 바이트 단위로 대조했습니다.

현재 변경으로 실제 장비에 명령을 보내지 않았습니다. 과거 post1의 Wine/QEMU NI 화면 시험은
`ANALYSIS.ko.md`에 보존하며 post2의 Windows NI 화면 재검증으로 합산하지 않습니다.

재현:

```sh
python -m pip install ".[qt,test,analysis]"
python -m pytest -q
python analysis/verify_optout_capture.py --native-oracle
python analysis/native_oracle.py --extended
python analysis/native_decoder_oracle.py
python analysis/native_decoder_oracle.py --extra
python tools/build_release.py
```
