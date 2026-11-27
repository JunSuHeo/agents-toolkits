# 검증 기록

검증일 2026-11-26 (Asia/Seoul). 대상은 Agent Toolkit 0.1.0 CLI, 패키징, 예제 A~F의 생성·적용 경로다. 아래 종료 코드는 명령 또는 표에 적힌 검증 절차의 실제 결과다.

## 실행 환경과 결과

| 환경 | 실행 명령 | 종료 코드 | 기대 결과와 관찰 |
| --- | --- | ---: | --- |
| macOS 26.6.2 arm64, CPython 3.12.14, uv 0.12.10 | `uv run --locked --python 3.12 pytest` | 0 | 32개 테스트 모두 통과 |
| macOS arm64, CPython 3.13.15, 별도 uv 환경 | `uv run --locked --python 3.13 pytest -q` | 0 | 32개 테스트 모두 통과 |
| Linux aarch64, Python 3.12.16, Git 2.39.5, Docker의 `python:3.12-bookworm` | 소스 배포를 풀고 `uv run --locked --python /usr/local/bin/python3.12 pytest` | 0 | 32개 테스트 모두 통과 |
| macOS 및 Linux | `uv run --locked ruff check .`, `uv run --locked ruff format --check .`, `uv run --locked python scripts/export_schemas.py --check` | 0 | 린트 오류 없음, 검사 파일 모두 포맷 일치, JSON Schema 5개가 모델과 일치 |
| macOS, Git 2.50.1 | `uv lock --check`, `uv build --no-sources` | 0 | 잠금 유효, wheel 및 sdist 생성. sdist에 예제, 스키마, 테스트와 잠금 파일 포함 |
| macOS, 격리된 uv 도구 디렉터리 | `uv tool install --python 3.12 .`, `agent-toolkit init`, `agent-toolkit validate` | 0 | 소스에서 명령 설치, 최소 프로젝트 생성, 설정 및 Lock 검증 |
| macOS, 격리된 uv 도구 디렉터리 | `uv run --locked python scripts/smoke_distribution.py` | 0 | wheel 설치 후 Codex·Claude Code·Grok Build·Generic 대상 웹서비스 생성과 유효성 검사 |
| macOS, 임시 Git 저장소 | `uv run --locked python scripts/build_release.py`, `uv run --locked python scripts/smoke_distribution.py --expect-commit <커밋>` | 0 | 원본 Git 커밋이 wheel에서 생성한 `toolkit.lock`에 기록됨 |
| macOS | 링크 대상이 저장소에 있는지 README·개발 문서·예제 문서 검사 | 0 | 상대 링크 대상 존재 확인 |

## 확인한 사례

- A~E 프로필·스택 조합, 파생 스택, 선택된 Skill 의존성 및 생성물 재현성
- F 기존 지침, 코드, 사용자 파일, CI와 기존 unittest 보존 및 적용 후 재검증
- 미관리 생성 경로 충돌, 수정·삭제된 관리 파일과 조작된 Lock의 쓰기 차단
- 경로 대소문자, 심볼릭 링크·하드링크, YAML 별칭·중복 키, 필수 보안 Gate 설정 보호
- CRLF 체크아웃 허용, 업데이트 예외 롤백, 중단된 게시 복구와 수동 수정 보존
- 승인된 로컬 Gate 실행, 테스트 명령 종료 코드 7과 선택 항목 종료 코드 8·9 처리
- 독립 검증자 조건, 작업별 인수인계와 Git worktree 생성·더러운 상태의 제거 차단·정상 제거

## 재현 및 미검증 범위

개발 명령과 wheel 설치 검증은 [README](../README.md#개발-및-릴리스)에서 실행할 수 있다. Linux는 생성된 `dist/agent_toolkit-0.1.0.tar.gz`를 Python 3.12와 Git이 있는 리눅스에서 풀고 동일한 빌드 환경을 설치한다.

Windows 네이티브 실행과 GitHub Actions의 원격 결과는 아직 확인하지 않았다. Codex·Claude Code·Grok Build는 공식 형식과 생성 파일을 확인했으며 실제 모델 세션에서의 로딩·호출은 이 검증 범위에 포함하지 않았다. 예제의 실제 애플리케이션 빌드나 대용량 데이터 부하는 프로젝트 생성 계약 밖에 있다.

macOS 및 Linux에서 MVP CLI, 패키지 설치와 검증 시나리오를 통과했다.

## 0.1.1 회귀 검증

2026-11-27 macOS, Python 3.12.14에서 `uv run --locked pytest`가 종료 코드 0으로 37개 테스트를 통과했다. 하위 경로 탐색과 중첩 생성, Git 경계, 기존 Claude 지침 연결, npm 감지, 이전 Lock의 품질 명령 실행과 업데이트를 검증했다.

## 0.1.2 회귀 검증

2026-11-27 macOS에서 Ruff 검사와 포맷 확인, 스키마 비교 및 pytest 39개가 통과했다. 규칙 제안의 근거 표시, 파일 보존, 프로젝트 명령이 실행되지 않는 동작과 잘못된 설정 파일 처리를 확인했다.
