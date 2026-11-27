"""Build deterministic file bytes without accessing the target workspace."""

from .adapters import ADAPTERS, adapter_files
from .catalog import CORE, Resolved, asset, catalog, skill_catalog

GUIDE = ".agent-toolkit/GUIDE.md"
PROJECT_RULES = ".agent-toolkit/project-rules.md"


def guide(resolved: Resolved) -> str:
    data = catalog()
    config = resolved.config
    project = config.project
    sections = [f"# {project.name} 개발 가이드", ""]
    if project.purpose:
        sections += ["## 프로젝트 목적", "", project.purpose, ""]
    sections += [
        f"Profile **{project.profile}** · 구성 **{project.complexity}** · 개발 인원 **{project.team_size}**",
        "",
        "프로젝트 전용 규칙은 필요할 때 `agent-toolkit document create PROJECT-RULES`로 만들고 "
        "`.agent-toolkit/project-rules.md`에 기록한다. 해당 파일이 있으면 함께 읽는다. "
        "공통 → Profile → Stack → 프로젝트 → 작업 순서로 구체화한다. 필수 보안과 승인 범위는 항상 적용한다.",
        "",
    ]
    if project.deployment:
        sections += [f"배포 환경 **{project.deployment}**", ""]
    for title, requirements in (
        ("프로젝트 보안 요구", project.security_requirements),
        ("프로젝트 테스트 요구", project.testing_requirements),
    ):
        if requirements:
            sections += [f"## {title}", "", *(f"- {item}" for item in requirements), ""]
    for section in CORE:
        sections += [f"#{asset(f'core/{section}.md').rstrip()}", ""]
    sections += ["## Profile", "", data.profiles[project.profile].guidance, ""]
    if resolved.stacks:
        sections += ["## 적용 Stack", ""]
        for name in resolved.stacks:
            sections.append(f"- **{name}** — {data.stacks[name].guidance}")
        sections.append("")
    if config.stack_conflict_notes:
        sections += ["## 스택 중첩 근거", ""]
        for key, note in sorted(config.stack_conflict_notes.items()):
            sections.append(f"- **{key}** — {note}")
        sections.append("")
    sections += ["## 품질 Gate", ""]
    for name, level in resolved.gates.items():
        mode = "명령 + 검토" if name in config.quality_gates.commands else "검토"
        if level == "not_applicable":
            mode = "제외"
        sections.append(f"- **{name}** ({level}, {mode}) — {data.gates[name]}")
    sections += [
        "",
        "`agent-toolkit validate`는 관리 파일의 상태를 검사한다. "
        "`validate --run`은 검토하고 승인한 로컬 명령을 실행한다.",
        "",
    ]
    if resolved.skills:
        sections += ["## Skills", "", "작업에 맞는 설명을 확인한 뒤 해당 Skill만 읽는다.", ""]
        root = ADAPTERS[config.tools[0]].skill_root
        relative = (
            root.removeprefix(".agent-toolkit/")
            if root.startswith(".agent-toolkit/")
            else f"../{root}"
        )
        for name in resolved.skills:
            description = skill_catalog()[name].spec.description
            sections.append(f"- [{name}]({relative}/{name}/SKILL.md) — {description}")
        sections.append("")
    if resolved.agents:
        sections += [
            "## 역할",
            "",
            "과업의 규모와 파일 범위에 따라 선택한다.",
            "",
            *(f"- [{name}](agents/{name}.md)" for name in resolved.agents),
            "",
        ]
    if resolved.workflows:
        sections += [
            "## 워크플로",
            "",
            *(f"- [{name}](workflows/{name}.md)" for name in resolved.workflows),
            "",
        ]
    return "\n".join(sections)


def render(resolved: Resolved, preserved: set[str]) -> dict[str, bytes]:
    result = adapter_files(resolved)
    result[GUIDE] = guide(resolved).encode("utf-8")
    if "AGENTS.md" not in preserved:
        result["AGENTS.md"] = (
            asset("templates/AGENTS.md").format(name=resolved.config.project.name).encode("utf-8")
        )
    if "claude" in resolved.config.tools and "CLAUDE.md" not in preserved:
        result["CLAUDE.md"] = asset("templates/CLAUDE.md").format(guide=GUIDE).encode("utf-8")
    for name in resolved.workflows:
        result[f".agent-toolkit/workflows/{name}.md"] = asset(f"workflows/{name}.md").encode(
            "utf-8"
        )
    return result
