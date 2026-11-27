"""Build a plan from the catalog, current files and their recorded ownership."""

import json
from dataclasses import dataclass, field
from difflib import unified_diff
from pathlib import Path

import yaml

from .adapters import ADAPTERS
from .catalog import Resolved, asset, resolve
from .files import CONFIG, LOCK, Change, checksum, execute, is_managed, no_transaction, read_file
from .models import ProjectConfig, ToolkitError, ToolkitLock, load_json, load_yaml, validated
from .provenance import VERSION, source_commit
from .render import GUIDE, render

ENTRYPOINTS = {"AGENTS.md", "CLAUDE.md"}


def text_checksum(data: bytes) -> str:
    # Git may materialize text as CRLF on another machine.
    return checksum(data.replace(b"\r\n", b"\n"))


@dataclass
class Plan:
    resolved: Resolved
    target: ToolkitLock
    current: ToolkitLock | None
    preserved: set[str]
    observed: dict[str, bytes | None] = field(default_factory=dict)
    changes: list[Change] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    def apply(self, root: Path) -> None:
        if self.conflicts:
            raise ToolkitError("Resolve the listed conflicts before applying")
        execute(root, self.changes, self.observed)


def canonical_config(config: ProjectConfig) -> bytes:
    # Include semantic defaults and sort mapping keys independently of YAML formatting.
    data = config.model_dump(mode="json")
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def dump_config(config: ProjectConfig) -> bytes:
    data = config.model_dump(mode="json", exclude_defaults=True)
    # Important defaults stay visible so a project owner has an editable starting point.
    data["schema_version"] = config.schema_version
    data["project"]["profile"] = config.project.profile
    data["project"]["complexity"] = config.project.complexity
    data["stacks"] = config.stacks
    data["tools"] = config.tools
    ordered = {key: data[key] for key in ("schema_version", "project", "stacks", "tools")}
    ordered.update(data)
    return yaml.safe_dump(ordered, allow_unicode=True, sort_keys=False).encode("utf-8")


def config_from(data: bytes, location: str = CONFIG) -> ProjectConfig:
    return validated(ProjectConfig, load_yaml(data, location), location)


def read_config(root: Path) -> ProjectConfig:
    data = read_file(root, CONFIG)
    if data is None:
        raise ToolkitError(f"{CONFIG} is missing. Run init or adopt first")
    return config_from(data)


def lock_from(data: bytes) -> ToolkitLock:
    lock = validated(ToolkitLock, load_json(data, LOCK), LOCK)
    if GUIDE not in lock.managed_files or any(not is_managed(path) for path in lock.managed_files):
        raise ToolkitError("Lock contains an invalid managed path or is missing its managed guide")
    if len({p.casefold() for p in lock.managed_files}) != len(lock.managed_files):
        raise ToolkitError("Lock contains case-conflicting paths")
    allowed = {GUIDE, "AGENTS.md"}
    if "claude" in lock.adapters:
        allowed.add("CLAUDE.md")
    for tool in lock.adapters:
        adapter = ADAPTERS[tool]
        allowed.update(f"{adapter.skill_root}/{name}/SKILL.md" for name in lock.skills)
        if adapter.native_roles:
            extension = "toml" if tool == "codex" else "md"
            allowed.update(
                f"{adapter.native_roles}/toolkit-{name}.{extension}" for name in lock.agents
            )
    allowed.update(f".agent-toolkit/agents/{name}.md" for name in lock.agents)
    allowed.update(f".agent-toolkit/workflows/{name}.md" for name in lock.workflows)
    if lock.managed_files.keys() - allowed:
        raise ToolkitError("Lock lists a path outside its recorded selection")
    return lock


def managed_conflict(path: str, content: bytes | None, expected: str) -> str | None:
    if content is None:
        return f"Missing managed file: {path}"
    if text_checksum(content) != expected:
        return f"User-modified managed file: {path}"
    return None


def verify_installed(root: Path) -> tuple[Resolved, ToolkitLock, list[str]]:
    no_transaction(root)
    data = read_file(root, LOCK)
    if data is None:
        raise ToolkitError(f"{LOCK} is missing. Run init or adopt first")
    record = lock_from(data)
    config = read_config(root)
    conflicts = []
    if checksum(canonical_config(config)) != record.config_sha256:
        conflicts.append("Configuration changed. Review update --dry-run")
    for path, expected in record.managed_files.items():
        if conflict := managed_conflict(path, read_file(root, path), expected):
            conflicts.append(conflict)
    return resolve(config), record, conflicts


def make_lock(resolved: Resolved, files: dict[str, bytes]) -> ToolkitLock:
    config = resolved.config
    return ToolkitLock(
        toolkit_version=VERSION,
        source_commit=source_commit(),
        config_sha256=checksum(canonical_config(config)),
        profile=config.project.profile,
        stacks=list(resolved.stacks),
        skills=list(resolved.skills),
        agents=list(resolved.agents),
        workflows=list(resolved.workflows),
        adapters={tool: ADAPTERS[tool].version for tool in sorted(config.tools)},
        managed_files={name: text_checksum(data) for name, data in sorted(files.items())},
    )


