# Spitfire GUI 1.6.0 로깅 확인

첨부 설치본에 **데이터 로깅 기능이 있습니다.** Programmer 패널의 `Data Logging`을 On으로 켜면 `datalog.csv`에 전류와 LBO 온도를 기록합니다. 기본값은 Off이므로 프로그램 실행만으로 이 파일이 생성되지는 않습니다.

## 기록 내용과 조건

| 항목 | 확인 결과 |
|---|---|
| 스위치 | Programmer 패널 1, 컨트롤 3 (`SW_DATA_LOGGER`), 기본 Off |
| 타이머 | Main 패널 6, 컨트롤 64 (`TMR_DATA_LOGGER`), 설정 간격 1.0초 |
| 콜백 | `_tmr_Data_Logger`, 원본 주소 `0x00412e60`, 타이머 이벤트 15에서만 기록 |
| 첫 번째 열 | Empower Setup 패널 9, 컨트롤 2: `SENSED CURRENT (A)` |
| 두 번째 열 | Empower Service 패널 8, 컨트롤 15: `LBO TEMP (C)` |
| 파일 위치 | 현재 작업 폴더의 `datalog.csv` (EXE 설치 폴더와 다를 수 있음) |
| 파일 처리 | 원본 `fopen("datalog.csv", "a+")` → `fprintf` → `fclose`; 기존 내용 뒤에 추가 |
| 형식 | 두 float32 값을 소수점 두 자리로 기록: `%.2f, %.2f\n` |
| 포함하지 않는 항목 | 헤더, 시각, 날짜, 파일 회전·크기 제한 |

예를 들어 전류 12.345 A, 온도 36.789 °C는 다음 한 줄로 기록됩니다.

```csv
12.35, 36.79
```

스위치를 Off로 바꾸면 추가 기록이 멈추며 기존 파일은 유지됩니다. 콜백은 장치 연결 상태를 따로 검사하지 않고 화면의 두 값을 읽으므로, 이 파일의 존재만으로 새 측정값 수신을 보장하지 않습니다. 실제 간격은 GUI 이벤트 처리 상황에 따라 달라질 수 있습니다. 원본은 파일 열기에 실패하면 그 회차를 알림 없이 건너뜁니다.

## 첨부 설치본과의 일치 확인

첨부된 원본 설치 자료의 `DistFile.cab`을 다시 풀어 기존 저장소의 분석용 EXE와 UIR 파일을 바이트 단위로 대조했습니다. EXE 두 사본, `SPITFIRE.UIR`, `SERVER.UIR`이 모두 일치했습니다. 해시는 [원본 식별 결과](logging_source_identity.json)에 보존했습니다.

- EXE SHA-256: `8a87bcad1709f93358cba5f5588647999524ba8b481c2f38cc6cc82a96623e9b`
- 함수 근거: [디컴파일 결과](decompiled.c)의 `_tmr_Data_Logger`, [디스어셈블리](functions.json)의 같은 심볼.
- 화면 기본값·열 이름·타이머 근거: [복구한 화면 정의](../spitfire/resources/gui_spec.json).
- 바이너리 문자열 주소: 파일명 `0x00436e8c`, 모드 `0x00436f4c`, 포맷 `0x004367c8`.

`_ERRORLOG_FILE`이라는 심볼도 있지만 체크섬 오류 메시지를 만드는 버퍼로 사용됩니다. 해당 경로는 팝업을 표시하며 디스크 오류 로그를 쓰는 근거가 아닙니다. 수학 함수 `log`·`log10`도 데이터 로깅과 무관합니다.

## Python 구현과 검증

이 기능은 기존 커밋 `2faf7e1`에 이미 포함되어 있습니다. [콜백](../spitfire/callbacks.py)의 `tmr_Data_Logger`가 기록 동작을 만들고, [제어부](../spitfire/controller.py)가 파일에 추가합니다. Python의 저장 폴더는 `--data-dir`로 지정할 수 있습니다. 이 옵션 자체가 로깅 스위치를 켜지는 않습니다.

Python의 TX/RX·연결·오류 이벤트는 최대 2,000개 메모리 기록이며 별도의 영구 로그 파일에 자동 저장하지 않습니다. 파일 열기 실패 처리는 원본과 차이가 있습니다. Python 제어부는 현재 파일 시스템 예외를 호출자에게 전달합니다.

| 검증 | 결과 |
|---|---|
| [로깅 통합 시험](../tests/test_logging.py): 기본 Off, 1초 경계, 추가 기록, Off 전환, 이벤트 필터, 저장 폴더, float32 반올림, 기존 내용 보존, 네이티브 타이머 중복 방지 | 7개 통과 |
| [원본 x86 로깅 실행 대조](native_logging_oracle.py): On/Off, 값·반올림·기존 내용, 무시 이벤트, 원본 파일 열기 실패 | 14개 통과 |
| 로깅 시험을 포함한 전체 자동 시험 | 59개 통과 |

[원본 실행 대조 결과](native_logging_results.json)에는 파일명·모드·포맷·인자·호출 순서와 Python 파일 결과를 기록했습니다. 14개 중 13개는 Python과 대조했고, 파일 열기 실패 1개는 원본 동작만 검증했습니다.

재실행:

```sh
python -m pip install ".[qt,test,analysis]"
python -m pytest -q tests/test_logging.py
python analysis/native_logging_oracle.py
QT_QPA_PLATFORM=offscreen python -m pytest -q
```

원본 콜백은 Unicorn에서 실행하고 CVI 값 읽기·CRT 파일 함수를 대역으로 교체했습니다. NI CRT의 실제 숫자 포맷터와 Windows 줄바꿈 변환은 실행하지 않았으며, 논리적인 줄 내용을 비교했습니다. 실장비 측정이나 원본 Windows 전체 실행 검증은 이 확인에 포함되지 않습니다.
