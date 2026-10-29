# 1.3.0 변경 사항

XP 1.6.0 설치 배포물의 EXE/UIR를 다시 대조하여 오류 출처와 타이밍 해석을 수정하고,
외부 펌프 운전의 readback 조건과 Python 안정성을 보강했습니다.
실제 레이저·TDG에 쓰기를 수행해 검증한 릴리스라는 의미는 아닙니다.

## 1.2.0 오류 매핑 정정

UIR 저장 control ID는 runtime ID보다 1 작습니다. 이전 코드가 이를 직접 대응시켜
`EMP:FAULT?`에 TDG·TCU 오류가 섞여 있다고 해석한 것은 잘못이었습니다.

- 1014는 확인된 원본 decoder 기준 Empower 오류입니다. 외부 모드는 이 조회를 전부 제외합니다.
- TDG fault는 1066, TCU 상태는 1088, 통신 상태는 1089, BWD 상태는 1039에서 읽습니다.
- 1066·1039는 unsigned 32-bit hexadecimal로 해석합니다. 예를 들어 문자열 `2000`은
  decimal 2,000이 아니라 `0x2000`입니다. TCU·통신·module 상태를 일괄 hex로 바꾸지 않습니다.
- 1014의 네 값은 decimal입니다. 네 번째 LBO stability scalar를 8-bit로 잘라내지 않습니다.
- Empower communication 표시에는 1014와 1089의 서로 다른 근거를 함께 반영합니다.
  한쪽 정상값이 다른 쪽의 오류를 지우지 않도록 합니다.
- 확인되지 않은 checksum 매핑을 만들지 않습니다. TDG fault의 미식별 nonzero 값과
  미식별 통신 비트는 보존하고, TCU의 모든 nonzero 상태를 고장으로 단정하지 않습니다.

## 외부 타이밍 프로파일

- `File > External timing...`에서 expected seed MHz, 허용 편차, expected pump Hz를 저장합니다.
  초기값은 80 MHz ±1 MHz와 10 Hz이며 사용자 편집 기준입니다.
- Expected pump Hz는 참고값입니다. 실제 펌프 반복률 측정이나 DM1 설정에 사용하지 않습니다.
- `SAVE & RECONNECT`는 DISARM 상태로 재연결하며 firmware에 타이밍을 쓰지 않습니다.
- `APPLY EXT SOURCES`를 명시적으로 실행하면 oscillator sync와 amplifier trigger를 EXT로
  요청하고 readback을 확인합니다. 최근 HV OFF가 필요하며 실제 UDP 쓰기는 ARM이 필요합니다.
- 출력 활성화 전에 최근 EXT readback 두 개와 1065의 측정 seed가 허용 범위에 있는지 확인합니다.
- TCU opt-out(1033), head/compressor opt-out(1069), humidity override(1044)도
  최근 readback이 모두 0이어야 합니다. TDG·TCU·head module 통신은 각각 최근 정상 응답이 필요합니다.
- opt-out·상태·보호·타이밍을 포함한 18개 필수 조회가 Automatic polling과 독립적으로 동작합니다.
- 타이밍 source, 분주, 내부 trigger frequency, oscillator 기준 갱신에도 최근 HV OFF를 요구하며
  제출 시점과 실제 송신 시점 모두 재검증합니다.

## 원본 주파수 해석 반영

- 1065 `TDG:READ:OSCQUEST?`를 measured seed oscillator MHz로 사용합니다.
- 2046 `TDG:OSC:SETTOFRQ`는 측정 MHz 숫자를 추가 배율 없이 전달합니다.
  simulator도 2046이 1024를 변경한다고 가정하지 않습니다.
- 1024의 이름만으로 독립적인 80 MHz 측정값으로 해석하지 않습니다.
- 1079는 원본에서 reply 값을 사용하지 않아 실제 pump Hz로 해석하지 않습니다.
- XP 원본 1067 초기화의 자동 INT→EXT 쓰기를 복사하지 않습니다.
- external 화면은 expected pump rate를 `unmeasured`, optical sync를 `unverified`로 구분합니다.

## Python 안정성

- 설정의 enum, host, port, timeout, polling 간격, boolean, log path와 타이밍 기준을 검증합니다.
  잘못된 저장 설정은 기본 simulator 설정으로 복구합니다.
- 설정 저장 시 고유 임시 파일, flush/fsync, 원자적 교체를 사용합니다.
  교체 실패로 기존 파일을 잃지 않도록 합니다.
- 오류·잘못된 응답을 받으면 같은 readback의 alias/canonical 유효성도 무효화합니다.
  예를 들어 1061 오류가 이전 1021 HV 상태를 계속 신뢰하게 만들지 않습니다.
- `--simulator`와 `--udp`를 동시에 지정하지 못하게 합니다.
- 모든 구성에서 command argument의 제어문자·세미콜론을 거부합니다.
  조회 인자는 확인된 1026의 channel 1–5 이외에는 허용하지 않습니다.
- Raw serial은 DTR/RTS를 적용한 후 포트를 열고, 설정·열기 실패 시 만든 handle을 닫습니다.
  USB adapter나 OS driver의 전기적 glitch 부재까지 보증하는 것은 아닙니다.

## 검증과 남은 범위

이 변경 기록은 구현 내역입니다. 전체 시험 수와 실행 결과는 별도 `VALIDATION_1_3_0.md`를
기준으로 하며 이전 1.2.0 결과를 재사용하지 않습니다.
실기 firmware의 opt-out 의미, 10 Hz 지원, 외부 동기 출력 사양·지터·광학 위상은 미검증입니다.
전체 원본 프로그램과의 동적 동등성도 주장하지 않습니다.

근거·구현 범위·추가 개선 항목은 [XP 대조 검토 보고서](XP_PARITY_REVIEW_1_3_0.md)에 있습니다.
