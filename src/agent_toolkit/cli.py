"""Command-line entry points for local project operations."""

import argparse
import platform
import subprocess
import sys
from pathlib import Path

from . import git_ops
from .catalog import asset, entries_for, resolve, roles_for
from .checks import quality
from .files import (
    CONFIG,
    LOCK,
    TRANSACTION,
    directory_for,
    lstat,
    no_transaction,
    project_root,
    read_file,
    read_path,
    recover,
    write_exclusive,
)
from .inspection import Inspection, inspect
from .models import ProjectConfig, ToolkitError, is_identifier, validated
from .project import (
    config_from,
    describe,
    diff,
    plan_project,
    read_config,
    reject_downgrade,
    verify_installed,
)
from .provenance import VERSION
from .render import PROJECT_RULES

TOOLS = ("codex", "claude", "grok", "generic")
TEMPLATES = (
    "SPEC",
    "ARCHITECTURE",
    "BACKLOG",
    "TESTING",
    "DECISIONS",
    "SECURITY",
    "RUNBOOK",
    "PROJECT-RULES",
)
SIZES = ("small", "medium", "large", "critical")


def print_lines(lines) -> None:
    for line in lines:
        print(line)


def csv_items(value: str) -> list[str]:
    items = [item.strip() for item in value.split(",")]
    if any(not item for item in items):
        raise ToolkitError("Expected a comma-separated list of nonempty names")
    return items


def configuration(
    root: Path, args: argparse.Namespace, discovery: Inspection | None
) -> ProjectConfig | None:
    options = (
        "name",
        "purpose",
        "profile",
        "complexity",
        "team_size",
        "deployment",
        "multi_agent",
        "stack",
        "tools",
        "skills",
        "agents",
        "security_requirement",
        "testing_requirement",
    )
    overrides = any(getattr(args, key) is not None for key in options)
    if args.config is not None:
        if overrides:
            raise ToolkitError("Use either --config or individual project options")
        source = args.config.absolute()
        data = read_path(source)
        if data is None:
            raise ToolkitError(f"Configuration file was not found: {source}")
        return config_from(data, str(source))
    if read_file(root, CONFIG) is not None and not overrides:
        return None

    profile = (
        args.profile if args.profile is not None else discovery.profile if discovery else "minimal"
    )
    complexity = args.complexity or ("minimal" if profile == "minimal" else "standard")
    project = {
        "name": args.name if args.name is not None else root.name or "project",
        "profile": profile,
        "complexity": complexity,
    }
    for attribute in ("purpose", "team_size", "deployment", "multi_agent"):
        if (value := getattr(args, attribute)) is not None:
            project[attribute] = value
    for kind in ("security", "testing"):
        if (items := getattr(args, f"{kind}_requirement")) is not None:
            project[f"{kind}_requirements"] = items
    stacks = discovery.stacks if discovery else []
    if args.stack is not None:
        stacks = csv_items(args.stack) if args.stack else []
    data = {
        "project": project,
        "stacks": stacks,
        "tools": csv_items(args.tools) if args.tools is not None else ["generic"],
    }
    for name in ("agents", "skills"):
        if (raw := getattr(args, name)) is not None:
            data[name] = {"enabled": csv_items(raw) if raw else []}
    return validated(ProjectConfig, data, "project options")


def initialize(root: Path, args: argparse.Namespace) -> int:
    discovery = None
    if args.command == "adopt":
        if not root.is_dir():
            raise ToolkitError("Adopt requires an existing project directory")
        discovery = inspect(root)
        print_lines(discovery.lines)
    plan = plan_project(root, configuration(root, args, discovery), operation=args.command)
    print_lines(describe(plan))
    if plan.conflicts:
        return 1
    if args.dry_run or (args.command == "adopt" and not args.apply):
        print(
            "Preview only"
            + (". Use adopt --apply to write files" if args.command == "adopt" else "")
        )
        return 0
    plan.apply(root)
    print("Applied. Run agent-toolkit validate in the project")
    return 0


def validate_project(root: Path, args: argparse.Namespace) -> int:
    selection, record, conflicts = verify_installed(root)
    if conflicts:
        print_lines(f"CONFLICT {conflict}" for conflict in conflicts)
        return 1
    print(f"Verified locked Toolkit {record.toolkit_version} configuration and managed files")
    lines, ok = quality(root, selection, run=args.run)
    print_lines(lines)
    return 0 if ok else 1


def installed_project(root: Path, args: argparse.Namespace) -> int:
    if args.command == "status":
        if read_file(root, LOCK) is None:
            print(f"Unmanaged project: {LOCK} is missing")
            return 1
    plan = plan_project(root, None, operation="update")
    print_lines(describe(plan))
    if args.command == "diff":
        print(diff(plan), end="")
    if plan.conflicts:
        return 1
    if args.command == "update":
        reject_downgrade(plan)
        if args.apply:
            plan.apply(root)
            print("Applied and verified")
        else:
            print("Preview only. Use update --apply to write files")
        return 0
    return 1 if plan.changes else 0


