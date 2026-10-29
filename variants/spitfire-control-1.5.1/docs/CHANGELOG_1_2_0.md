# Spitfire Python Control 1.2.0

기존 1.1.3의 Empower 통합 제어 경로에 외부 펌프 구성을 추가합니다.
DM1-527-20은 별도 제어하며 TDG와 seed oscillator를 유지하는 구성에 맞췄습니다.

## 변경 사항

- 통신 방식(`simulator`/`udp`)과 독립적인 펌프 설정(`empower`/`external`) 및 CLI `--pump-mode` 추가.
- 외부 펌프 모드에서 Empower 전용 초기·자동·수동·명령 후 조회를 제외.
- 외부 펌프 모드의 송신 정책을 GUI뿐 아니라 controller의 명령 제출·실제 송신 시점에도 적용.
- 실기 응답에 가상 Empower 정상값을 섞지 않고 미사용/미감시 상태 표시.
- 사용자가 명시적으로 요청한 경우에만 opt-out 설정. HV OFF 및 readback 확인 적용.
- 일반 polling과 별개로 opt-out, 공유 fault, TDG 상태·fault, HV 상태, TDG fault override,
  PC1/PC2 복합 readback을 감시.
- HV/채널 ON에는 최근 fault override=0과 PC1/PC2 BWD·ENA 확인을 요구.
- opt-out 및 BWD/TCU/TDG latch reset은 최근 HV OFF 확인을 요구.
- 의미가 검증되지 않은 전역 BWD 쓰기는 외부 펌프 모드에서 차단.
- 공유 `EMP:FAULT?` 원시값 보존. 확인된 opt-out에서만 알려진 Empower 전용 비트를 유효 요약에서 제외.
- 메인 RUN 위치에 `TDG / HV` 화면 이동 버튼을 제공하고 외부 펌프 모드의
  `HV OFF` 버튼을 TDG HV OFF로 한정.
- 외부 펌프 모드에서 Empower 서비스, 임의 raw 송신, 전역 pump ON/OFF/reset 및 보호 우회 활성화 차단.
- 구성 변경 시 기존 연결·대기 명령·상태를 정리하며 자동 ARM/출력 복원을 하지 않음.
- 시뮬레이터에 Empower 없음, opt-out 미지원, 공유 오류 조회 미지원 및 지속 고장 주입 시나리오 추가.
- Windows 설치·실행 스크립트와 한국어 외부 펌프 안내 추가.

## 검증 범위와 남은 확인

오프라인 테스트는 소프트웨어 경로와 합성 응답 처리를 검증합니다.
배포 검증의 실제 통과·실패·제외 항목은 `VALIDATION_1_2_0.md`에 기록합니다.
환경에 의해 loopback UDP가 제한된 검사를 통과한 것으로 보고하지 않습니다.
실제 장비를 제어하지 않으며 DM1의 준비·발진·광펄스 타이밍을 보증하지 않습니다.
실제 TDG에서 `EMPOPTOUT`의 지원·동작 범위를 확인해야 하고,
DM1 동기 출력의 전기 규격 및 광펄스 대비 지연을 측정해야 합니다.

원본 매뉴얼의 펌프→TDG 트리거 구조를 기준으로 안내를 수정했습니다.
최신 TDG의 기능을 구형 TDG에서 사용할 수 있다고 가정하지 않습니다.
기존 1.1.3은 별도 보관하고 새 폴더에서 1.2.0을 실행하십시오.
