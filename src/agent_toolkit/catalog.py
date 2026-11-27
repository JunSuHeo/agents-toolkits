"""Resolve project choices against the catalog shipped in the wheel."""

from dataclasses import dataclass
from functools import cache
from importlib.resources import files

from pydantic import Field, TypeAdapter

from .models import (
    Agent,
    Identifier,
    Model,
    Profile,
    ProjectConfig,
    Skill,
    Text,
    ToolkitError,
    load_yaml,
    validated,
)

RESOURCES = files("agent_toolkit").joinpath("resources")
CORE = ("security", "development", "verification", "collaboration")
REQUIRED_GATES = ("code-quality", "test-quality", "security")


class Stack(Model):
    description: Text
    guidance: Text
    requires: list[Identifier] = Field(default_factory=list)


class StackConflict(Model):
    stacks: list[Identifier]
    reason: Text


class Catalog(Model):
    standard_skills: list[Identifier]
    extended_skills: list[Identifier]
    profiles: dict[Identifier, Profile]
    stacks: dict[Identifier, Stack]
    gates: dict[Identifier, Text]
    conflicts: list[StackConflict]


@dataclass(frozen=True)
class SkillAsset:
    spec: Skill
    content: bytes

    @property
    def dependencies(self) -> list[str]:
        value = self.spec.metadata.get("toolkit-dependencies", "")
        return value.split(",") if value else []


@dataclass(frozen=True)
class Resolved:
    config: ProjectConfig
    stacks: tuple[str, ...]
    skills: tuple[str, ...]
    agents: tuple[str, ...]
    workflows: tuple[str, ...]
    gates: dict[str, str]
    notes: tuple[str, ...]


def asset(path: str) -> str:
    return RESOURCES.joinpath(*path.split("/")).read_text(encoding="utf-8")


@cache
def catalog() -> Catalog:
    return validated(Catalog, load_yaml(asset("catalog.yml"), "catalog.yml"), "catalog")


@cache
def agent_catalog() -> dict[str, Agent]:
    return TypeAdapter(dict[Identifier, Agent]).validate_python(
        load_yaml(asset("agents.yml"), "agent catalog")
    )


@cache
def skill_catalog() -> dict[str, SkillAsset]:
    result = {}
    for folder in sorted(RESOURCES.joinpath("skills").iterdir(), key=lambda item: item.name):
        if not folder.is_dir():
            continue
        body = folder.joinpath("SKILL.md").read_text(encoding="utf-8").replace("\r\n", "\n")
        front = body.split("---\n", 2)
        if len(front) != 3 or front[0] or not front[2].strip():
            raise ToolkitError(f"Missing skill frontmatter or body: {folder.name}")
        spec = validated(Skill, load_yaml(front[1], folder.name), folder.name)
        if spec.name != folder.name:
            raise ToolkitError(f"Skill name must match its directory: {folder.name}")
        result[spec.name] = SkillAsset(spec, body.encode("utf-8"))
    return result


def lookup(items: dict, name: str, category: str):
    if name not in items:
        raise ToolkitError(f"Unknown {category}: {name}. Choose from: {', '.join(items)}")
    return items[name]


def without_duplicates(values: list[str], label: str) -> list[str]:
    if len(set(values)) != len(values):
        raise ToolkitError(f"Duplicate entries in {label}")
    return values


def expand(selected, entries: dict, label: str, requirements) -> tuple[str, ...]:
    resolved: dict[str, None] = {}

    def visit(name: str, chain: tuple[str, ...] = ()) -> None:
        if name in chain:
            raise ToolkitError(f"Cyclic {label} dependency: {' → '.join((*chain, name))}")
        if name not in resolved:
            for item in requirements(lookup(entries, name, label)):
                visit(item, (*chain, name))
            resolved[name] = None

    for name in selected:
        visit(name)
    return tuple(resolved)


def quality_gates(config: ProjectConfig, profile: Profile, available: dict[str, str]) -> dict:
    gates = config.quality_gates
    levels = {name: "required" for name in REQUIRED_GATES}
    specified = set()
    for level in ("required", "optional", "not_applicable"):
        for name in without_duplicates(getattr(gates, level), f"quality_gates.{level}"):
            lookup(available, name, "quality gate")
            if name in specified or (name in REQUIRED_GATES and level != "required"):
                raise ToolkitError(f"Conflicting quality gate classification: {name}")
            specified.add(name)
            levels[name] = level

    for name in profile.gates:
        lookup(available, name, "quality gate")
        levels.setdefault(name, "optional")

    for name, commands in gates.commands.items():
        lookup(available, name, "quality gate")
        if name not in levels or levels[name] == "not_applicable" or not commands:
            raise ToolkitError(f"Commands require an applicable gate and a nonempty list: {name}")
    for name in available:
        levels.setdefault(name, "not_applicable")
    return levels