def list_catalog(_: Path, args: argparse.Namespace) -> int:
    query = args.search.casefold() if args.search else ""
    for name, description in entries_for(args.category).items():
        if query in f"{name} {description}".casefold():
            print(f"{name:<22} {description}")
    return 0


def show_inspection(root: Path, args: argparse.Namespace) -> int:
    result = inspect(root, suggest_rules=args.suggest_rules)
    print_lines(result.lines)
    return 0 if root.is_dir() else 1


def doctor(_: Path, __: argparse.Namespace) -> int:
    print(f"Agent Toolkit {VERSION} · Python {platform.python_version()} · {platform.system()}")
    entries_for("profiles")
    entries_for("stacks")
    entries_for("skills")
    entries_for("agents")
    print("Packaged catalog available")
    for command in ("git", "uv", "codex", "claude", "grok"):
        print(f"{command}: {git_ops.find_executable(command) or 'not found (optional)'}")
    return 0


def changelog(_: Path, __: argparse.Namespace) -> int:
    print(asset("CHANGELOG.md"), end="")
    return 0


def worktree_command(root: Path, args: argparse.Namespace) -> int:
    if args.action == "create":
        path, origin_state = git_ops.create_worktree(root, args.branch)
        print(
            f"Created {args.branch} at {path} (source checkout was {origin_state}; forked from HEAD)"
        )
    elif args.action == "remove":
        path = git_ops.remove_worktree(root, args.branch, apply=args.apply)
        print(f"Removed {path}; branch retained" if args.apply else f"Remove {path} with --apply")
    else:
        for item in git_ops.worktrees(root):
            status = ""
            if args.action == "status":
                state = git_ops.git_state(item.path) if item.path.is_dir() else "missing"
                status = f" · {state}"
            print(f"{item.branch or '(detached)'} · {item.head or '—'} · {item.path}{status}")
    return 0


def seed_user_document(root: Path, relative: str, text: str) -> None:
    no_transaction(root)
    if not root.is_dir():
        raise ToolkitError("Document creation requires an existing project directory")
    target = directory_for(root, relative, [])
    try:
        write_exclusive(target, text.encode("utf-8"))
    except FileExistsError as exc:
        raise ToolkitError(f"Existing user-owned document: {relative}") from exc
    print(f"Created {relative}")


def document_command(root: Path, args: argparse.Namespace) -> int:
    path = PROJECT_RULES if args.template == "PROJECT-RULES" else f"docs/{args.template}.md"
    seed_user_document(root, path, asset(f"templates/{args.template}.md"))
    return 0


def handoff_command(root: Path, args: argparse.Namespace) -> int:
    if not is_identifier(args.task_id):
        raise ToolkitError("Use a lowercase task ID such as feature-login")
    branch, commit = git_ops.head(root)
    text = asset("templates/HANDOFF.md").format(
        git_context=f"- 브랜치: `{branch}`\n- 기준 커밋: `{commit}`"
    )
    seed_user_document(root, f".agent-toolkit/handoffs/{args.task_id}.md", text)
    return 0


def task_command(root: Path, args: argparse.Namespace) -> int:
    selection = resolve(read_config(root))
    roles = roles_for(selection, args.size, args.role)
    print("Selected roles: " + (", ".join(roles.selected) or "none"))
    if roles.verifier:
        print(f"Independent verification: {roles.verifier}")
    print("Record scope and evidence in a task handoff")
    if args.size in {"large", "critical"}:
        print("Assign non-overlapping paths, split independent worktrees and verify integration")
    if args.size == "critical":
        print("Require independent verification and explicit approval before high-risk actions")
        if not roles.verifier:
            print("Enable a separate verifier or assign an independent human reviewer")
            return 1
    return 0


def recovery_command(root: Path, args: argparse.Namespace) -> int:
    print(recover(root, apply=args.apply))
    return 0


