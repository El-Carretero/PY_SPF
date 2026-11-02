# PY_SPF 문서

현재 앱의 [설치·실행 안내](../README.ko.md)와 [Windows 설치·제거 및 격리 범위](../packaging/windows/README.ko.md)를 먼저 확인할 수 있습니다. 소스를 직접 실행하거나 시험하려면 [소스 개발 안내](source-development.md)를 사용합니다.

## Spitfire 통합 제어 흐름

전원 투입부터 RUN 요청, 하드웨어 활성화 및 Emission Expected까지 코드·원본 실행 파일·통신 기록·제조사 매뉴얼의 근거를 구분한 분석입니다. Python 구현, 원본 프로그램과 실제 하드웨어의 동작을 구별하며 미확인 조건을 명시합니다.

| 자료 | English | 한국어 |
|---|---|---|
| 전체 분석·도면 안내 | [README](spitfire_control_flow/README.md) | [README](spitfire_control_flow/ko/README.md) |
| 검토용 PDF | [Review 02](spitfire_control_flow/XL-TR-SPF-001_Spitfire-Control-Flow_Review02.pdf) | [Review 02](spitfire_control_flow/XL-TR-SPF-001_Spitfire-Control-Flow_KO_Review02.pdf) |
| 통합 운전 순서 | [01](spitfire_control_flow/01_main_operation.md) | [01](spitfire_control_flow/ko/01_main_operation.md) |
| 신호·인터록 논리 | [02](spitfire_control_flow/02_signal_interlock.md) | [02](spitfire_control_flow/ko/02_signal_interlock.md) |
| 상태 전이 | [03](spitfire_control_flow/03_state_machine.md) | [03](spitfire_control_flow/ko/03_state_machine.md) |
| 통신 시퀀스 | [04](spitfire_control_flow/04_communication_sequence.md) | [04](spitfire_control_flow/ko/04_communication_sequence.md) |
| 신호 참조표 | [05](spitfire_control_flow/05_signal_reference.md) | [05](spitfire_control_flow/ko/05_signal_reference.md) |
| 출처·검증·미확인 사항 | [06](spitfire_control_flow/06_evidence_and_unknowns.md) | [06](spitfire_control_flow/ko/06_evidence_and_unknowns.md) |

문서는 명시된 소스 커밋과 보관된 근거를 기준으로 작성한 **검토용 분석**입니다. 현재 설치 파일의 실장비 제어·광학 출력 인증이나 운전 승인 문서로 해석하지 않습니다. Mermaid 원본과 렌더링 도면, 출처 목록 및 PDF 제작·검사 기록은 [문서 디렉터리](spitfire_control_flow/README.md)에 함께 보관합니다.

## 릴리스와 보관 자료

- [Native 1.0 제어 변경과 과거 실장비 관측 범위](../RELEASE.ko.md)
- [이전 배포·원본 복구 분석 안내](../Legacy/README.md)
- [원본 분석 및 검증 근거](../analysis/)
- [원본 리소스·타사 구성요소 출처](../THIRD_PARTY_NOTICES.md)

제조사 매뉴얼과 문서 작성 표준의 PDF 전문은 저장소에 재배포하지 않습니다. 제공된 자료의 제목·해시·페이지 수와 보관 범위는 [출처 매니페스트](spitfire_control_flow/evidence/source_manifest.json)에 기록돼 있습니다.
