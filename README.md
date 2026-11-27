# Agent Toolkit

새 프로젝트와 기존 저장소에 공통 개발 규칙, 프로젝트별 Profile, 기술 Stack, Skills, 에이전트 역할과 검증 기준을 구성하는 로컬 CLI입니다. 애플리케이션 코드는 각 프로젝트에서 개발합니다. Toolkit 실행에 모델, 계정, API 키, 서버 또는 데이터베이스가 필요하지 않습니다.

## 설치

Python 3.12 이상과 uv를 사용합니다. 이 저장소 루트에서 설치합니다. 작업 공간 분리 기능을 사용할 때는 Git도 필요합니다.

```bash
uv tool install .
agent-toolkit --version
agent-toolkit doctor
```

## 새 프로젝트에서 시작

현재 디렉터리에 기본 최소 구성을 적용합니다.

```bash
agent-toolkit init
agent-toolkit validate
agent-toolkit status
```

웹서비스는 Profile, Stack과 AI 도구를 선택할 수 있습니다. `init`과 `adopt`는 기본으로 현재 디렉터리를 대상으로 합니다. 같은 Git 체크아웃 안에서 상위 Toolkit 프로젝트가 발견되면 중첩 생성을 중단합니다. 독립 프로젝트를 의도한 경우 `--allow-nested`를 지정합니다.

`status`, `validate`, `diff`, `update`, `recover`, `task plan`은 `--path`를 생략하면 가장 가까운 상위 Toolkit 루트를 탐색합니다. 별도 Git 체크아웃 경계에서 탐색을 멈춥니다. `--path`를 지정하면 해당 위치를 직접 사용합니다.

```bash
agent-toolkit init --path ./my-web --name my-web --profile web-service --stack nextjs,supabase --tools codex,claude --dry-run
agent-toolkit init --path ./my-web --name my-web --profile web-service --stack nextjs,supabase --tools codex,claude
agent-toolkit validate --path ./my-web
```

- `--complexity minimal`은 기본 검증 Skill과 단일 역할을 배치합니다. `standard`는 Profile에 필요한 역할과 작업 절차를, `extended`는 추가 검증·협업 자료를 배치합니다.
- `--skills code-review,handoff`로 기본 Skill 선택을 바꿀 수 있습니다. `--agents`도 같은 방식으로 선택하며, 빈 값은 해당 선택을 비웁니다.
- `--config <경로>`는 프로젝트 YAML을 입력으로 사용합니다. 프로젝트 루트에 `agent-toolkit.yml`을 미리 작성했다면 별도 옵션 없이 적용할 수 있습니다.
- `agent-toolkit list profiles`, `list stacks`, `list skills`, `list agents`에서 지원 항목을 확인합니다. `--search`는 이름과 설명을 찾습니다.

[예제 설정](examples/)에는 Next.js/Supabase 웹서비스, FastAPI/LangGraph, Rust/Oracle, Spring Boot/Docker, 소규모 Python 자동화와 기존 저장소 테스트용 fixture가 있습니다.

## 기존 프로젝트에 적용

프로젝트 루트에서 실행합니다. `inspect`는 알려진 파일 위치, 의존성 선언과 Git 상태에서 후보를 찾습니다. 추정한 Profile, Stack과 근거 파일을 적용 전에 검토할 수 있습니다. npm 스택은 `package.json`의 의존성 이름으로 감지합니다. `langgraph-js`는 JavaScript 또는 TypeScript용이며 기존 `langgraph`는 Python용입니다. 이미 적용된 선택은 `agent-toolkit.yml`에서 수정할 수 있습니다.

```bash
agent-toolkit inspect
agent-toolkit adopt --tools codex,claude
agent-toolkit adopt --tools codex,claude --apply
agent-toolkit validate
```

`adopt`와 `adopt --dry-run`은 파일을 쓰지 않습니다. `--apply`는 해당 명령에서 표시한 계획을 적용합니다. 기존 `AGENTS.md`와 `CLAUDE.md`가 있으면 보존하고 `KEEP`으로 표시합니다. Toolkit이 생성한 `CLAUDE.md`는 `AGENTS.md`와 `.agent-toolkit/GUIDE.md`를 함께 가져옵니다. 사용자가 관리하는 진입점에는 필요한 가이드 연결을 추가합니다. 기존 Skill이나 역할이 생성 경로와 겹치면 적용 전체가 중단됩니다.

