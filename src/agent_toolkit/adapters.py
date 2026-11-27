"""Translate portable assets into project-scoped tool formats."""

import json
from dataclasses import dataclass

import yaml

from .catalog import Resolved, agent_catalog, skill_catalog
from .models import Agent


@dataclass(frozen=True)
class Adapter:
    skill_root: str
    native_roles: str | None = None
    version: int = 1


ADAPTERS = {
    "generic": Adapter(".agent-toolkit/skills"),
    "codex": Adapter(".agents/skills", ".codex/agents"),
    "claude": Adapter(".claude/skills", ".claude/agents"),
    "grok": Adapter(".grok/skills"),
}


def role_body(name: str, agent: Agent) -> str:
    return f"""# {name}

{agent.description}

- **호출 조건** — {agent.trigger}
- **입력** — {agent.input}
- **읽기 범위** — {agent.scope}
- **허용 도구** — {agent.tools}
- **변경 범위** — {agent.changes}
- **검증 책임** — {agent.verification}

도구의 실제 권한과 사용자가 지정한 범위를 적용한다. 비밀 열람, 범위 밖 쓰기,
승인 없는 외부 호출·운영 변경은 금지한다. 프로젝트의 공통 보안 규칙을 확인한다.

상위 작업자에게 작업 ID, 변경 또는 검토 경로, 검증 명령과 실제 결과,
실패 및 미검증 범위, 다음 조치와 승인 필요 여부를 보고한다.
"""


def codex_role(name: str, agent: Agent, body: str) -> str:
    values = {
        "name": f"toolkit-{name}",
        "description": agent.description,
        "developer_instructions": body,
    }
    return "".join(
        f"{key} = {json.dumps(value, ensure_ascii=False)}\n" for key, value in values.items()
    )


def claude_role(name: str, agent: Agent, body: str) -> str:
    values = {"name": f"toolkit-{name}", "description": agent.description}
    if agent.read_only:
        values["tools"] = "Read, Grep, Glob"
    front = yaml.safe_dump(values, allow_unicode=True, sort_keys=False, width=10000)
    return f"---\n{front}---\n\n{body}"


def adapter_files(resolved: Resolved) -> dict[str, bytes]:
    result = {}
    tools = resolved.config.tools
    for tool in tools:
        adapter = ADAPTERS[tool]
        for name in resolved.skills:
            result[f"{adapter.skill_root}/{name}/SKILL.md"] = skill_catalog()[name].content

    for name in resolved.agents:
        agent = agent_catalog()[name]
        body = role_body(name, agent)
        result[f".agent-toolkit/agents/{name}.md"] = body.encode("utf-8")
        if "codex" in tools:
            root = ADAPTERS["codex"].native_roles
            result[f"{root}/toolkit-{name}.toml"] = codex_role(name, agent, body).encode("utf-8")
        if "claude" in tools:
            root = ADAPTERS["claude"].native_roles
            result[f"{root}/toolkit-{name}.md"] = claude_role(name, agent, body).encode("utf-8")
    return result
