"""Network diagnostics and human-readable setup instructions."""

from __future__ import annotations

import ipaddress
import socket


def validate_ipv4(value: str, *, field: str = "address") -> str:
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid IPv4 address") from exc
    if address.version != 4 or address.is_multicast or address.is_unspecified:
        raise ValueError(f"{field} must be a unicast IPv4 address")
    return str(address)


def local_ipv4_addresses() -> list[str]:
    result = {"127.0.0.1"}
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            result.add(item[4][0])
    except OSError:
        pass
    return sorted(result, key=lambda item: tuple(int(part) for part in item.split(".")))


def setup_text(bind_ip: str, original_ip: str, python_ip: str, port: int) -> str:
    return f"""권장 분리형 네트워크

  가상 Spitfire (Windows 호스트): {bind_ip}:{port}
  Python GUI 로컬 주소:            {python_ip}:{port}
  XP VM / 원본 GUI 주소:           {original_ip}:{port}

1. VM 네트워크를 Host-only(호스트 전용) 어댑터로 설정합니다.
2. Windows 호스트의 그 어댑터에 {python_ip}/24와 {bind_ip}/24를 추가합니다.
3. XP VM의 고정 IPv4를 {original_ip}/24로 설정합니다. Gateway와 DNS는 비워도 됩니다.
4. 검증기에서 가상 장비를 시작합니다.
5. XP 원본 프로그램을 실행합니다. 원본은 {bind_ip}:{port}로 송신합니다.
6. Python 1.1.3 설정:
     Remote host = {bind_ip}, Remote port = {port}
     Local host  = {python_ip}, Local port  = {port}
7. 두 프로그램에서 같은 조작을 한 뒤 [비교 생성]을 누릅니다.

중요
- Python GUI의 Local host를 0.0.0.0으로 두면 가상 장비의 UDP {port}와 충돌할 수 있습니다.
- Bridged 대신 Host-only를 권장합니다. 실제 레이저 제어망과 분리하십시오.
- 이 검증기는 가상 장비이며 실제 레이저, HV 또는 모터에 패킷을 전달하지 않습니다.
"""
