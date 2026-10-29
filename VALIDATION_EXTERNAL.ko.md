# External Control 2.0.0 검증 기록

검증일: 2026-10-30 (Asia/Seoul). 기준은 원본 재구현 커밋 `2faf7e16f410096f9fe8c987a680cb128dfb5ba2`이며,
이번 브랜치는 Empower 독립형 동작을 추가한 `spitfire-external-control` 2.0.0이다.

## 결과

| 검증 | 결과 |
|---|---|
| 전체 Python/Qt 회귀 시험 | **141개 통과**, 세부 subtest **71개 통과**, 실패·스킵 없음 |
| Empower 미응답 시작·폴링 | 연결·TDG/ECU/Head 상태 갱신 성공, 초기 자동 쓰기 0개 |
| 송신 정책 | EMP/MIL, 전역 ON/OFF, raw·구분자 삽입, 보호 해제 경로 차단 |
| PC 제어 | 3초 누르기, PC2 ON 조회 후 PC1 ON, STOP 취소·두 OFF 확인 |
| 통신 실패 | ON 응답 유실·빈 응답·불일치 시 다음 ON 차단, 첫 OFF 실패 시 두 번째 OFF 시도 |
| 접속·응답 경계 | 초기 handshake 중 STOP 즉시 우선 처리, 재연결 후 OFF 정리 유지, 타 송신자·이전 대기 패킷 배제 |
| GUI | Empower 패널·컨트롤 재노출 차단, 포커스·포인터 이탈 시 RUN 취소, 실제 Qt 입력 시험 |
| 설치 wheel | 별도 가상환경 설치 후 headless 데모 연결 성공, Qt **8개 화면** 렌더 성공 |
| 설치 wheel의 전체 조작 흐름 | 명시적 HV ON → PC2 ON → PC1 ON → Esc → PC1 OFF → PC2 OFF, 최종 두 채널 OFF 확인 |

Linux Python 3.12.14, PySide6 6.12.0, pytest 9.2.0에서 실행했다.
Qt 시험·캡처는 `QT_QPA_PLATFORM=offscreen`을 사용했다. 모든 장치 통신은 시뮬레이터 또는
실제 loopback UDP/TCP이며 실장비에 접속하지 않았다. Native 어댑터 시험은 Windows DLL을
로드하지 않는 경계 시험이다. **Windows NI GUI 실행·실장비·펌웨어·광출력·광학 동기는 미검증**이다.

현재 실행 근거:

- [전체 시험 로그](validation/external/pytest.txt) / [JUnit](validation/external/pytest.xml)
- [설치 wheel headless 결과](validation/external/wheel-headless.json)
- [설치 wheel 조작 및 송신 순서](validation/external/wheel-workflow.json)
- [설치·렌더링·패키지 일치 확인](validation/external/package-check.json)
- [Qt External 데모 화면](previews/external-main.png)
- [배포 체크섬](output/external/SHA256.json)

## 재현

소스의 전용 가상환경에서:

```sh
python -m pip install ".[qt,test]"
QT_QPA_PLATFORM=offscreen python -m pytest -q
python -m spitfire --demo --headless --duration 2 --tcp-port 0
python -m spitfire --backend qt --demo --tcp-port 0 --render-dir external-previews
```

wheel은 `pip wheel . --no-deps --no-build-isolation --wheel-dir output/external`로 만들었다.
이 명령의 빌드 환경에는 setuptools와 wheel이 필요하다. 설치 확인은 소스 디렉터리 밖에서
별도 가상환경에 wheel을 설치한 뒤 수행했다. Qt 렌더링에는 기존 검증 환경의 PySide6를 재사용하고,
`spitfire` 자체의 import 경로가 설치된 wheel 디렉터리임을 확인했다.

원본 콜백·decoder와 기존 화면 렌더러의 일부 시험은 분석 근거를 유지하기 위해 남겼다.
전체 141개가 모두 새로운 External 기능 시험이라는 의미는 아니다. 이전 원본의 756개 기계어 대조 결과는
이번 변경의 검증 횟수에 합산하지 않았다.

## 남은 동작 경계

수신 ID는 명령 번호이며 거래별 고유 번호가 아니다. 새 요청 전에 수신 큐에 있던 응답은 폐기하고
송신자·현재 요청 ID를 확인하지만, 새 요청 뒤 늦게 도착한 같은 ID의 과거 응답은 프로토콜 자체만으로
완전히 구별할 수 없다. PC 조회 확인은 실제 광출력 측정이 아니다.
정지 결과가 미확인이면 새 RUN을 차단하며, STOP을 다시 요청해 두 OFF readback을 확인해야 한다.
앱 종료 자체는 하드웨어 정지를 확인하는 동작이 아니므로 종료 전에 PC STOP 결과를 확인한다.
