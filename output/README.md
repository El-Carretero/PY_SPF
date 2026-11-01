# 1.6.0.post2 배포 파일

- `PY_SPF_1.6.0.post2.zip`: 소스·원본 NI 리소스·분석·시험·install.bat·post2 wheel.
- `spitfire_gui_reconstruction-1.6.0.post2-py3-none-any.whl`: 설치용 앱.
- `PY_SPF_1.6.0.post2_installer_fix.zip`: 기존 프로젝트에 덮어쓰는 설치·실행 배치 수정본.
- `SHA256.json`: 위 배포물의 크기와 SHA256. ZIP 외부에서 배포물 해시를 확인합니다.

기존 설치가 실패했다면 `installer_fix.zip`을 **기존 프로젝트 폴더에** 풀어 덮어쓰고
`install.bat`을 다시 실행합니다. 폴더를 옮기거나 `.python32`·가상환경을 삭제할 필요는 없습니다.
이 작은 ZIP은 설치기만 포함합니다. **Native GUI 수정까지 적용하려면 전체 `PY_SPF_1.6.0.post2.zip`을
덮어쓰고 `install.bat`을 실행**합니다. 01번 PC는 수정된 소스와 가상환경을 이미 반영했습니다.

Windows에서는 ZIP을 풀고 그 안의 `install.bat`을 실행합니다.
의존성 다운로드에 인터넷이 필요합니다. Python 및 PySide6 wheel은 ZIP에 포함하지 않습니다.
기본 설치는 Native용 32비트 Python을 찾거나 공식 서명 확인 후 자동 설치하며 `.venv-native`를 만듭니다.
Qt는 `install.bat qt`로 별도 설치합니다.
앱 wheel 자체의 `py3-none-any` 표시는 NI DLL이 모든 OS에서 작동한다는 뜻은 아닙니다.

이 브랜치의 배포물은 post2만 포함합니다. post1 배포물은 `main` 이력에 있습니다.
재생성: 개발 가상환경에서 `python tools/build_release.py`.