프로젝트에 맞는 규칙 초안은 `agent-toolkit inspect --suggest-rules`로 확인합니다. 선언된 pytest·Ruff 설정, npm 스크립트, GitHub Actions와 기존 지침 경로를 근거로 후보를 출력합니다. 프로젝트 명령 실행과 파일 반영은 사용자가 검토한 뒤 별도로 진행합니다. 필요한 경우 `agent-toolkit document create PROJECT-RULES`로 프로젝트 소유 문서를 만든 뒤 채택한 문장을 옮깁니다.

## 구성과 파일 소유권

프로젝트 요구사항은 `agent-toolkit.yml`, [설정 스키마](schemas/project.schema.json), 프로젝트 소유 문서로 관리합니다. 팀 인원, 배포 환경, 보안·검증 조건, `multi_agent` 정책은 YAML에서 수정할 수 있습니다. 예를 들어 `nextjs`의 `react`, `supabase`의 `postgresql`은 생성 계획과 Lock에 함께 표시됩니다. 스택 중첩이 오류로 표시되면 하나를 제거하거나 `stack_conflict_notes`의 키에 실제 유형 구분과 검증 근거를 남깁니다.

| 경로 | 소유권과 역할 |
| --- | --- |
| `agent-toolkit.yml` | 프로젝트 소유. 설정과 실행 명령을 편집합니다. |
| `toolkit.lock` | Toolkit 소유. 설치 버전, 원본 커밋, Profile·Stack·Skill·역할·워크플로·Adapter 버전과 관리 파일 SHA-256을 기록합니다. 텍스트 줄바꿈을 LF로 정규화하여 검증합니다. |
| `.agent-toolkit/GUIDE.md` | Toolkit 소유. 규칙과 선택된 Skill·역할·워크플로의 안내입니다. |
| `AGENTS.md`, `CLAUDE.md`, 도구별 파일 | 생성한 파일만 Lock으로 관리합니다. 기존 루트 지침은 프로젝트가 관리합니다. |
| `.agent-toolkit/project-rules.md`, `.agent-toolkit/handoffs/`, `docs/` | 프로젝트 소유. 필요한 문서만 별도로 만듭니다. |

공통 규칙, Profile, Stack, 프로젝트 전용 규칙, 작업 지침 순으로 구체화합니다. 필수 보안 정책과 승인 범위는 모든 작업에 적용합니다. `agent-toolkit document create PROJECT-RULES`로 프로젝트 확장을 기록할 수 있습니다. `SPEC`, `ARCHITECTURE`, `BACKLOG`, `TESTING`, `DECISIONS`, `SECURITY`, `RUNBOOK` 템플릿도 같은 명령으로 생성합니다.

## AI 도구 연결

| 도구 | 읽는 지침 | 선택한 Skills | 역할 생성 |
| --- | --- | --- | --- |
| Codex | `AGENTS.md` | `.agents/skills/` | `.codex/agents/toolkit-*.toml` |
| Claude Code | 공통 안내를 가져오는 `CLAUDE.md` | `.claude/skills/` | `.claude/agents/toolkit-*.md` |
| Grok Build | `AGENTS.md` | `.grok/skills/` | 공통 역할 Markdown |
| Generic | `AGENTS.md` 또는 `.agent-toolkit/GUIDE.md` 직접 전달 | `.agent-toolkit/skills/` | 공통 역할 Markdown |

공통 역할 자료는 `.agent-toolkit/agents/`에 생성됩니다. 사용 중인 클라이언트의 기존 우선 지침(예를 들어 Codex의 `AGENTS.override.md`)과 작업 권한을 확인합니다. Codex 역할의 읽기 범위는 지침이며 런타임 권한은 부모 설정을 따릅니다. Claude Code의 읽기 전용 역할은 `Read, Grep, Glob`으로 도구를 지정합니다. Toolkit은 Hooks나 모델 호출을 생성·실행하지 않습니다. [제품 기능 확인 근거](docs/RESEARCH.md)

## 검증 및 안전한 업데이트

```bash
agent-toolkit validate
agent-toolkit status
agent-toolkit changelog
agent-toolkit update --dry-run
agent-toolkit diff
agent-toolkit update --apply
agent-toolkit validate
```

대상 버전은 현재 실행 중인 CLI 버전입니다. 버전이 바뀌면 계획에서 릴리스 노트를 표시합니다. `update` 기본 동작은 미리보기입니다. 관리 파일을 편집했거나 제거했다면 충돌로 표시되며, 미관리 파일과 충돌한 경우에도 변경을 반영하지 않습니다. 변경을 보관한 뒤 프로젝트 규칙이나 다른 파일로 옮기고, 관리 파일은 적용 당시 버전으로 복원해 다시 계획을 검토합니다. `diff`는 체크섬이 검증된 관리 내용의 변경 계획을 표시합니다. `status`와 `diff`는 드리프트나 적용할 변경이 있으면 종료 코드 1을 반환합니다.

