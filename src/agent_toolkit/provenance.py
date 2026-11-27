"""Version and source identity for released and VCS-installed toolkits."""

import json
import re
from importlib.metadata import distribution
from pathlib import Path

DIST = distribution("agent-toolkit")
VERSION = DIST.version


def source_commit() -> str | None:
    # VCS installers write PEP 610 metadata next to the wheel's distribution metadata.
    if direct_url := DIST.read_text("direct_url.json"):
        try:
            commit = json.loads(direct_url).get("vcs_info", {}).get("commit_id")
        except (ValueError, AttributeError):
            commit = None
        if isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
            return commit
    # Release workflows can package a verified Git revision before building.
    path = Path(__file__).with_name("_source_commit.txt")
    if path.is_file():
        commit = path.read_text(encoding="utf-8").strip()
        if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit):
            return commit
    return None
