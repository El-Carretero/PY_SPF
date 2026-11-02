# Legacy — 이전 버전 보관함

현재 유지하는 버전은 **main의 Native PY_SPF 1.0 설치형 배포본**입니다.
[현재 설치·실행 안내](../README.ko.md) · [현재 배포 파일](../output/native-installer/)

이 폴더는 이전 배포본과 역사적 설명을 보존합니다. 현재 앱과 혼합 설치하거나,
이곳의 과거 시험 결과를 현재 설치본의 실장비 검증으로 합산하지 않습니다.

| 보관 대상 | 파일 및 출처 |
|---|---|
| 원본 재구현 1.6.0.post1 | [ZIP·wheel](reconstruction-1.6.0.post1/) |
| 원본 재구현 1.6.0.post2 | [ZIP·설치기 수정 ZIP·wheel](reconstruction-1.6.0.post2/) |
| EXE 도입 전 Native PY_SPF 1.0 | [소스 ZIP·wheel](source-distributions/PY_SPF_1.0/) |
| External Control 2.0.0 | [기존 배포물·통신 진단 브랜치 출처](external-control-2.0.0/) |
| 외부 펌프 비교 프로그램 1.5.1 | [소스 스냅샷](external-pump-1.5.1/) |
| 원본 복구 분석 | [역사적 분석 기록](notes/ANALYSIS.ko.md) |
| post2 개발·검증 기록 | [당시 변경 기록](notes/POST2.ko.md) |

원본 배포 파일은 바이트를 바꾸지 않고 이동하거나 고정 Git 커밋에서 복원했습니다.
[MANIFEST.json](MANIFEST.json)은 출처 커밋·원본 경로·크기·SHA256을 기록합니다.
[SHA256SUMS](SHA256SUMS)는 이 보관함의 현재 파일을 확인하는 용도입니다.
이동한 설명 문서는 상대 링크와 보관 안내만 조정했으며 원본 해시도 출처 목록에 남겼습니다.

현재 소스는 루트 `spitfire/` 하나를 기준으로 합니다. 과거 프로그램 소스를 다시
활성 패키지 경로에 중복 배치하지 않으며, 기존 브랜치와 Git 이력은 그대로 보존합니다.
원본 제조사 리소스·역설계 근거는 `analysis/`, 당시 화면은 `previews/`, 최신 영문·한글
통합 제어 문서는 [docs/spitfire_control_flow/](../docs/spitfire_control_flow/)에 유지합니다.
제조사 매뉴얼과 문서 양식 PDF 전문은 저장소에 없으며, 기존 문서에 첨부 출처와 해시가 기록돼 있습니다.

새 개발용 소스 ZIP과 wheel을 만들 때는 `python tools/build_release.py`를 사용합니다.
생성물은 Git에서 제외한 `dist/source/PY_SPF_1.0/`에 기록되며, 이 보관함의 원본 배포물을 덮어쓰지 않습니다.