변경은 프로젝트별 트랜잭션으로 적용하고 실패 시 보관본을 사용합니다. 중단된 트랜잭션이 표시되면 실행 중인 Toolkit 작업이 없는지 확인한 후 `agent-toolkit recover`로 상태를 보고, `recover --apply`로 복구합니다. 독립적인 수동 변경이 확인되면 파일과 보관본을 남깁니다. Lock과 복구 기록은 출처가 확인된 프로젝트에서 사용합니다. 심볼릭 링크나 junction이 없는 실제 프로젝트 경로와 하드링크 지원 로컬 파일시스템을 사용합니다. 프로젝트에 대한 적대적인 동시 파일 변경과 파일시스템 장애는 실행 환경에서 통제합니다.

`validate`는 프로젝트가 기록한 Lock의 구성 해시와 관리 파일 체크섬을 확인합니다. 설치 CLI와 Lock의 버전이 달라도 이 기준으로 검증할 수 있습니다. 설치 버전에서 바뀔 생성물은 `update --dry-run`으로 확인합니다. CLI는 문서 기준인 필수·선택·적용 불가 Gate를 별도로 표시합니다. 실제 명령을 등록하려면 `agent-toolkit.yml`의 `quality_gates`에 다음처럼 작성합니다.

```yaml
quality_gates:
  optional: [documentation]
  not_applicable: [accessibility]
  commands:
    test-quality:
      - argv: [uv, run, pytest]
        timeout_seconds: 180
```

`code-quality`, `test-quality`, `security`는 기본 필수 기준입니다. 수동 검토는 [TESTING 문서](src/agent_toolkit/resources/templates/TESTING.md)에 기록합니다. 수정한 설정을 `update --apply`로 반영한 뒤 신뢰하는 프로젝트에서만 `validate --run`으로 등록 명령을 실행합니다. 명령은 로컬 사용자 권한 및 환경을 상속합니다. 필수 명령의 실행 실패, 시간 초과 또는 비정상 종료는 종료 코드 1이며, 선택 명령의 실패도 출력에 표시됩니다. Windows에서는 직접 실행할 수 있는 실행 파일을 지정합니다.

## 병렬 작업과 인수인계

```bash
agent-toolkit task plan large
agent-toolkit handoff create feature-login
agent-toolkit worktree create feature/login
agent-toolkit worktree list
agent-toolkit worktree status
agent-toolkit worktree remove feature/login
agent-toolkit worktree remove feature/login --apply
```

역할 계획은 활성 역할에서 필요한 사람만 제안합니다. Critical 작업에는 독립 검증자와 사용자 승인을 적용합니다. 각 작업의 요구, 변경 경로와 검증 근거는 작업 ID별 인수인계에 기록합니다. Worktree는 현재 HEAD를 기준으로 프로젝트 내부에 분리하고, 추적·미추적·무시된 파일에 변경이 있으면 제거를 중단합니다. 제거 후 브랜치를 보존합니다. 외부 Git 필터가 설정된 저장소에서는 자동 worktree 생성과 상태 검사가 차단됩니다. Worktree는 권한 또는 네트워크 격리와 별개의 기능입니다.

## 개발 및 릴리스

```bash
uv sync --locked --python 3.12
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python scripts/export_schemas.py --check
uv run --locked pytest
uv build --no-sources
uv run --locked python scripts/smoke_distribution.py
```

릴리스 후보는 커밋과 변경 이력을 검토한 뒤 `uv run --locked python scripts/build_release.py`로 빌드합니다. 후보는 커밋된 트리에서 만들며 원본 커밋을 패키지에 포함합니다. Git VCS 경로로 설치한 경우 설치 메타데이터의 커밋을 기록합니다. 일반 로컬 소스나 커밋 정보가 없는 wheel은 Lock의 `source_commit`을 `null`로 기록합니다. 버전 태그는 `v<버전>`을 사용하며 원격 공개는 별도로 승인합니다.

- [조사 및 호환성](docs/RESEARCH.md)
- [기능 요구사항](docs/SPEC.md)
- [아키텍처](docs/ARCHITECTURE.md)
- [설계 결정](docs/DECISIONS.md)
- [구현 상태와 로드맵](docs/BACKLOG.md)
- [검증 기록](docs/TESTING.md)
