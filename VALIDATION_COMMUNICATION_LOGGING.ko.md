# 영구 통신 진단 로그 검증

기준 브랜치: `feature/empower-independent`, 기준 커밋
`4c319aa7ed3a6068c86622b759535dc693c4c056`.
이전 2026-10-31 CI 기능을 보존하고 선택형 통신 로깅을 추가했다.
실제 장비와 통신하지 않았다. 모든 시험과 CI 앱 프로세스는 loopback 가드를 사용한다.

## 로컬 실행 결과

Linux x86-64, Python 3.12.14, pytest 9.2.0, PySide6/Qt 6.12.0,
`QT_QPA_PLATFORM=offscreen`.

| 검증 | 결과 |
|---|---|
| 변경 전 기준 회귀시험 | 153 passed + 71 subtests passed |
| 새 통신 로그 시험 | 21 passed |
| 변경 후 전체 회귀시험 | 174 passed + 71 subtests passed, 실패·스킵 0 |
| 설치 패키지 headless 2초 demo | 연결·컨트롤 업데이트 성공; 진단 JSONL 생성, dropped 0, oversized 0, error 없음, 정상 종료 |
| 설치 패키지 Qt offscreen 2초 demo | 8개 패널 렌더링 성공, 진단 로그 생성 |
| diff 공백 검증 | `git diff --check` 통과 |

데모 이벤트 수는 실행 시간/스케줄링에 따라 달라진다. 각 이벤트를 fsync한 것은 아니며,
로그 ON/OFF 상태의 실제 장비 지터를 측정한 결과가 아니다.

## 새 시험이 확인한 것

- 기본 OFF에서 파일이 생기지 않음; CLI 활성화·파일 크기/회전 수 범위 검증.
- UTC 시각을 뒤로 조정해도 monotonic 경과시간과 순서가 유지됨.
- byte 크기 제한·회전·backup 0/2·완전한 JSON 줄·동시 세션 파일 분리.
- 큰 레코드 생략 표시·느린 writer의 큐 포화·종료 대기 제한·누락 수 기록.
- 동일한 시뮬레이터 시나리오에서 로그 OFF/ON/파일 열기 실패/쓰기 실패/회전 실패의
  **송신 패킷 전체·기존 메모리 이벤트·화면 값·애플리케이션 상태가 동일**함.
- COMSTATUS 4→5와 기존 Fault 사유·freshness 변화 기록.
- 기존 Reset `(2049,2052,2050)`의 queue/send/ACK/readback 상관관계,
  기존 조건에 의한 차단, timeout, STOP에 의한 미전송 취소.
- startup timeout·재연결 세대·잘못된 readback 기록.
- 실제 localhost UDP에서 원문 바이트/CRLF/NUL/비ASCII,
  다른 발신자·이전 대기 응답 drain·잘못된 헤더·다중 응답 기록.
- 실제 localhost UDP에서 Controller 전체 초기화와 Reset 3단계 및 ACK 유실 시 timeout.
  시뮬레이터 보드가 받은 write는 지정된 Reset 3개뿐임.
- observer 예외가 UDP 송수신을 바꾸지 않음. send 오류는 로깅 후 기존처럼 전파됨.
- headless 프로세스 종료 후 실제 파일의 줄 수가 보고된 기록 수와 같고 session_end까지 저장됨.
- 회전 파일 CSV 병합·epoch 정밀도·원문 payload 보존·입력 파일 덮어쓰기 방지.

재현:

```sh
python -m pip install -c requirements-ci.txt ".[qt,test]"
python tools/ci_validate.py --profile portable --output artifacts/communication-check
```

JUnit, stdout/stderr, 환경 정보, headless 결과, Qt 캡처와 통신 JSONL이 지정한
artifact 폴더에 남는다. Windows x86에서는 기존 `native-boundary` 프로필이
통신 로깅 시험 21개를 추가로 실행한다. 실제 NI DLL을 로드하는 시험은 아니다.

## Windows와 실장비 범위

위 표는 로컬 Linux 결과다. Windows 2022 x64/x86 및 Ubuntu 24.04
Actions의 최종 결과는 [PR #3](https://github.com/El-Carretero/PY_SPF/pull/3) 본문/Checks에 실행 링크와 함께 별도로 기록한다. 기존 브랜치의
이전 Windows CI 성공을 이 변경의 검증으로 대신하지 않는다.

다음 항목은 이 작업의 자동시험으로 확인할 수 없고 아직 실제 검증하지 않았다.

- 07 PC의 실제 Windows 설치·사용자 계정 권한·백신/보안 소프트웨어·디스크 동작.
- Native NI GUI/DLL을 실제로 띄운 상태에서의 로그 기록 및 종료.
- XP 원본 프로그램과 새 Python 로그를 실제 Wireshark 캡처에 맞춰 비교하는 현장 시험.
- 실제 NIC/장비의 UDP 손실·장시간 부하·강제 종료/전원 장애에서의 저장 보존.
- 실제 레이저 명령·HV·광출력·타이밍/지터. 이 작업에서는 실제 장비에 명령을 보내지 않았다.

새 기능은 별도 PR에서 검토하며 기존 배포 ZIP/wheel은 재발행하지 않았다.
사용법과 프로토콜 식별 한계는 [통신 진단 로그 안내](COMMUNICATION_LOGGING.ko.md)에 있다.

첫 Actions 실행 #4에서 Windows x64·Ubuntu는 통과했고, Windows x86의 localhost 시험
종료 단계에서 UDP 상대 소켓을 먼저 닫아 시험 서버에 WSAECONNRESET(10054)이 발생했다.
시험 서버를 먼저 종료하도록 teardown을 수정했다. 장비 transport의 동작은 변경하지 않았다.
Windows x86 headless artifact는 실제 5,556줄과 보고된 기록 수가 일치했고 session_end까지
저장되었음을 확인했다. 이후 CI는 headless/Qt 실제 파일의 종료 레코드도 검사한다.
