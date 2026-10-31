# 선택형 영구 통신 진단 로그

`feature/empower-independent`의 External Control용 기능이다. 기본값은 OFF이며
기존 2,000개 메모리 이벤트를 유지한다. 원본 GUI의 `datalog.csv` 및 External
앱의 `external_datalog.csv`·Data Logging 스위치와 별개다. 새 로그를 켜도
조회·쓰기·폴링·timeout·Fault 판정·Reset 명령 및 순서를 추가하거나 변경하지 않는다.

## 켜기 / 끄기

Windows에서 안전하게 시뮬레이터로 확인하는 예:

```bat
python -m spitfire --demo --backend qt --tcp-port 0 --comm-log-dir "C:\Users\Fluke\Documents\PY_SPF_logs" --comm-log-max-bytes 5242880 --comm-log-backups 4
```

GUI 없는 확인(실제 장비 연결 없음):

```bat
python -m spitfire --demo --headless --tcp-port 0 --duration 3 --comm-log-dir ".\comm_logs"
```

`--comm-log-dir`를 생략하면 파일·기록 스레드가 생성되지 않는다. 실행 중 변경하는
GUI 스위치는 없으며, 종료 후 옵션을 바꿔 다시 실행한다. Qt·Native·headless 모두
공통 `make_controller()`를 통해 적용된다. 별도 Python 코드에서는
`Controller(..., diagnostic_config=DiagnosticConfig(Path("comm_logs")))`를 사용한다.
새 의존성은 없고 Python 표준 라이브러리만 사용한다. 기존 배포 ZIP/wheel은 이
수정을 포함하지 않으므로 변경 브랜치의 소스를 사용하거나 새로 빌드해야 한다.

## 파일·보존·오류 처리

- 세션마다 고유한 `comm-<session_id>.jsonl`을 만든다. UTF-8 JSON Lines, 한 줄에 한 이벤트다.
- 기본 파일당 5 MiB, 회전본 4개(현재 파일 포함 세션당 최대 25 MiB).
  `.1`이 가장 최근 회전본이며 오래된 `.4`는 삭제된다. `--comm-log-backups 0`은
  회전 시 현재 파일을 비우고 새 파일을 만든다. 최소 파일 크기는 4,096 bytes다.
- 제한은 **세션별**이다. 재실행 시 다른 세션의 파일을 지우지 않으므로 전체 폴더
  크기는 실행 횟수에 따라 늘어난다. 여러 앱 실행도 서로의 파일을 회전시키지 않는다.
- 파일 I/O·JSON 직렬화·flush·회전은 단일 별도 스레드가 수행한다. 통신 스레드는
  최대 4,096개 이벤트의 큐에 `put_nowait`한다. 큐가 차면 새 이벤트를 버리고
  `dropped_total`·순번 누락으로 표시한다. 종료 요약에도 누락 수를 기록한다.
- 한 레코드가 파일 상한보다 크면 `record_omitted="exceeds max_bytes"`와 원래 크기를
  남긴다. 파일 크기 상한을 넘기거나 JSON 한 줄을 분할하지 않는다. 작은 상한에서는
  원문 UDP 레코드도 생략될 수 있으므로 원문 비교에는 기본 5 MiB를 권장한다.
- 경로/권한/디스크 부족/rename 오류는 로거만 중단하고 stderr와
  `controller.diagnostic_status`에 표시한다. 장비 Fault나 연결 상태로 취급하지 않는다.
  headless 출력에는 `communication_log` 상태가 포함된다. GUI의 기존 Fault 화면은
  로거 오류를 표시하지 않는다. 콘솔 없는 실행에서는 상태 API 또는 생성 파일을 확인한다.
- 정상 종료 시 최대 1초 동안 큐 배출을 기다린다. 스레드는 daemon이며 느린 디스크에서
  이 시간 안에 끝나지 않으면 종료 시 미기록분이 남을 수 있다. 각 줄을 flush하지만
  fsync는 하지 않는다. 강제 종료·정전 시 마지막 데이터의 보존을 보장하지 않는다.
  이는 손실 가능한 진단 기록이지 무손실 감사 로그/패킷 캡처가 아니다.

## 기록 필드

| 필드 / 이벤트 | 의미 |
|---|---|
| `schema_version`, `session_id`, `sequence` | 형식 버전 1, 실행 식별자, 세션 내 이벤트 순서. 회전 후에도 유지 |
| `utc_time`, `wall_time_ns` | UTC 실제 시각 / Unix epoch nanoseconds. OS 시각 조정 시 뒤로 갈 수 있음 |
| `elapsed_ns` | 로그 세션 시작 이후 `monotonic_ns()` 경과시간. 실제 시각과 별개 |
| `connection_id` | 연결 시도 세대. reconnect 후 증가 |
| `request_id` | 원본 프로토콜의 `[1089]`/`<1089>` 같은 명령 ID |
| `request_seq` | Python 세션에서 각 송신 시도마다 부여한 별도 순번. 패킷에는 넣지 않음 |
| `request_attempt`, `request_sent`, `request_failed` | 검증 전 송신 시도, 성공한 send 호출 이후, timeout/거부/실패 |
| `udp_tx`, `udp_rx`, `udp_send_error` | 실제 transport 경계 원문. `mode=simulator`이면 모의 데이터 |
| `payload_hex`, `payload_text`, `captured_bytes` | 바이트 비교용 hex, Latin-1 표시용 텍스트(JSON escape), 수신/송신된 바이트 수 |
| `local_endpoint`, `peer_endpoint`, `sender_endpoint` | 로컬 bind 주소·포트, 설정된 상대, 실제 수신 송신자 |
| `datagram_id`, `packet_number`, `line` | 모든 관측 수신 패킷 순번, 파서 패킷 순번, `(packet,line)<id>...` 형태의 응답 |
| `disposition` | raw RX: `parsed`, `unparsed`, `unexpected_peer`, `drained_before_request`; 응답: 정상·거부·불일치·잘못된 readback 등 |
| `active_request_seq` | 패킷 관측 당시 활성 요청. 응답과 일치한다고 단정하는 필드가 아님 |
| `state` | 연결 상태, 기존 `fault_reason`, COMSTATUS/TDG/ECU/Head의 수치와 freshness. 변화할 때 기록 |
| `reset_id`, `reset_step` | 사용자 Reset 조작과 3단계 명령의 상관관계 |
| `reset_requested/blocked`, `reset_step_queued/result/cancelled` | Reset 접수·기존 조건에 따른 차단·큐 등록·ACK/실패·미전송 취소 |
| `readback_for_request_seq` | Reset 후 조회가 어느 송신 요청의 readback인지 식별 |
| `startup_result`, `connection`, `transport_open/close` | 초기 IDN 응답/timeout, 연결·재연결·종료, 소켓 생명주기 |
| `session_end`, `dropped_total`, `record_omitted` | 정상 배출 종료·누락/생략 여부. 없으면 완전한 기록이라고 간주하지 말 것 |