def add_path(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--path", type=Path, help="Explicit target project directory")


def apply_options(parser: argparse.ArgumentParser) -> None:
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true", help="Show the plan without writing")
    modes.add_argument("--apply", action="store_true", help="Apply the displayed plan")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="agent-toolkit", description="Local, model-independent development harness"
    )
    root.add_argument("--version", action="version", version=VERSION)
    commands = root.add_subparsers(dest="command", required=True)

    def add(name, help_text, run, *, path=True):
        command = commands.add_parser(name, help=help_text)
        command.set_defaults(run_command=run)
        if path:
            add_path(command)
        return command

    for name, help_text in (
        ("init", "Generate a toolkit for a new project"),
        ("adopt", "Inspect and preview adoption in an existing project"),
    ):
        cmd = add(name, help_text, initialize)
        apply_options(cmd)
        cmd.add_argument(
            "--allow-nested",
            action="store_true",
            help="Allow a separate project within a managed project",
        )
        cmd.add_argument("--config", type=Path, help="Use a separate YAML configuration as input")
        cmd.add_argument("--profile", help="Project type (see list profiles)")
        cmd.add_argument("--complexity", choices=("minimal", "standard", "extended"))
        cmd.add_argument("--stack", help="Comma-separated technology stacks")
        cmd.add_argument("--tools", help=f"Comma-separated AI tools ({', '.join(TOOLS)})")
        cmd.add_argument("--skills", help="Comma-separated enabled skill IDs (empty for none)")
        cmd.add_argument("--agents", help="Comma-separated enabled role IDs (empty for none)")
        cmd.add_argument("--multi-agent", choices=("auto", "off", "on"))
        cmd.add_argument("--name", help="Project display name")
        cmd.add_argument("--purpose", help="Project purpose")
        cmd.add_argument("--team-size", type=int)
        cmd.add_argument("--deployment", help="Deployment environment")
        cmd.add_argument("--security-requirement", action="append")
        cmd.add_argument("--testing-requirement", action="append")

    scan = add("inspect", "Find project and Git signals without writing", show_inspection)
    scan.add_argument(
        "--suggest-rules", action="store_true", help="Print draft rules with evidence"
    )
    verify = add("validate", "Verify project configuration and checksums", validate_project)
    verify.add_argument("--run", action="store_true", help="Run trusted local quality commands")
    add("status", "Show the recorded and desired project state", installed_project)
    add("doctor", "Check the local environment and packaged catalog", doctor, path=False)
    add("changelog", "Read the installed release notes", changelog, path=False)
    update = add("update", "Preview regeneration with the installed toolkit", installed_project)
    apply_options(update)
    add("diff", "Show desired changes to verified managed files", installed_project)
    recover_cmd = add(
        "recover", "Inspect or recover an interrupted Toolkit transaction", recovery_command
    )
    recover_cmd.add_argument(
        "--apply", action="store_true", help="Recover when no writer is running"
    )

    listing = add("list", "List or search the packaged catalog", list_catalog, path=False)
    listing.add_argument("category", choices=("profiles", "stacks", "skills", "agents"))
    listing.add_argument("--search", help="Match a name or description")

    tree = add("worktree", "Manage project-local Git worktrees", worktree_command, path=False)
    tree_commands = tree.add_subparsers(dest="action", required=True)
    for action in ("create", "list", "status", "remove"):
        cmd = tree_commands.add_parser(action)
        add_path(cmd)
        if action in {"create", "remove"}:
            cmd.add_argument("branch")
        if action == "remove":
            cmd.add_argument("--apply", action="store_true", help="Remove the clean worktree")

    handoff = add("handoff", "Create a user-owned handoff by task ID", handoff_command, path=False)
    handoff_create = handoff.add_subparsers(dest="action", required=True).add_parser("create")
    handoff_create.add_argument("task_id")
    add_path(handoff_create)

    docs = add("document", "Create a user-owned project document", document_command, path=False)
    doc_create = docs.add_subparsers(dest="action", required=True).add_parser("create")
    doc_create.add_argument("template", choices=TEMPLATES)
    add_path(doc_create)

    task = add("task", "Prepare a task strategy without launching agents", task_command, path=False)
    task_plan = task.add_subparsers(dest="action", required=True).add_parser("plan")
    task_plan.add_argument("size", choices=SIZES)
    task_plan.add_argument("--role", help="Name a specialist who is enabled in this project")
    add_path(task_plan)
    return root


def managed_ancestor(root: Path) -> Path | None:
    for directory in (root, *root.parents):
        if any(lstat(directory / marker) is not None for marker in (LOCK, TRANSACTION)):
            return directory
        if lstat(directory / ".git") is not None:
            break
    return None


def command_root(args: argparse.Namespace) -> Path:
    cwd = Path.cwd()
    if not hasattr(args, "path"):
        return cwd
    root = project_root(args.path if args.path is not None else cwd)
    if args.command in {"init", "adopt"} and not args.allow_nested:
        parent = managed_ancestor(root)
        if parent is not None and parent != root:
            raise ToolkitError(
                f"Parent Toolkit project: {parent}. Use --allow-nested for an independent project"
            )
    if args.path is None and args.command in {
        "status",
        "validate",
        "diff",
        "update",
        "recover",
        "task",
    }:
        return managed_ancestor(root) or root
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        target = command_root(args)
        return args.run_command(target, args)
    except (ToolkitError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
