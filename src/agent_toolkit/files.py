"""Project boundary checks and recoverable, serialized file changes."""

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from .models import Digest, Model, ToolkitError, load_json, validated

CONFIG = "agent-toolkit.yml"
LOCK = "toolkit.lock"
TRANSACTION = ".agent-toolkit-transaction"
MAX_BYTES = 1024 * 1024
SLUG_PART = r"[a-z0-9]+(?:-[a-z0-9]+)*"
MANAGED = re.compile(
    rf"AGENTS\.md|CLAUDE\.md|\.agent-toolkit/GUIDE\.md"
    rf"|\.agent-toolkit/(?:agents|workflows)/{SLUG_PART}\.md"
    rf"|\.(?:agent-toolkit|agents|claude|grok)/skills/{SLUG_PART}/SKILL\.md"
    rf"|\.codex/agents/toolkit-{SLUG_PART}\.toml|\.claude/agents/toolkit-{SLUG_PART}\.md"
)
COMPONENT = re.compile(r"[A-Za-z0-9_.-]+")
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"{p}{n}" for p in ("COM", "LPT") for n in range(10))}


def is_managed(relative: str) -> bool:
    return len(relative) <= 256 and MANAGED.fullmatch(relative) is not None


def checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def lstat(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def is_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def project_root(path: Path) -> Path:
    path = path.absolute()
    for ancestor in (*reversed(path.parents), path):
        info = lstat(ancestor)
        if info and (is_link(info) or not stat.S_ISDIR(info.st_mode)):
            raise ToolkitError(f"Project path must use real directories: {ancestor}")
    return path.resolve()


def safe_path(
    root: Path, relative: str, *, directory: bool = False, allow_hardlink: bool = False
) -> Path:
    """Require a portable literal path and reject every link below the project root."""
    parts = relative.split("/")
    if any(
        not COMPONENT.fullmatch(part)
        or part.endswith(".")
        or part.split(".")[0].upper() in RESERVED
        for part in parts
    ):
        raise ToolkitError(f"Unsafe project path: {relative!r}")
    root_info = lstat(root)
    if root_info and (is_link(root_info) or not stat.S_ISDIR(root_info.st_mode)):
        raise ToolkitError("Project root changed or is a link")
    current = root
    for index, part in enumerate(parts):
        if lstat(current):
            for sibling in current.iterdir():
                if sibling.name.casefold() == part.casefold() and sibling.name != part:
                    raise ToolkitError(f"Path casing conflicts with {sibling.relative_to(root)}")
        current /= part
        info = lstat(current)
        if info is None:
            continue
        if is_link(info):
            raise ToolkitError(
                f"Link or reparse point in project path: {current.relative_to(root)}"
            )
        if directory or index < len(parts) - 1:
            if not stat.S_ISDIR(info.st_mode):
                raise ToolkitError(f"Expected a directory: {current.relative_to(root)}")
        elif not stat.S_ISREG(info.st_mode) or (info.st_nlink != 1 and not allow_hardlink):
            raise ToolkitError(f"Expected a regular file without hard links: {relative}")
    return current


def read_file(root: Path, relative: str) -> bytes | None:
    return read_path(safe_path(root, relative))


def read_path(path: Path) -> bytes | None:
    info = lstat(path)
    if info is None:
        return None
    if is_link(info) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ToolkitError(f"Expected a regular file without links: {path.name}")
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
        fd = os.open(path, flags)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_BYTES:
            raise ToolkitError(f"Unsupported file type, size, or hard link: {path.name}")
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ToolkitError(f"Project file exceeds {MAX_BYTES} bytes: {path.name}")
    return data


def no_transaction(root: Path) -> None:
    if safe_path(root, TRANSACTION, directory=True).exists():
        raise ToolkitError("Pending transaction. Use recover after confirming no writer is running")


def write_exclusive(path: Path, contents: bytes) -> None:
    # The caller validates the path and creates parents.
    with path.open("xb") as stream:
        stream.write(contents)
        stream.flush()
        os.fsync(stream.fileno())


@dataclass(frozen=True)
class Change:
    path: str
    before: bytes | None
    after: bytes | None


class JournalEntry(Model):
    path: str
    before: Digest | None
    after: Digest | None


class Journal(Model):
    entries: list[JournalEntry]


def digest(data: bytes | None) -> str | None:
    return checksum(data) if data is not None else None


def installed(stage_file: Path, target: Path, *, replace: bool) -> None:
    if replace:
        os.replace(stage_file, target)
    else:
        # Exclusive and atomic publication, including when a file appears after planning.
        os.link(stage_file, target)
        stage_file.unlink()


def directory_for(root: Path, relative: str, created: list[Path]) -> Path:
    path = safe_path(root, relative)
    missing = []
    parent = path.parent
    while parent != root and not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for directory in reversed(missing):
        directory.mkdir()
        created.append(directory)
    return safe_path(root, relative)


def precheck(root: Path, expected: dict[str, bytes | None]) -> None:
    for relative, data in expected.items():
        if read_file(root, relative) != data:
            raise ToolkitError(f"Changed since planning: {relative}")


def clean_stage(root: Path, names: set[str]) -> None:
    stage = safe_path(root, TRANSACTION, directory=True)
    if extras := {entry.name for entry in stage.iterdir()} - names:
        raise ToolkitError(f"Unexpected data in transaction directory: {', '.join(sorted(extras))}")
    for name in sorted(names - {"journal.json", "settled"}):
        safe_path(root, f"{TRANSACTION}/{name}").unlink(missing_ok=True)
    # Keep the completion marker until the backups and journal are removed.
    safe_path(root, f"{TRANSACTION}/journal.json").unlink(missing_ok=True)
    safe_path(root, f"{TRANSACTION}/settled").unlink(missing_ok=True)
    stage.rmdir()


def stage_names(count: int) -> set[str]:
    return {"journal.json", "settled"} | {
        f"{index}.{suffix}" for index in range(count) for suffix in ("before", "after", "restore")
    }


def remove_empty(dirs: list[Path]) -> None:
    for directory in reversed(dirs):
        try:
            directory.rmdir()
        except OSError:
            continue


def rollback(root: Path, journal: Journal) -> None:
    # Read all snapshots before restoring any file. A subsequent recovery can resume.
    pending = []
    for index, entry in reversed(list(enumerate(journal.entries))):
        finish_interrupted_publication(root, index, entry)
        current = digest(read_file(root, entry.path))
        if current == entry.before:
            continue
        if current != entry.after:
            raise ToolkitError(f"Recovery conflict, file changed independently: {entry.path}")
        backup = f"{TRANSACTION}/{index}.before"
        content = read_file(root, backup) if entry.before is not None else None
        if digest(content) != entry.before:
            raise ToolkitError(f"Missing or invalid backup for {entry.path}")
        pending.append((index, entry, content))

    for index, entry, content in pending:
        target = safe_path(root, entry.path)
        if digest(read_file(root, entry.path)) != entry.after:
            raise ToolkitError(f"Recovery conflict, file changed independently: {entry.path}")
        if content is None:
            target.unlink()
        else:
            restore = safe_path(root, f"{TRANSACTION}/{index}.restore")
            restore.unlink(missing_ok=True)
            write_exclusive(restore, content)
            backup = safe_path(root, f"{TRANSACTION}/{index}.before")
            restore.chmod(stat.S_IMODE(backup.stat().st_mode))
            installed(restore, target, replace=entry.after is not None)


def finish_interrupted_publication(root: Path, index: int, entry: JournalEntry) -> None:
    """Drop the verified staging link if a process stopped just after exclusive publication."""
    if entry.before is not None and entry.after is not None:
        return
    suffix = "after" if entry.before is None else "restore"
    temporary = safe_path(root, f"{TRANSACTION}/{index}.{suffix}", allow_hardlink=True)
    target = safe_path(root, entry.path, allow_hardlink=True)
    staging_info = lstat(temporary)
    target_info = lstat(target)
    if staging_info and target_info and staging_info.st_nlink == target_info.st_nlink == 2:
        if os.path.samestat(staging_info, target_info):
            temporary.unlink()


def execute(root: Path, changes: list[Change], expected: dict[str, bytes | None]) -> None:
    if not changes:
        return
    root.mkdir(parents=True, exist_ok=True)
    stage = safe_path(root, TRANSACTION, directory=True)
    try:
        stage.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise ToolkitError("A Toolkit transaction already exists") from exc
    dirs: list[Path] = []
    names = stage_names(len(changes))
    journal = Journal(
        entries=[
            JournalEntry(path=item.path, before=digest(item.before), after=digest(item.after))
            for item in changes
        ]
    )
    prepared = False
    applied: list[JournalEntry] = []
    try:
        precheck(root, expected)
        for index, change in enumerate(changes):
            if change.before is not None:
                backup = stage / f"{index}.before"
                write_exclusive(backup, change.before)
                backup.chmod(stat.S_IMODE(safe_path(root, change.path).stat().st_mode))
            if change.after is not None:
                staged = stage / f"{index}.after"
                write_exclusive(staged, change.after)
                if change.before is not None:
                    staged.chmod(stat.S_IMODE((stage / f"{index}.before").stat().st_mode))
        write_exclusive(stage / "journal.json", journal.model_dump_json().encode())
        prepared = True
        snapshots = dict(expected)
        for index, change in enumerate(changes):
            if change.path == LOCK:
                precheck(root, snapshots)
            target = directory_for(root, change.path, dirs)
            precheck(root, {change.path: change.before})
            applied.append(journal.entries[index])
            if change.after is None:
                target.unlink()
            else:
                installed(stage / f"{index}.after", target, replace=change.before is not None)
            snapshots[change.path] = change.after
        precheck(root, snapshots)
        write_exclusive(stage / "settled", b"applied\n")
    except BaseException as exc:
        try:
            # Keep original entry indexes so backup names still match.
            if prepared and applied:
                rollback(root, Journal(entries=journal.entries[: len(applied)]))
            clean_stage(root, names)
            remove_empty(dirs)
        except (OSError, ToolkitError) as restore_error:
            raise ToolkitError(
                f"Transaction interrupted. Backups remain in {TRANSACTION}: {restore_error}"
            ) from exc
        raise
    # A failure to clean an already committed plan leaves a recoverable marker.
    clean_stage(root, names)


def recover(root: Path, *, apply: bool) -> str:
    stage = safe_path(root, TRANSACTION, directory=True)
    if not stage.exists():
        return "No pending transaction"
    data = read_file(root, f"{TRANSACTION}/journal.json")
    settled = read_file(root, f"{TRANSACTION}/settled")
    journal = None
    if data is not None:
        journal = validated(Journal, load_json(data, "transaction journal"), "transaction journal")
        paths = [entry.path for entry in journal.entries]
        if len(paths) != len(set(paths)) or not all(
            path in {CONFIG, LOCK} or is_managed(path) for path in paths
        ):
            raise ToolkitError("Unexpected path in transaction journal")
    names = stage_names(len(journal.entries)) if journal else {"journal.json", "settled"}
    if journal is None and settled is None:
        # Planning completed no writes: the journal is published before any target change.
        names.update(
            path.name
            for path in stage.iterdir()
            if re.fullmatch(r"[0-9]+\.(before|after)", path.name)
        )
    will_rollback = journal is not None and settled != b"applied\n"
    if settled not in (None, b"applied\n", b"rolled-back\n"):
        raise ToolkitError("Invalid transaction marker")
    if settled == b"rolled-back\n":
        will_rollback = False
    if not apply:
        return ("Pending rollback" if will_rollback else "Pending transaction cleanup") + (
            "; use recover --apply when no other writer is running"
        )
    if will_rollback and journal is not None:
        rollback(root, journal)
        write_exclusive(stage / "settled", b"rolled-back\n")
    clean_stage(root, names)
    return "Transaction recovered"
