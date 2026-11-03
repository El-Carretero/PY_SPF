# 권장 검증 플레이북

각 단계 전에 캡처와 가상 상태를 초기화하고 응답 조건을 확인합니다.
[6. 시나리오 / 화면 기록]에서 단계를 시작하고 XP 원본 → Python 순서로 같은 동작을
반복합니다. 실제 레이저망은 연결하지 않습니다.

## A. 시작 및 기본 조회

1. 두 GUI를 각각 30초 실행
2. 통신등, IDN, version, 온도, 습도, status 화면 확인
3. Query ID coverage와 polling 횟수 차이 비교

합격 기준: 핵심 query의 base 문자열이 같고, Python에만 존재하는 안전 readback은
의도적 차이로 설명 가능해야 합니다.

## B. Q-switch 단위

1. 양쪽 UI에 1250 Hz 입력
2. wire write ID 2004의 인자가 모두 `125.00`인지 확인
3. query 1010에 대한 raw `125` 응답이 양쪽 화면에서 1250 Hz인지 기록

## C. Delay 복합 응답

1. channel 1에 12.5 설정
2. ON/OFF, BWD/NBWD, ENA/NENA를 각각 전환
3. ID 2019 인자와 1045 readback을 비교

## D. 안전 동작

1. ARM/DISARM 전환 자체는 클라이언트 로컬 상태이므로 wire에 나타나지 않을 수 있음
2. OFF, HV OFF, motor STOP을 각각 실행
3. write ID와 후속 readback query를 확인
4. Python에서 DISARM 직후 위험 queue가 취소되는지는 Python 자체 회귀 테스트 결과와
   함께 평가

## E. 오류 처리

응답 실험 탭에서 한 조건씩 적용합니다.

1. 1010 강제 응답 `125.00`
2. 1031 `ERROR:INJECTED`
3. 1000 응답 유실
4. 2004 설정 명령에서 응답 유실과 요청 유실을 각각 주입하고 readback 차이 확인
4. 1013 2500 ms 지연
5. CRLF
6. 잘못된 reply header

각 경우 두 GUI의 표시, reconnect, timeout 문구를 화면 기록 탭에 입력하고 단계 종료합니다. 보고서의 `ui_observations.csv`에 함께 저장됩니다.

## F. 최종 판정

- Wire report `MATCH`만으로 완전 호환 판정을 내리지 않음
- 모든 의도적 차이를 목록화
- 화면 관찰과 wire 증거가 모두 있는 기능만 호환 확인
- 실제 컨트롤러 확인은 별도 commissioning 절차로 분리


## G. 새 판정 확인

- 양쪽 습도값이 다르면 폴링 압축을 켠 상태에서도 `DIFFERENT`여야 합니다.
- 정상 조회 뒤 Python에서만 추가 명령을 보내고 바로 저장하면 최신 차이가 포함되어야 합니다.
- 한쪽 지연이 다른 쪽 IDN 조회를 막지 않아야 합니다.
- 지연 중 초기화하면 이전 세션 응답은 취소되고 새 캡처에 섞이지 않아야 합니다.
- 양쪽에 같은 오류/유실을 주입해도 `MATCH` 대신 `OBSERVATION_REQUIRED`여야 합니다.
- 장비 효과를 구현하지 않은 모터 STOP 등은 wire 일치와 별개로 `UNVERIFIED`입니다.
- `ERROR:VALIDATION:*`는 검증기가 만든 진단 응답이며 실제 펌웨어의 오류 문자열이라고 주장하지 않습니다.
