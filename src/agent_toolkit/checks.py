"""Execute only explicitly requested local quality commands."""

import os
import subprocess
from pathlib import Path

from .catalog import Resolved
from .git_ops import find_executable


def command_path(root: Path, command: str) -> str | None:
    path = Path(command)
    if path.is_absolute() or "/" in command or "\\" in command:
        result = str(root / path)
    else:
        result = find_executable(command)
    if result and os.name == "nt" and Path(result).suffix.lower() in {".bat", ".cmd"}:
        return None
    return result


def quality(root: Path, resolved: Resolved, *, run: bool) -> tuple[list[str], bool]:
    lines = []
    success = True
    commands = resolved.config.quality_gates.commands
    for gate, level in resolved.gates.items():
        if level == "not_applicable":
            lines.append(f"{gate} ({level}): excluded")
        elif gate not in commands:
            lines.append(f"{gate} ({level}): manual review")
        elif not run:
            lines.append(f"{gate} ({level}): {len(commands[gate])} command(s) configured")
        else:
            for index, item in enumerate(commands[gate], 1):
                label = f"{gate} ({level}) #{index}"
                executable = command_path(root, item.argv[0])
                if executable is None:
                    lines.append(f"{label}: executable unavailable or requires a batch shell")
                    success = success and level != "required"
                    continue
                try:
                    result = subprocess.run(
                        [executable, *item.argv[1:]],
                        cwd=root,
                        stdin=subprocess.DEVNULL,
                        timeout=item.timeout_seconds,
                        check=False,
                    )
                    lines.append(f"{label}: exit {result.returncode}")
                    success = success and (result.returncode == 0 or level != "required")
                except subprocess.TimeoutExpired:
                    lines.append(f"{label}: timed out after {item.timeout_seconds}s")
                    success = success and level != "required"
                except OSError:
                    lines.append(f"{label}: executable could not start")
                    success = success and level != "required"
    return lines, success
