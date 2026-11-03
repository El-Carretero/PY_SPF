# 1.2.0 검증 결과

이 기록은 소프트웨어와 시뮬레이터 검증 결과입니다. 실제 TDG 또는 DM1의 동작 승인 기록이 아닙니다.

## 실행한 검사

| 검사 | 결과 |
| --- | --- |
| 전체 테스트 검색 | 175개 |
| 실행하여 통과 | 165개 |
| 실패 / 오류 | 0 / 0 |
| 환경 제한으로 제외 | 실제 loopback UDP 왕복을 요구하는 10개 |
| External Pump 핵심 정책 테스트 | 33개 통과, 위 165개에 포함 |
| 소스 GUI: Empower / External Pump | 두 모드 PASS, 1024×768에서 잘린 제어 없음 |
| Windows EXE GUI: Empower / External Pump | 두 모드 PASS, 별도 프로세스에서 실행 |
| Python wheel / Windows EXE 빌드 | 완료, 버전 1.2.0 |

Python 3.13.9, Tk 8.6.15, Windows 11 환경에서 검사했습니다. EXE는 PyInstaller 6.19.0으로 빌드했습니다.
실장비 I/O를 차단한 검증 프로세스에서 실행했으며, 실제 COM 포트나 레이저 장비를 열지 않았습니다.
사용자의 기존 연결 설정을 불러오거나 저장하지 않았습니다.

External Pump GUI 검사는 Empower 부재 시뮬레이터에서 다음을 확인했습니다.

- 시작 시 쓰기 명령 없음, opt-out 자동 적용 없음.
- 명시적 opt-out 적용 후 실제 시뮬레이터 readback 확인.
- 필요한 보호 상태 확인 후 시뮬레이터 HV ON/OFF 왕복.
- Empower 전용 제어 및 전체 시스템 RUN/STOP 명령 미전송.
- DM1의 실제 출력/준비 상태를 확인했다고 표시하지 않음.

핵심 테스트에는 요청 접수 및 전송 직전 정책 검사, 혼합 fault word 보존,
오래되거나 없는 readback 차단, 기존 TDG fault override 및 PC1/PC2 BWD·ENA 상태 확인,
리셋 시 HV OFF 요구, 긴급 OFF 우선순위, 연결 시작 시 오래된 활성화 요청 차단이 포함됩니다.
기존 Empower GUI와 제어 경로의 회귀 검사도 포함했습니다.

## UDP 검사 제한

이 실행 환경에서는 localhost UDP bind/send는 가능했지만 실제 패킷 수신이 timeout되었습니다.
독립적인 단일 socket 자기 송수신에서도 같은 현상이 확인되었습니다.
최종 검사는 이 조건에 의존하는 10개만 실행 중 임시 제외했으며,
배포하는 테스트 소스에는 skip을 추가하지 않았습니다. 제외한 테스트 이름은
`validation_1_2_0/final_tests_120.json`에 모두 기록되어 있습니다.

실행 가능한 일반 Windows 환경에서 `run_tests.cmd`로 전체 175개를 다시 검사할 수 있습니다.
실제 TDG 네트워크 통신 성공을 이번 결과로 주장하지 않습니다.

## 실장비에서 남은 확인

- 실제 TDG firmware의 EMPOPTOUT 명령 지원과 opt-out 이후 fault/인터록 의미.
- 1014 혼합 fault 및 필요한 보호 설정 readback의 실제 응답 호환성.
- DM1 동기 출력의 존재와 전기 규격, TDG 입력 호환성.
- DM1 실제 광펄스와 기준 신호의 지연·지터 및 Pockels cell 타이밍.

프로그램은 DM1 제어, TTL 생성, 실제 광펄스 동기화 또는 광학적 준비 상태 검출을 구현하지 않습니다.
실제 오류를 일괄 정상 처리하거나 TDG·TCU·인터록 보호를 제거하지 않습니다.

## 원시 결과

`docs/validation_1_2_0/`에 테스트 로그와 소스/EXE GUI JSON 보고서를 포함했습니다.
`dist/SpitfirePythonControl.validation.json`에는 배포 EXE의 버전과 SHA-256이 있습니다.
해시는 파일 혼동을 확인하기 위한 것이며 코드 서명은 아닙니다.
