# Spitfire External Control 2.0.0

이 폴더는 `feature/empower-independent` 브랜치의 배포물입니다.

- `spitfire_external_control-2.0.0-py3-none-any.whl`: 설치용 Python 패키지
- `PY_SPF_external_2.0.0.zip`: 소스·리소스·시험·분석 근거. 이전 `output/` 배포 바이너리와 가상환경은 제외
- `source_manifest.json`: 소스 ZIP에 포함된 파일별 SHA-256
- `SHA256.json`: 배포물 SHA-256

새 가상환경에서 wheel과 Qt 의존성을 설치합니다.

```sh
python -m pip install "spitfire_external_control-2.0.0-py3-none-any.whl[qt]"
spitfire-external --backend qt --demo --tcp-port 0
```

소스 ZIP은 압축 해제 후 `python -m pip install ".[qt]"`로 설치합니다.
기존 원본 재구현과 같은 `spitfire` import 경로를 사용하므로 각각 별도 가상환경을 사용합니다.
이전 1.6.0.post1 wheel/ZIP은 External 버전이 아닙니다.
검증 결과와 한계는 저장소 루트의 [VALIDATION_EXTERNAL.ko.md](../../VALIDATION_EXTERNAL.ko.md)에 있습니다.