Reset은 기존 `(2049, 2052, 2050)` 순서와 readback 조회를 관찰한다. `ack`는
명령 응답 수신이며 Fault 해제 성공의 보증이 아니다. 이후 `response`와 `state`를
확인한다. 별도의 Reset 성공 판정이나 재전송 로직을 추가하지 않았다.

원문 수신은 **기존 `recvfrom(1495)`가 전달한 바이트**를 기록한다. 1,495 bytes이면
`possibly_truncated=true`이며 그 이상 UDP 데이터는 기존 transport에서 이미 잘렸을
수 있다. 패킷 크기·파서·발신자 필터·이전 응답 drain 정책은 바꾸지 않았다.

## XP Wireshark와 비교

먼저 앱을 종료하거나 닫힌 로그 파일을 복사해 분석한다. 회전본을 함께 지정한다.

```bat
python -m spitfire.diagnostic_export comm_logs\comm-SESSION.jsonl.2 comm_logs\comm-SESSION.jsonl.1 comm_logs\comm-SESSION.jsonl --output python-communication.csv
```

CSV 변환은 파일 인수 순서와 무관하게 세션/이벤트 순서로 병합하고 네트워크를
열지 않는다. 모든 이벤트를 보존하므로 `event=udp_tx/udp_rx`를 필터링하면 된다.
`udp.payload`는 `payload_hex`, `frame.time_epoch`는 정밀도를 잃지 않는 epoch 문자열이다.

XP에서 확보한 캡처는 Wireshark가 설치된 분석 PC에서 다음처럼 내보낼 수 있다.

```bat
tshark -r xp_capture.pcapng -Y "udp.port == 1024" -T fields -E header=y -E separator=, -E quote=d -e frame.number -e frame.time_epoch -e ip.src -e udp.srcport -e ip.dst -e udp.dstport -e udp.payload > xp-udp.csv
```

1. 패킷 방향·포트·payload에서 `[id]command`와 `<id>response`를 대조한다. tshark의
   hex에 `:`가 있다면 제거한다. raw hex는 대소문자·공백·CR/LF/NUL을 보존한다.
2. `wall_time_ns`/`frame.time_epoch`는 양쪽 PC 시계가 맞을 때만 직접 비교한다.
   서로 다른 실행은 Reset 또는 첫 IDN을 기준으로 정렬하고, 이벤트 사이 간격은
   Python `elapsed_ns`와 캡처 상대시간을 사용한다.
3. COMSTATUS 원문(예: 4/5), 유효성, state의 freshness와 Fault 사유를 함께 본다.
   원본과 External 버전의 Empower 정책 차이를 로그 수집기의 차이와 구분한다.
4. 로컬 UDP 소켓은 기존대로 `0.0.0.0`에 bind하므로 `local_ip_bound`는 실제 송신
   NIC 주소를 뜻하지 않는다. 실제 출발 IP/링크 시각·커널 버퍼 손실은 PCAP에서 확인한다.

기록 시각은 Python이 send/recv를 관측한 시각이며 NIC 캡처 시각이 아니다. 로그
ON에도 CPU/메모리의 작은 관측 비용은 생긴다. 스케줄·명령/상태 로직은 그대로지만
실제 장비의 시간 정밀도에 영향이 0이라는 주장은 하지 않는다. 프로토콜 ID는
트랜잭션 번호가 아니므로 **새 요청 이후 도착한 같은 ID의 과거 응답**은 기존처럼
구별할 수 없다. 로컬 순번 추가는 이 wire 한계를 해결하지 않는다.

## 검증 범위

[검증 기록](VALIDATION_COMMUNICATION_LOGGING.ko.md)에 로컬 실행 결과와 Windows
검증 범위를 구분한다. `tests/test_diagnostics.py`는 시뮬레이터와 실제 localhost
UDP를 사용하고, 기존 `tests/conftest.py`의 loopback 네트워크 가드를 따른다.
기존 CI의 Windows/Linux portable 전체시험에 자동 포함되고, Windows x86 Native
경계 시험에도 추가했다. CI 데모의 JSONL은 OS별 artifact의 `communication/`에 남는다.
실제 레이저에 대한 접근·명령 전송은 수행하지 않았다.
