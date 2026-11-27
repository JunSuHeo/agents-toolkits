import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from agent_toolkit import files
from agent_toolkit.cli import main


def call(root, *args):
    return main([*args, "--path", str(root)])


def checkout(path):
    git = shutil.which("git")
    if git is None:
        pytest.skip("Git unavailable")
    path.mkdir(exist_ok=True)
    subprocess.run([git, "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run([git, "config", "core.autocrlf", "false"], cwd=path, check=True)
    (path / ".gitignore").write_bytes(b"ignored.log\n")
    (path / "app.txt").write_bytes(b"Version one\n")
    subprocess.run([git, "add", "."], cwd=path, check=True)
    subprocess.run(
        [
            git,
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "user.name=Tester",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "first",
        ],
        cwd=path,
        check=True,
    )
    return git


def test_user_owned_handoffs_and_documents(tmp_path):
    checkout(tmp_path)
    assert call(tmp_path, "init", "--profile", "backend-api") == 0
    assert call(tmp_path, "handoff", "create", "task-one") == 0
    assert call(tmp_path, "handoff", "create", "task-two") == 0
    assert call(tmp_path, "handoff", "create", "task-one") == 1
    first = tmp_path / ".agent-toolkit/handoffs/task-one.md"
    second = tmp_path / ".agent-toolkit/handoffs/task-two.md"
    assert first.read_bytes() == second.read_bytes()
    assert "`main`" in first.read_text(encoding="utf-8")
    assert call(tmp_path, "document", "create", "PROJECT-RULES") == 0
    own_rules = tmp_path / ".agent-toolkit/project-rules.md"
    own_rules.write_text("Custom rules\n", encoding="utf-8")
    assert call(tmp_path, "document", "create", "PROJECT-RULES") == 1
    assert call(tmp_path, "document", "create", "SPEC") == 0
    assert call(tmp_path, "validate") == 0
    assert own_rules.read_text(encoding="utf-8") == "Custom rules\n"
    assert call(tmp_path, "task", "plan", "critical") == 0


def test_critical_requires_separate_verifier(tmp_path, capsys):
    assert call(tmp_path, "init", "--agents", "orchestrator,qa") == 0
    assert call(tmp_path, "task", "plan", "critical", "--role", "qa") == 1
    assert "independent human reviewer" in capsys.readouterr().out
    assert call(tmp_path, "task", "plan", "small") == 0
    assert "Selected roles: orchestrator" in capsys.readouterr().out


def test_worktree_requires_clean_status_to_remove(tmp_path, capsys, monkeypatch):
    # Keep the fixture independent of runner configuration such as system Git LFS.
    config = tmp_path / "fixture.gitconfig"
    config.touch()
    isolation = {"GIT_CONFIG_GLOBAL": str(config), "GIT_CONFIG_NOSYSTEM": "1"}
    run = subprocess.run

    def run_with_fixture_config(args, **kwargs):
        env = kwargs.get("env") or os.environ
        return run(args, **(kwargs | {"env": env | isolation}))

    monkeypatch.setattr(subprocess, "run", run_with_fixture_config)
    root = tmp_path / "checkout"
    git = checkout(root)
    subprocess.run([git, "config", "filter.fixture.clean", "fixture-filter"], cwd=root, check=True)
    assert call(root, "worktree", "create", "feature/login") == 1
    assert "without external filters" in capsys.readouterr().err
    subprocess.run([git, "config", "--remove-section", "filter.fixture"], cwd=root, check=True)
    assert call(root, "worktree", "create", "../unsafe") == 1
    original = (root / "app.txt").read_bytes()
    (root / "app.txt").write_bytes(b"Local uncommitted change")
    assert call(root, "worktree", "create", "feature/login") == 0
    assert "source checkout was dirty" in capsys.readouterr().out
    (target,) = [path for path in (root / ".agent-toolkit-worktrees").iterdir() if path.is_dir()]
    assert (target / "app.txt").read_bytes() == original
    assert call(root, "worktree", "status") == 0
    assert "feature/login" in capsys.readouterr().out
    ignored = target / "ignored.log"
    ignored.touch()
    assert call(root, "worktree", "remove", "feature/login", "--apply") == 1
    assert ignored.exists()
    ignored.unlink()
    (target / "app.txt").write_bytes(b"Worktree changes")
    assert call(root, "worktree", "remove", "feature/login", "--apply") == 1
    (target / "app.txt").write_bytes(original)
    assert call(root, "worktree", "remove", "feature/login") == 0
    assert target.exists()
    assert call(root, "worktree", "remove", "feature/login", "--apply") == 0
    assert not target.exists()
    subprocess.run([git, "show-ref", "--verify", "refs/heads/feature/login"], cwd=root, check=True)
    assert (root / "app.txt").read_bytes() == b"Local uncommitted change"


def test_files_rollback_after_error_during_update(tmp_path, monkeypatch):
    assert call(tmp_path, "init", "--profile", "frontend", "--tools", "codex,claude") == 0
    cfg_path = tmp_path / "agent-toolkit.yml"
    cfg = yaml.safe_load(cfg_path.read_bytes())
    cfg["project"]["name"] = "changed project"
    cfg["tools"] = ["generic"]
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    publish = files.installed

    def fail_final(stage_file: Path, target: Path, *, replace: bool) -> None:
        if target.name == "toolkit.lock" and stage_file.suffix == ".after":
            raise OSError("simulated publication error")
        publish(stage_file, target, replace=replace)

    with monkeypatch.context() as patch:
        patch.setattr(files, "installed", fail_final)
        assert call(tmp_path, "update", "--apply") == 1
    assert not (tmp_path / files.TRANSACTION).exists()
    assert before == {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert call(tmp_path, "update", "--apply") == 0
    assert call(tmp_path, "validate") == 0


def test_recover_interrupted_exclusive_publication(tmp_path):
    stage = tmp_path / files.TRANSACTION
    stage.mkdir()
    new = b"new agent instructions\n"
    staging_file = stage / "0.after"
    staging_file.write_bytes(new)
    try:
        os.link(staging_file, tmp_path / "AGENTS.md")
    except OSError:
        pytest.skip("Creating hard links is unavailable")
    journal = files.Journal(
        entries=[files.JournalEntry(path="AGENTS.md", before=None, after=files.checksum(new))]
    )
    (stage / "journal.json").write_text(journal.model_dump_json(), encoding="utf-8")
    assert call(tmp_path, "recover") == 0
    assert (tmp_path / "AGENTS.md").exists()
    assert call(tmp_path, "recover", "--apply") == 0
    assert not (tmp_path / "AGENTS.md").exists()
    assert not stage.exists()


def test_recovery_does_not_overwrite_concurrent_user_change(tmp_path):
    stage = tmp_path / files.TRANSACTION
    stage.mkdir()
    (stage / "0.before").write_bytes(b"original")
    (tmp_path / "AGENTS.md").write_bytes(b"user edit")
    journal = files.Journal(
        entries=[
            files.JournalEntry(
                path="AGENTS.md",
                before=files.checksum(b"original"),
                after=files.checksum(b"generated"),
            )
        ]
    )
    (stage / "journal.json").write_text(journal.model_dump_json(), encoding="utf-8")
    assert call(tmp_path, "recover", "--apply") == 1
    assert (tmp_path / "AGENTS.md").read_bytes() == b"user edit"
    assert (stage / "0.before").read_bytes() == b"original"