def plan_project(root: Path, config: ProjectConfig | None, *, operation: str) -> Plan:
    no_transaction(root)
    config_data = read_file(root, CONFIG)
    lock_data = read_file(root, LOCK)
    current = lock_from(lock_data) if lock_data is not None else None
    if operation == "update":
        if current is None or config_data is None:
            raise ToolkitError(f"Update requires {CONFIG} and {LOCK}")
        config = config_from(config_data)
    else:
        if current is not None:
            raise ToolkitError("Project is already managed. Use status or update")
        if config_data is not None:
            if config is not None:
                raise ToolkitError(f"{CONFIG} already exists. Use it without overriding options")
            config = config_from(config_data)
    if config is None:
        raise ToolkitError("Project configuration is required")
    resolved = resolve(config)
    previous = current.managed_files if current else {}
    preserved = {
        name for name in ENTRYPOINTS if name not in previous and read_file(root, name) is not None
    }
    desired = render(resolved, preserved)
    if not all(is_managed(path) for path in desired):
        raise ToolkitError("Adapter attempted to generate outside the managed file namespace")
    target = make_lock(resolved, desired)
    # Keep the original release provenance on equivalent regenerations. A wheel installed
    # via another route can know less about the source of otherwise identical content.
    if current and target.model_dump(exclude={"source_commit"}) == current.model_dump(
        exclude={"source_commit"}
    ):
        target = current
    plan = Plan(resolved, target, current, preserved, {CONFIG: config_data, LOCK: lock_data})
    for path in sorted(set(previous) | set(desired) | ENTRYPOINTS):
        before = read_file(root, path) if path in previous or path in desired else None
        if path not in previous and path not in desired:
            continue
        after = desired.get(path)
        plan.observed[path] = before
        conflict = managed_conflict(path, before, previous[path]) if path in previous else None
        if conflict:
            plan.conflicts.append(conflict)
        elif path not in previous and before is not None:
            plan.conflicts.append(f"Existing unmanaged file: {path}")
        elif before is None or after is None or text_checksum(before) != text_checksum(after):
            plan.changes.append(Change(path, before, after))

    if config_data is None:
        plan.changes.insert(0, Change(CONFIG, None, dump_config(config)))
    target_lock = (target.model_dump_json(indent=2) + "\n").encode("utf-8")
    if target != current:
        plan.changes.append(Change(LOCK, lock_data, target_lock))
    return plan


def describe(plan: Plan) -> list[str]:
    old = plan.current.toolkit_version if plan.current else "unmanaged"
    selection = plan.resolved
    lines = [
        f"Toolkit: {old} → {plan.target.toolkit_version}",
        f"Profile: {plan.target.profile} ({selection.config.project.complexity})",
        "Stacks: " + (", ".join(selection.stacks) or "none"),
        "Tools: " + ", ".join(selection.config.tools),
        "Skills: " + (", ".join(selection.skills) or "none"),
        "Roles: " + (", ".join(selection.agents) or "none"),
    ]
    if plan.current and plan.current.toolkit_version != plan.target.toolkit_version:
        lines.append("Installed Toolkit release notes:")
        lines.extend(asset("CHANGELOG.md").strip().splitlines())
    lines.extend(f"NOTE   {note}" for note in selection.notes)
    for path in sorted(plan.preserved):
        if path == "AGENTS.md" or "claude" in selection.config.tools:
            lines.append(f"KEEP   {path} (link to .agent-toolkit/GUIDE.md from your instructions)")
    for item in plan.changes:
        action = "CREATE" if item.before is None else "REMOVE" if item.after is None else "UPDATE"
        lines.append(f"{action:<6} {item.path}")
    lines.extend(f"CONFLICT {conflict}" for conflict in plan.conflicts)
    if not plan.changes and not plan.conflicts:
        lines.append("Up to date")
    return lines


def diff(plan: Plan) -> str:
    return "".join(
        "".join(
            unified_diff(
                (item.before or b"").decode("utf-8", errors="replace").splitlines(keepends=True),
                (item.after or b"").decode("utf-8").splitlines(keepends=True),
                fromfile=f"a/{item.path}" if item.before is not None else "/dev/null",
                tofile=f"b/{item.path}" if item.after is not None else "/dev/null",
            )
        )
        for item in plan.changes
    )


def reject_downgrade(plan: Plan) -> None:
    if plan.current:
        version = tuple(map(int, plan.current.toolkit_version.split(".")))
        target = tuple(map(int, plan.target.toolkit_version.split(".")))
        if target < version:
            raise ToolkitError(
                "Downgrade is unsupported. Use the installed or a newer toolkit version"
            )
