# 두 구현의 현재 실행 검증

검증일: **2026-10-30 (Asia/Seoul)**. 로그와 JUnit에 기록된 원래 시각은 변환하지 않았다.

기존 `PY_SPF`의 회귀 시험은 52개 모두 통과했다. 첨부 1.5.1의 제어 시험은 첫 전체 실행에서 **407개 중 406개 통과, 1개 실패**했으며, 실패한 폴링 모듈을 단독으로 다시 실행했을 때는 7개 모두 통과했다. 따라서 첨부 버전의 전체 시험이 이번 환경에서 처음부터 모두 통과했다고 해석하면 안 된다.

## 범위와 실행 환경

- 기준 구현: `PY_SPF` 커밋 `2faf7e16f410096f9fe8c987a680cb128dfb5ba2` (`spitfire-gui-reconstruction 1.6.0.post1`).
- 비교 구현: 업로드 ZIP의 `Spitfire_Python_Control_1.5.1` 소스를 별도 scratch 디렉터리에 풀어 실행했다. 저장소의 [`variants/spitfire-control-1.5.1`](../../variants/spitfire-control-1.5.1/)과 같은 첨부 소스이며 검증을 위해 소스를 수정하지 않았다.
- Linux 6.18.55, glibc 2.41, Python 3.12.14. 기준 구현은 기존 가상환경의 pytest 9.2.0, PySide6 6.12.0, Unicorn 2.1.4, pefile 2024.8.26을 사용했다.
- 첨부 구현은 scratch에 별도 가상환경을 만들고 pyserial 3.5를 설치했다. Tk GUI 시험용 Xvfb 21.1.16 Debian 패키지도 scratch에만 풀어 사용했다. 기준 구현의 Qt는 `QT_QPA_PLATFORM=offscreen`으로 실행했다.
- 첨부의 [`verification/run_tests.py`](../../variants/spitfire-control-1.5.1/verification/run_tests.py)는 실행 전에 검토했다. 이 실행기는 소켓 목적지를 loopback으로 제한하고 설정·증거 출력 경로를 분리한다. 시리얼 시험은 가짜 포트/메모리 객체를 사용했다. 기준 구현의 통신 시험 역시 localhost와 simulator를 사용한다.
- 실제 장치, Windows NI 화면 엔진, 실제 광출력·보정·인터록은 이번 시험 범위에 포함되지 않는다. 원본 EXE 대조는 x86 함수 에뮬레이션 또는 파일 내용 비교이며 원본 Windows GUI를 실행한 결과가 아니다.

## 실제 실행 결과

| 대상 | 결과 | 근거 |
|---|---|---|
| 기준 구현 pytest | **52 통과**, 실패·오류·스킵 0, 1.80초 | [로그](evidence/baseline-tests.txt), [JUnit](evidence/baseline-pytest.xml) |
| 기준 구현 원본 콜백 대조 | **395/395 통과**, 콜백 85개 | [요약](evidence/baseline-oracle-callbacks.txt) |
| 기준 구현 원본 디코더 대조 | **338/338 통과** | [요약](evidence/baseline-oracle-decoders.txt) |
| 기준 구현 추가 디코더 대조 | **23/23 통과** | [요약](evidence/baseline-oracle-extra.txt) |
| 첨부 control, 첫 전체 실행 | **406 통과 / 1 실패**, 오류·스킵 0, 총 407개, 78.067초 | [결과 JSON](evidence/control-initial-result.json), [전체 로그](evidence/control-initial-tests.txt) |
| 첨부 control, 폴링 모듈 단독 재실행 | **7/7 통과**, 실패·오류·스킵 0, 7.316초 | [결과 JSON](evidence/control-polling-rerun-result.json), [로그](evidence/control-polling-rerun-tests.txt) |
| 첨부 verifier, 전체 실행 | **209 통과 / 1 스킵**, 실패·오류 0, 총 210개, 12.652초 | [결과 JSON](evidence/verifier-result.json), [전체 로그](evidence/verifier-tests.txt) |
| 첨부 verifier, EXE 제공 후 provenance 모듈 추가 실행 | **4/4 통과**, 실패·오류·스킵 0, 0.018초 | [결과 JSON](evidence/verifier-provenance-result.json), [로그](evidence/verifier-provenance-tests.txt) |

재실행 숫자는 처음 실행한 시험과 겹친다. 7개와 4개를 별도 신규 시험 수로 합산하지 않는다. 기계가 읽을 수 있는 환경·결과 요약은 [`evidence/summary.json`](evidence/summary.json)에 있다.

### 처음 실패한 폴링 시험

실패 항목은 `test_polling.HeartbeatUdpTests.test_polling_off_keeps_real_udp_link_fresh_past_stale_limit`이다. [`tests/test_polling.py`](../../variants/spitfire-control-1.5.1/tests/test_polling.py)의 테스트용 UDP timeout은 0.15초이며, 125행에서 `self.c.state.link_fresh()`가 참인지 확인하다 실패했다. 이 시험은 자동 폴링을 꺼도 실제 loopback UDP 연결 상태가 계속 최신으로 유지되는지 검사한다.

첫 실행에서는 control·verifier 시험과 기준 구현의 기계어 대조 프로세스들이 겹쳐 실행되었다. 기계어 대조 종료 후 동일 소스를 수정하지 않고 `test_polling.py`만 다시 실행하자 실패 항목을 포함한 7개 모두 통과했다. **부하에 민감한 타이밍 문제일 가능성은 있으나 원인을 확정하지 않았다.** 실패를 숨기거나 시험 timeout을 변경하지 않았으며, 전체 407개 재실행 결과로 대체하지도 않았다.

### verifier의 선택적 EXE 검사

