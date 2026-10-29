# Spitfire Python Control 1.3.0 검증 결과

검증일: 2026-10-26. 원본 XP 설치 배포물을 정적으로 대조하고 Python 코드와 배포 EXE를
시뮬레이터 환경에서 검사했습니다. 원본 EXE/installer를 실행하거나 실제 장치에 접속하지 않았습니다.
COM 포트 열기와 외부 네트워크 접근을 차단한 환경에서 수행했습니다.

## 최종 결과

| 검사 | 결과 | 근거 |
| --- | --- | --- |
| 전체 회귀 검사 | 총 260개: **250 통과, 10 건너뜀, 실패/오류 0** | `validation_1_3_0/final_tests_130.json`, `.txt` |
| Python 소스 Empower GUI | PASS | `validation_1_3_0/empower_gui_source_130.json` |
| Python 소스 External GUI | PASS | `validation_1_3_0/external_gui_source_130.json` |
| 배포 EXE Empower GUI | PASS | `validation_1_3_0/empower_gui_exe_130.json` |
| 배포 EXE External GUI | PASS | `validation_1_3_0/external_gui_exe_130.json` |
| XP 원본 명령 목록 대조 | 조회 90 + 쓰기 56 = 146개 문자열 일치 | `XP_PARITY_REVIEW_1_3_0.md` |

전체 회귀 검사에는 명령 경계, 응답 해석, 상태/alias 무효화, 시뮬레이터, GUI, scheduler,
외부 구성, 오류 매핑, 설정 저장 및 serial 자원 관리 검사가 포함됩니다.
별도의 전체 검사 과정에서 제품 코드의 hardware 접근을 허용하지 않았습니다.

## 건너뛴 10개 검사의 의미

이 실행 환경에서는 loopback UDP 자기 송신도 수신되지 않았습니다. 이에 최종 검사 wrapper가
실제 loopback packet 교환에 의존하는 10개만 건너뛰었습니다. 배포한 테스트 소스에는 이
skip을 삽입하지 않았습니다. 정확한 이름은 `final_tests_130.json`의 `skip_details`에 있습니다.

- UDP heartbeat 및 backlog: 3개
- 다른 송신자의 UDP 응답 배제: 1개
- UDP 모의 서버를 이용한 하드웨어 조회 도구: 6개

따라서 이번 결과는 해당 10개 통신 경로가 통과했다는 근거가 아닙니다. loopback UDP가 가능한
Windows 호스트에서 `run_tests.cmd` 또는 `py validate_spitfire.py offline`으로 다시 확인할 수 있습니다.
일반 테스트는 실제 장치 대신 simulator/loopback/fake serial을 사용합니다.

## GUI 및 외부 모드 검사 범위

소스와 EXE 모두 Empower 모드의 Q-switch 1,250 Hz readback 왕복 및 1,500 Hz 편집 초안
보존을 확인했습니다. Empower GUI는 1024×768 창의 7개 탭에서 잘린 컨트롤이 없었습니다.
외부 모드 GUI도 검사에서 잘린 컨트롤이 없었습니다.

외부 GUI 검사에서는 missing Empower 시나리오를 사용했습니다. 시작 시 쓰기 명령은 0개였으며,
검사 과정의 명시적 opt-out 및 EXT 설정 후 source readback 확인과 simulator HV ON/OFF를
검증했습니다. 실제 펌프 발진 상태는 계속 `unmonitored`입니다. 사용자 설정은 읽거나 저장하지 않았습니다.

외부 모드의 필수 18개 조회, fresh EXT/seed 조건, 보호 상태, opt-out/override 및 모듈 통신 오류,
명령 제출과 송신 사이의 상태 변화, 비정상·오래된 응답에 대한 거부를 회귀 검사했습니다.
이는 합성 응답에 대한 프로그램 판단 검사이며 실제 TTL/광펄스 타이밍 검사가 아닙니다.

## 빌드와 배포 무결성

Python 3.13.9 / Tk 8.6.15 / PyInstaller 6.19.0으로 Windows EXE를 만들었습니다.
소스의 선언된 최소 버전은 Python 3.10이며 이번 실행 검사는 3.13에서 했습니다.
XP 원본은 참조 자료입니다. 배포 EXE는 XP용 빌드가 아니며 XP 실행 호환성을 주장하지 않습니다.

- `dist/SpitfirePythonControl.exe` SHA-256: `945a686da85e50a27c4655fef770699b321e6dd88f662b95ab9de249b658587f`
- `release/spitfire_control-1.3.0-py3-none-any.whl` SHA-256: `725cbc703f3b4a59e13949e477bba0190407abdf5a29cce3f93c7bdfca52f61d`

배포 ZIP에는 소스·테스트·EXE·wheel·문서·의존성 license가 포함됩니다. 원본 vendor 실행 파일은
포함하지 않습니다. `SHA256SUMS.txt`는 자기 자신을 제외한 배포 파일의 SHA-256을 기록합니다.
패키징 시 Python 파일 구문, wheel 내 모듈과 소스의 바이트 일치, ZIP CRC 및 파일 해시를 확인합니다.

## 이번에 입증하지 않은 사항

- 원본의 모든 callback과 Python을 실제로 동시에 실행한 동등성
- 실제 TDG firmware의 opt-out 지원·효과 및 모든 응답 형식
- 실제 UDP/RS-232 장치 통신, 전기적 신호나 DTR/RTS의 순간 변화
- TDG/대체 펌프의 10 Hz 운전, 최소 반복률, pulse drop과 저주파 보호 동작
- 펌프 광펄스·seed·Pockels cell의 지연·지터·위상 관계

80 MHz ±1 MHz는 수정 가능한 소프트웨어 확인 기준이며, expected pump 10 Hz는 참고값입니다.
10 Hz 측정이나 광학 동기화 확인이 구현됐다는 뜻이 아닙니다. 원본 대조 근거와 남은 개선 항목은
`XP_PARITY_REVIEW_1_3_0.md`에 기록했습니다.
