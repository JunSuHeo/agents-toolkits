"""Read local Git metadata and manage only Toolkit-created worktree locations."""

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .files import no_transaction, read_file, safe_path, write_exclusive
from .models import ToolkitError

WORKTREES = ".agent-toolkit-worktrees"
IGNORE = b"*\n"


def find_executable(name: str) -> str | None:
    # Use absolute PATH entries to avoid implicit execution from the project directory.
    for entry in os.get_exec_path():
        directory = Path(entry)
        if directory.is_absolute():
            if result := shutil.which(str(directory / name)):
                return result
    return None


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    command = find_executable("git")
    if not command:
        raise ToolkitError("Git is required for worktree commands")
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", LC_ALL="C")
    with tempfile.TemporaryDirectory(prefix="agent-toolkit-no-hooks-") as empty_hooks:
        result = subprocess.run(
            [
                command,
                "-c",
                f"core.hooksPath={empty_hooks}",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "submodule.recurse=false",
                *args,
            ],
            cwd=root,
            env=env,
            capture_output=True,
            timeout=120,
            check=False,
        )
    if check and result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ToolkitError(f"Git {args[0]} exited {result.returncode}: {detail}")
    return result


def output(result: subprocess.CompletedProcess) -> str:
    return os.fsdecode(result.stdout).rstrip("\r\n")


def checkout_root(root: Path) -> Path | None:
    if not root.is_dir() or not find_executable("git"):
        return None
    location = git(root, "rev-parse", "--show-toplevel", check=False)
    return Path(output(location)).resolve() if location.returncode == 0 else None


def check_filters(root: Path) -> None:
    # Attributes can activate a configured process on stat refresh or checkout.
    filters = git(
        root,
        "config",
        "--name-only",
        "--get-regexp",
        r"^filter\..*\.(clean|smudge|process)$",
        check=False,
    )
    if filters.returncode != 1:
        raise ToolkitError(
            "Git status and worktree checkout require a repository without external filters"
        )


def git_state(root: Path, *, ignored: bool = False) -> str:
    check_filters(root)
    args = ["status", "--porcelain=v1", "-z", "--untracked-files=all"]
    if ignored:
        args.append("--ignored=matching")
    return "dirty" if git(root, *args).stdout else "clean"


def head(root: Path) -> tuple[str, str]:
    if checkout_root(root) is None:
        return ("—", "—")
    branch = git(root, "symbolic-ref", "--short", "-q", "HEAD", check=False)
    commit = git(root, "rev-parse", "--verify", "HEAD", check=False)
    return (output(branch) or "detached", output(commit) or "unborn")


@dataclass(frozen=True)
class Worktree:
    path: Path
    branch: str | None
    head: str | None


def worktrees(root: Path) -> list[Worktree]:
    if checkout_root(root) != root:
        raise ToolkitError("Run worktree commands at the checkout root")
    data = output(git(root, "worktree", "list", "--porcelain", "-z"))
    result = []
    for stanza in data.split("\0\0"):
        fields = dict(
            (key, value)
            for line in stanza.split("\0")
            if line
            for key, _, value in [line.partition(" ")]
        )
        if "worktree" in fields:
            branch = fields.get("branch", "").removeprefix("refs/heads/") or None
            result.append(Worktree(Path(fields["worktree"]), branch, fields.get("HEAD")))
    return result


def worktree_relative(branch: str) -> str:
    if len(branch) > 160 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", branch):
        raise ToolkitError("Use a branch with portable letters, digits, dots, dashes or slashes")
    label = re.sub(r"[^a-z0-9]+", "-", branch.lower()).strip("-")[:32]
    suffix = hashlib.sha256(branch.encode()).hexdigest()[:12]
    return f"{WORKTREES}/{label}-{suffix}"


def create_worktree(root: Path, branch: str) -> tuple[Path, str]:
    no_transaction(root)
    existing = worktrees(root)
    relative = worktree_relative(branch)
    git(root, "check-ref-format", f"refs/heads/{branch}")
    if any(item.branch == branch for item in existing):
        raise ToolkitError(f"Branch is already checked out: {branch}")
    git(root, "rev-parse", "--verify", "HEAD")
    state = git_state(root)
    storage = safe_path(root, WORKTREES, directory=True)
    ignore = read_file(root, f"{WORKTREES}/.gitignore")
    if storage.exists() and ignore != IGNORE:
        raise ToolkitError(f"Existing unmanaged worktree storage: {WORKTREES}")
    target = safe_path(root, relative, directory=True)
    if target.exists():
        raise ToolkitError(f"Worktree path already exists: {relative}")
    if ignore is None:
        storage.mkdir()
        write_exclusive(safe_path(root, f"{WORKTREES}/.gitignore"), IGNORE)
    git(root, "worktree", "add", "-b", branch, "--", str(target), "HEAD")
    return target, state


def remove_worktree(root: Path, branch: str, *, apply: bool) -> Path:
    no_transaction(root)
    entries = worktrees(root)
    relative = worktree_relative(branch)
    target = safe_path(root, relative, directory=True)
    if read_file(root, f"{WORKTREES}/.gitignore") != IGNORE:
        raise ToolkitError("Toolkit worktree storage marker is missing")
    if not target.is_dir() or not any(
        item.path.resolve() == target and item.branch == branch for item in entries
    ):
        raise ToolkitError(f"No Toolkit worktree matches: {branch}")
    if git_state(target, ignored=True) != "clean":
        raise ToolkitError("Worktree has dirty, untracked or ignored files. Preserve them first")
    if apply:
        git(root, "worktree", "remove", "--", str(target))
    return target
