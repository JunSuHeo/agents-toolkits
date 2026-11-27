"""Install a release wheel into a temporary uv tools directory and verify project setup."""

import argparse
import json
import os
import subprocess
import tempfile
import tomllib
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect-commit")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    wheel = root / "dist" / f"agent_toolkit-{version}-py3-none-any.whl"
    with tempfile.TemporaryDirectory(prefix="agent-toolkit-smoke-") as temporary:
        directory = Path(temporary).resolve()
        env = os.environ | {
            "UV_TOOL_DIR": str(directory / "tools"),
            "UV_TOOL_BIN_DIR": str(directory / "bin"),
            "PYTHONUTF8": "1",
        }
        subprocess.run(
            ["uv", "tool", "install", "--python", "3.12", str(wheel)], env=env, check=True
        )
        executable = (
            directory / "bin" / ("agent-toolkit.exe" if os.name == "nt" else "agent-toolkit")
        )
        target = directory / "project"
        common = {"cwd": directory, "env": env, "check": True}
        subprocess.run([str(executable), "doctor"], **common)
        subprocess.run(
            [
                str(executable),
                "init",
                "--path",
                str(target),
                "--profile",
                "web-service",
                "--tools",
                "codex,claude,grok,generic",
                "--stack",
                "nextjs,supabase",
            ],
            **common,
        )
        subprocess.run([str(executable), "validate", "--path", str(target)], **common)
        lock = json.loads((target / "toolkit.lock").read_bytes())
        if args.expect_commit and lock["source_commit"] != args.expect_commit:
            raise SystemExit(f"Wheel lost source provenance: {lock['source_commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
