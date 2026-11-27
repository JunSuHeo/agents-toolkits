"""Build release candidates from the committed tree and embed its Git identity."""

import io
import subprocess
import tarfile
import tempfile
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=root, check=True)
    revision = subprocess.check_output(["git", "rev-parse", "--verify", "HEAD"], cwd=root).decode()
    archive = subprocess.check_output(
        ["git", "archive", "--format=tar", revision.strip()], cwd=root
    )
    with tempfile.TemporaryDirectory(prefix="agent-toolkit-release-") as temporary:
        sources = Path(temporary)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(sources, filter="data")
        marker = sources / "src/agent_toolkit/_source_commit.txt"
        marker.write_text(revision, encoding="ascii")
        subprocess.run(
            ["uv", "build", "--no-sources", "--out-dir", str(root / "dist")],
            cwd=sources,
            check=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
