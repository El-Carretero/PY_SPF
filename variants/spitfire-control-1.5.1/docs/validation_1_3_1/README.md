# 1.3.1 시험 근거

최종 결과는 [검증 보고서](../VALIDATION_1_3_1.md)를 참조하십시오.
`aggregate_final.json`은 새 실제 장비 조회 10단계만 집계합니다.
루트의 `spitfire_audit_20261027.csv`와 `spitfire_data_20261027_200055.csv`는 **작업 전 기존 1.3.0 세션**의 분석용 사본이며 새 시험 송신에 합산하지 않았습니다.
각 단계 폴더의 TX/RX/summary는 새 조회 시험 자료입니다. simulator-audit 폴더는 실제 장비와 통신하지 않은 합성 GUI 시험입니다.

`full_tests_131_initial.*`는 최초 실행에서 발견한 테스트 fixture 오류 기록입니다.
fixture 수정 뒤 `full_tests_131.*`의 최종 결과는 304개 통과, 실패·오류·skip 0개입니다.

이 폴더의 Python 파일은 **이 PC의 경로와 장비 주소에 고정된 시험 기록용 스크립트**입니다.
일반 실행 파일이나 범용 진단 도구가 아니며 자동 실행하지 마십시오.
재현하려면 경로와 query-only 제한, 포트 점유, 비가동 상태를 먼저 검토해야 합니다.
실제 송신이 없는 `aggregate_diagnostics.py`도 기록 당시 폴더 구조에 의존합니다.

패킷 수신 기록은 Python socket의 recvfrom 관측이며 NIC 선로 캡처가 아닙니다.
단위 변환과 출력·설정 쓰기 경로는 오프라인에서 검증했고, 실제 장치 설정 쓰기는 하지 않았습니다.