def resolve(config: ProjectConfig) -> Resolved:
    entries = catalog()
    project = config.project
    profile = lookup(entries.profiles, project.profile, "profile")
    without_duplicates(config.tools, "tools")
    stacks = expand(
        without_duplicates(config.stacks, "stacks"), entries.stacks, "stack", lambda s: s.requires
    )
    conflict_keys = set()
    notes = []
    for conflict in entries.conflicts:
        key = "+".join(sorted(conflict.stacks))
        if set(conflict.stacks).issubset(stacks):
            conflict_keys.add(key)
            if not config.stack_conflict_notes.get(key, "").strip():
                raise ToolkitError(f"Stack conflict ({key}): {conflict.reason}")
            notes.append(f"Stack overlap declared for {key}")
    if unused := config.stack_conflict_notes.keys() - conflict_keys:
        raise ToolkitError(f"Unused stack_conflict_notes keys: {', '.join(sorted(unused))}")

    agents = config.agents.enabled
    if agents is None:
        agents = ["orchestrator"]
        if project.multi_agent != "off" and (
            project.multi_agent == "on" or project.complexity != "minimal"
        ):
            agents = list(dict.fromkeys([*agents, *profile.agents]))
            if project.complexity == "extended":
                agents = list(dict.fromkeys([*agents, "architect", "reviewer", "security"]))
    for name in without_duplicates(agents, "agents.enabled"):
        lookup(agent_catalog(), name, "agent")
    if project.multi_agent == "off" and len(agents) > 1:
        raise ToolkitError("multi_agent=off conflicts with multiple enabled agents")
    if project.multi_agent == "on" and len(agents) < 2:
        raise ToolkitError("multi_agent=on requires at least two enabled agents")

    selected = config.skills.enabled
    if selected is None:
        selected = ["testing-verification"]
        if project.complexity != "minimal":
            selected = list(dict.fromkeys([*entries.standard_skills, *profile.skills]))
        if project.complexity == "extended":
            extras = ["parallel-development"] if len(agents) > 1 else []
            selected = list(dict.fromkeys([*selected, *entries.extended_skills, *extras]))
    skills = expand(
        without_duplicates(selected, "skills.enabled"),
        skill_catalog(),
        "skill",
        lambda s: s.dependencies,
    )
    levels = quality_gates(config, profile, entries.gates)
    workflows = ()
    if project.complexity == "standard":
        workflows = tuple(dict.fromkeys(["bug-fix", *profile.workflows]))
    elif project.complexity == "extended":
        workflows = tuple(
            sorted(
                item.name.removesuffix(".md")
                for item in RESOURCES.joinpath("workflows").iterdir()
                if item.name.endswith(".md")
            )
        )
    return Resolved(config, stacks, skills, tuple(agents), workflows, levels, tuple(notes))


def entries_for(category: str) -> dict[str, str]:
    if category == "skills":
        return {name: item.spec.description for name, item in skill_catalog().items()}
    if category == "agents":
        return {name: item.description for name, item in agent_catalog().items()}
    return {name: item.description for name, item in getattr(catalog(), category).items()}


@dataclass(frozen=True)
class TaskRoles:
    selected: tuple[str, ...]
    verifier: str | None = None


def roles_for(resolved: Resolved, size: str, specialist: str | None) -> TaskRoles:
    active = resolved.agents
    if specialist and specialist not in active:
        raise ToolkitError(f"Role is not enabled: {specialist}")
    lead = ("orchestrator",) if "orchestrator" in active else active[:1]
    if size == "small":
        return TaskRoles((specialist,) if specialist else lead)
    planners = ("architect",) if size in {"large", "critical"} else ()
    validators = ("qa", "reviewer", "security") if size == "critical" else ("qa", "reviewer")
    implementer = specialist or next(
        (
            role
            for role in active
            if role not in (*lead, *validators) and not agent_catalog()[role].read_only
        ),
        None,
    )
    verifier = next(
        (
            role
            for role in (("security", *validators) if size == "critical" else validators)
            if role in active and role not in (*lead, implementer)
        ),
        None,
    )
    selected = tuple(
        dict.fromkeys(role for role in (*lead, *planners, implementer, verifier) if role in active)
    )
    return TaskRoles(selected, verifier)
