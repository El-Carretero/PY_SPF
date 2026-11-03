# v0.1.0 검토 사항 반영표

| 검토 항목 | v0.2.0 수정 | 확인 방법 |
|---|---|---|
| 폴링 응답 차이 누락 | 동일 관측 반복만 압축, 상태·오류 전이는 유지 | test_poll_values_are_compared, test_poll_state_transitions_survive_compression |
| 과거 판정/최신 캡처 혼합 | 단일 snapshot에서 결과와 모든 증거 파일 생성 | test_report_recomputes_a_stale_comparison, test_export_handler_refreshes_result |
| 전역 지연 및 거짓 latency | 비차단 전송 예약, 클라이언트별 순서 유지, 수신부터 측정 | test_delayed_client_does_not_block_other_and_latency_is_honest |
| 프로토콜 오류/헤더 차이 누락 | 진단도 판정에 포함, 프레이밍 별도 비교, 화면 오류 이력 | test_real_malformed_packet_invalidates_comparison, test_reply_header_difference_is_detected |
| 초기화 이후 이전 요청 혼입 | 세션 ID, 이전 응답 취소, 버퍼 정리, GUI 이전 이벤트 제외 | test_reset_cancels_old_delayed_evidence, test_clear_handler_filters_old_events_and_keeps_new_events |
| ID만 보고 잘못된 명령 실행 | ID/문자열 및 인자 검증, 검증기 진단 응답 | test_id_text_mismatch_cannot_switch_on, test_numeric_argument_is_required_and_finite |
| 조회 별칭 상태 불일치 | 별칭은 동일한 논리 상태와 복합 delay 상태 참조 | test_motor_speed_aliases_share_state, test_bwd_aliases_share_state |
| 응답 유실이 실행도 취소 | 요청 유실/응답 유실 분리, override도 실행 후 적용 | test_reply_loss_still_executes_write, test_request_loss_does_not_execute_write |
| 프로필 재현 정보 부족 | 요청별 전체 profile JSON, 변경 이력, session metadata | test_profile_is_frozen_until_delayed_reply |
| 미구현 효과가 정상으로 보임 | wire 비교와 effect coverage 분리, UNVERIFIED 판정 | test_unmodelled_writes_are_not_certified |
| 시나리오 및 화면 기록 불편 | 단계 표식과 수동 관찰 입력 탭, HTML/JSON/CSV 저장 | test_observation_handler_persists_values |
| EXE 진입점 상대 import 오류 | 루트 run_verifier.py로 빌드, 실패 검사, frozen CLI 자체검사 | 소스 진입점/설치 wheel 통과; 실제 Windows EXE 미실행 |

## 판정 범위

- UI와 테스트에서 사용하는 잘못된 패킷/유실은 가상 서버에만 도달합니다.
- REPLIED는 서버의 sendto 성공입니다. UDP 클라이언트의 수신 또는 화면 파싱 성공을 의미하지 않습니다.
- 숫자 의미 비교는 단독 숫자 문자열만 정규화합니다. 명령 ID와 복합 문자열의 의미를 추측하지 않습니다.
- 물리 효과를 구현하지 않은 motor/service 명령은 의도적으로 미검증 상태입니다.
- strict fixture 인자 문법은 실제 XP 캡처로 보완할 수 있습니다. 실제 펌웨어 문법 전부를 입증한 것은 아닙니다.
- 스크린/DPI 및 Windows EXE·XP 원본 운용 검증은 별도입니다.