첫 verifier 실행의 유일한 스킵은 `SPITFIRE_XP_EXE`가 설정되지 않은 `test_user_supplied_original_binary`였다. 이어서 기준 저장소의 [`analysis/reference/SPITFIRE.EXE`](../../analysis/reference/SPITFIRE.EXE)를 제공해 해당 모듈 4개 시험을 실행했고 모두 통과했다.

이 파일은 271,360바이트이며 SHA-256은 `8a87bcad1709f93358cba5f5588647999524ba8b481c2f38cc6cc82a96623e9b`이다. 추가 검사는 파일 해시·명령 테이블 위치·명령 문자열이 verifier의 출처 기준과 일치함을 확인한다. 이것은 두 구현이 같은 원본 바이너리의 명령 표를 기준으로 삼았다는 근거이며 GUI 또는 펌웨어의 전체 동작 일치 근거는 아니다.

## 시험 구성의 차이

| 항목 | 기준 PY_SPF | 첨부 Python Control 1.5.1 |
|---|---|---|
| 응용 시험 규모 | 8개 파일, 52개 시험 메서드 | 32개 파일, 407개 시험 메서드 |
| 주요 목표 | 원본 명령·응답 형식, 콜백/스케줄링, 상태 디코딩, TCP 응답, Qt 입력/화면 복원 | 외부 펌프 프로파일, 명령 제한, 읽기 확인·stale 상태, RUN/STOP 순서, 폴링, 설정/TEC/HV, Tk GUI, 검증 도구 |
| GUI 근거 | Qt 실제 이벤트 시험과 원본 화면 캡처 대조 시험. 별도 x86 함수 대조 756개 | Tk 실제 위젯·worker·loopback verifier 연동과 1024×768 배치 시험. 원본 GUI 픽셀 일치 시험은 아님 |
| 추가 검증 구성 | 원본 EXE를 Unicorn으로 에뮬레이션하는 분석 스크립트 | 별도 `spitfire_twin_verifier` 시험 19개 파일, 210개 시험 메서드; 시나리오·통신·로그 비교·GUI·명령 출처 검사 |

시험 수는 목적과 단위가 다르므로 품질 순위나 코드 커버리지 비율로 비교할 수 없다. 첨부 폴더의 `docs/validation_*` 및 `verification/results/*`는 업로드에 이미 포함된 과거 기록이다. 이 문서의 `evidence/`만 이번 환경에서 새로 실행해 확보한 결과다.

## 재현 명령

아래는 저장소 루트에서 같은 검증을 재현하는 명령이다. `python`은 필요한 패키지를 설치한 Python 3.10 이상 가상환경을 가리키고, Linux Tk 시험에는 `xvfb-run`이 필요하다. 비교 분석 시에는 같은 패키지명과 경로가 섞이지 않도록 두 구현의 환경을 분리한다.

```sh
# 기준 구현: pytest 및 PySide6가 설치된 환경
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider --junitxml=/tmp/spitfire-baseline.xml

# 첨부 구현: pyserial이 설치된 별도 환경
PYTHONDONTWRITEBYTECODE=1 xvfb-run -a -s '-screen 0 1280x1024x24 -nolisten tcp' python variants/spitfire-control-1.5.1/verification/run_tests.py --suite control --output /tmp/spitfire-control-first
PYTHONDONTWRITEBYTECODE=1 python variants/spitfire-control-1.5.1/verification/run_tests.py --suite control --pattern test_polling.py --output /tmp/spitfire-control-polling-rerun
PYTHONDONTWRITEBYTECODE=1 xvfb-run -a -s '-screen 0 1280x1024x24 -nolisten tcp' python variants/spitfire-control-1.5.1/verification/run_tests.py --suite verifier --output /tmp/spitfire-verifier
PYTHONDONTWRITEBYTECODE=1 SPITFIRE_XP_EXE="$PWD/analysis/reference/SPITFIRE.EXE" python variants/spitfire-control-1.5.1/verification/run_tests.py --suite verifier --pattern test_catalog_provenance.py --output /tmp/spitfire-verifier-provenance
```

실제 첫 실행에서는 `/workspace/PY_SPF/.venv/bin/python`으로 기준 시험을 실행했고, 첨부 시험에는 `/workspace/scratch/spitfire-validation/venv/bin/python`과 `/workspace/scratch/spitfire-validation/xvfb/usr/bin/xvfb-run`을 사용했다. 첨부 소스의 작업 디렉터리는 `/workspace/scratch/spitfire-comparison/Spitfire_Python_Control_1.5.1`이었다. 실행 인자와 결과 폴더 대응은 위 표와 같으며 control과 verifier의 Xvfb display 번호는 각각 91과 92였다.

원본 함수 대조 스크립트는 `analysis/`의 JSON 결과 파일을 갱신하므로 원본 트리를 scratch에 복사한 뒤 복사본에서 다음 명령을 실행했다. 복사할 때 `.git`, `.venv`, 캐시, 빌드 산출물, 추가된 `variants/`를 제외하고, 복사본의 해당 기존 결과 JSON만 지운 다음 재생성했다.

```sh
# 기준 소스 복사본의 루트에서, unicorn 및 pefile이 설치된 환경
PYTHONDONTWRITEBYTECODE=1 python analysis/native_oracle.py --extended
PYTHONDONTWRITEBYTECODE=1 python analysis/native_decoder_oracle.py
PYTHONDONTWRITEBYTECODE=1 python analysis/native_decoder_oracle.py --extra
```

저장소에는 현재 실행의 요약 JSON/JUnit과 텍스트 로그만 추가했다. 가상환경, Xvfb 패키지, 전체 UDP capture, 원본 EXE의 새 복사본은 추가하지 않았다.
