# 조사 기록

확인일 2026-11-26 (Asia/Seoul). 저장소 라이선스는 GitHub API의 기본 브랜치 커밋과 해당 파일을 대조했다. 외부 코드는 가져오지 않았다.

| 자료 | 확인한 라이선스 | 채택 및 제외 판단 |
| --- | --- | --- |
| [claude-code-tips](https://github.com/ykdojo/claude-code-tips/tree/577ac89252195d61283b334c4b9d292b52c82203) | [All Rights Reserved](https://github.com/ykdojo/claude-code-tips/blob/577ac89252195d61283b334c4b9d292b52c82203/LICENSE) | 작은 작업 분해, 짧은 지침, 컨텍스트 인수인계, worktree, 검증 결과 기록의 운영 아이디어를 검토했다. 팁 문구, DX 플러그인, 스크립트는 가져오지 않았다. |
| [SafeClaw](https://github.com/ykdojo/safeclaw/tree/2527f1bda7cd19ac90e09db300928c85415d6746) | [MIT](https://github.com/ykdojo/safeclaw/blob/2527f1bda7cd19ac90e09db300928c85415d6746/LICENSE) | 세션별 작업 공간이라는 아이디어를 채택했다. 컨테이너 대시보드, 호스트 볼륨 연결, 권한 우회 기본값은 MVP 구성에서 제외했다. |
| [OpenAI Codex](https://github.com/openai/codex/tree/af71942309704997f4bdc86c020717646423c080) | [Apache-2.0](https://github.com/openai/codex/blob/af71942309704997f4bdc86c020717646423c080/LICENSE) | 지침, Skills, 역할을 분리했다. 실제 생성 형식은 제품 문서에서 확인하고 Codex 런타임 의존성은 두지 않는다. |
| [Anthropic Claude Code](https://github.com/anthropics/claude-code/tree/9587741f62205d168459b1be9441fdb901a1b482) | [All Rights Reserved 및 상업 약관](https://github.com/anthropics/claude-code/blob/9587741f62205d168459b1be9441fdb901a1b482/LICENSE.md) | 도구별 진입점과 Markdown 역할 설정 구조를 참고했다. 동작 계약은 공식 문서에서 확인했다. |
| [AGENTS.md](https://github.com/agentsmd/agents.md/tree/d001185d792eb6402a58e4cbef1c228b309ec25d) | [MIT](https://github.com/agentsmd/agents.md/blob/d001185d792eb6402a58e4cbef1c228b309ec25d/LICENSE) | 짧은 루트 안내와 경로별 지침을 채택했다. 계층 적용은 각 도구의 로딩 규칙을 따른다. |
| [Agent Skills](https://github.com/agentskills/agentskills/tree/83021e2be457a9b6679148719c1f6074f0ad975e) | [Apache-2.0](https://github.com/agentskills/agentskills/blob/83021e2be457a9b6679148719c1f6074f0ad975e/LICENSE) | 디렉터리 이름, `SKILL.md` frontmatter, 설명 기반 점진적 로딩을 채택했다. Toolkit 의존 관계는 명세의 문자열 `metadata` 필드에 둔다. [공개 명세](https://agentskills.io/specification) |

## 제품 지원과 Toolkit 출력

- Codex는 루트/하위 `AGENTS.md`, 저장소의 `.agents/skills/`, `.codex/agents/*.toml`을 문서화한다. 역할에는 `name`, `description`, `developer_instructions`를 사용한다. 오래된 예제의 `.codex/skills/` 대신 현행 경로를 쓴다. 프로젝트 Hook도 문서화되어 있으며 별도 신뢰 및 실행 설정이 필요하므로 Toolkit은 생성하지 않는다. [지침](https://learn.chatgpt.com/docs/agent-configuration/agents-md) · [Skills](https://learn.chatgpt.com/docs/build-skills) · [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) · [Hooks](https://learn.chatgpt.com/docs/hooks)
- Claude Code는 `CLAUDE.md`의 상대 `@path` 가져오기, `.claude/skills/`, `.claude/agents/*.md`를 지원한다. 현재 문서에서 `AGENTS.md` 폴백은 v2.1.277부터 지원하며 설정에 좌우된다. Toolkit은 명시적 가져오기를 써서 해당 기본값에 의존하지 않는다. 예전 명령 디렉터리와 실행 Hook은 생성하지 않는다. [메모리](https://code.claude.com/docs/en/memory) · [Skills](https://code.claude.com/docs/en/skills) · [Subagents](https://code.claude.com/docs/en/sub-agents) · [Hooks](https://code.claude.com/docs/en/hooks)
- Grok Build는 `AGENTS.md`, `.grok/skills/`, `.grok/agents/` 및 신뢰 승인으로 실행하는 프로젝트 Hooks를 공식 문서화한다. Toolkit은 루트 안내와 네이티브 Skills를 생성한다. 하위 에이전트 형식과 권한 호환성의 설치본 검증은 MVP 범위를 벗어나므로 역할은 공통 Markdown 계약을 사용한다. 일반 Grok 채팅이나 별도 API 사용자도 Markdown을 읽을 수 있다. [프로젝트 지침](https://docs.x.ai/build/features/project-rules) · [Skills](https://docs.x.ai/build/features/skills-plugins-marketplaces) · [Subagents](https://docs.x.ai/build/features/subagents)
- Generic은 `AGENTS.md`, 공통 가이드, 선택된 Skills 및 역할 Markdown을 직접 읽는 방식이다. 특정 도구의 자동 로딩이나 실행을 전제로 하지 않는다.

## 기술 선택

| 선택 | 근거 |
| --- | --- |
| Python 3.12+, `argparse` | 필수 명령, 하위 명령, 도움말, 반환 코드에 표준 라이브러리가 충분하다. Typer 런타임 의존성을 추가하지 않는다. [Python](https://docs.python.org/3.12/library/argparse.html) |
| uv와 uv_build | 개발 잠금, 격리 도구 설치와 wheel 배포를 같은 도구로 검증한다. Python 패키지 안에서 카탈로그 리소스를 배포한다. [도구 설치](https://docs.astral.sh/uv/guides/tools/) · [빌드 백엔드](https://docs.astral.sh/uv/concepts/build-backend/) |
| Pydantic 2, PyYAML | 엄격한 모델과 JSON Schema를 한 원본에서 생성한다. SafeLoader에 중복 키와 별칭 차단을 추가한다. [Pydantic](https://docs.pydantic.dev/latest/concepts/json_schema/) · [PyYAML](https://pyyaml.org/wiki/PyYAMLDocumentation) |
| 내장 문자열 포맷, 정적 Markdown | 동적 템플릿 표현식이 필요 없는 소규모 출력이다. Jinja2와 실행 가능한 외부 템플릿 로딩을 추가하지 않는다. |
| Git, Ruff, pytest, Actions | Git은 조사와 worktree에서 선택적으로 호출한다. Actions는 OS별 테스트를 구성한다. [Git worktree](https://git-scm.com/docs/git-worktree) · [Ruff](https://docs.astral.sh/ruff/) · [pytest](https://docs.pytest.org/en/stable/) · [Actions 매트릭스](https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs) |

릴리스 빌드는 커밋 식별자를 wheel에 기록한다. VCS 설치 시에는 표준 `direct_url.json`의 커밋 ID를 사용한다. CI에서 사용하는 두 Actions는 GitHub 태그의 커밋으로 고정했다. [설치 메타데이터](https://packaging.python.org/en/latest/specifications/direct-url-data-structure/) · [checkout v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1) · [setup-uv v10.4.0](https://github.com/astral-sh/setup-uv/releases/tag/v10.4.0)
