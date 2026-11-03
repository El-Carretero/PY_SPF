# Spitfire GUI 1.6.0 Python 재구현

업로드된 Spectra-Physics Spitfire GUI 1.6.0 Windows 설치본에서 복구한 Python 제어 코드, GUI, 분석 근거와 검증 자료입니다.

**실장비 검증은 수행하지 않았으며, 원본과 모든 동작·화면이 완전히 동일하다고 인증한 결과는 아닙니다.** Windows용 화면은 원본 NI 런타임과 UIR 리소스를 사용합니다. Qt 모드는 별도의 Python GUI이며 동적 렌더링에 차이가 있습니다.

- [실행 방법과 파일 구성](README.ko.md)
- [원본 분석·동일성 검증 범위](ANALYSIS.ko.md)
- [전체 소스·분석 패키지 ZIP](output/Spitfire_Python_1_6_0.zip)
- [설치용 Python wheel](output/spitfire_gui_reconstruction-1.6.0.post1-py3-none-any.whl)
- [검증 결과 요약](analysis/validation_summary.json)
- [공급된 NI 런타임·리소스 출처](THIRD_PARTY_NOTICES.md)

## Qt 데모 실행

Python 3.10 이상에서:

```sh
python -m pip install ".[qt]"
python -m spitfire --backend qt --demo --tcp-port 0
```

`--demo`는 실장비에 연결하지 않는 개발용 시뮬레이터입니다.

## 원본 NI 화면 실행

32비트 Windows Python 3.10 이상에서:

```bat
python run_spitfire.py --backend native --demo --tcp-port 0
```

실장비 연결 설정과 원본 포트는 [실행 안내](README.ko.md)에 있습니다. NI 모드는 독립 응용 프로세스로 실행합니다.

## 검증

자동 시험 52개, 원본 x86 코드와 Python을 대조한 756개 사례가 통과했습니다. Windows NI 화면의 모의 장치 연결, 10개 패널, 4개 접근 단계, 실제 메뉴·버튼·모터 입력과 종료를 Wine/QEMU에서 확인했습니다. 검증 범위와 남은 차이는 [분석 보고서](ANALYSIS.ko.md)에 기록했습니다.

```sh
python -m pip install ".[qt,test]"
python -m pytest -q
```

원본 기계어 대조 스크립트는 `analysis/`에 있습니다. `analysis/reference/SPITFIRE.EXE`는 검증용 사본이며 Python 응용 실행 경로에서는 사용하지 않습니다.

![원본 NI 화면 엔진에서 실행한 Python 제어부](previews/native-cli.png)
