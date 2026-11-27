import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

from agent_toolkit.cli import main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def call(root, command, *options):
    return main([command, "--path", str(root), *map(str, options)])


def lock(root):
    return json.loads((root / "toolkit.lock").read_bytes())


def snapshot(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


@pytest.mark.parametrize(
    ("example", "profile", "stacks", "signals"),
    [
        (
            "web-service",
            "web-service",
            {"react", "nextjs", "typescript", "postgresql", "supabase"},
            {
                ".agents/skills/code-review/SKILL.md",
                "CLAUDE.md",
                ".claude/agents/toolkit-frontend.md",
            },
        ),
        (
            "ai-agent",
            "ai-agent",
            {"python", "fastapi", "langgraph", "postgresql"},
            {".grok/skills/security-audit/SKILL.md", ".codex/agents/toolkit-ai-engineer.toml"},
        ),
        (
            "data-pipeline",
            "data-pipeline",
            {"rust", "oracle"},
            {".agent-toolkit/agents/database.md"},
        ),
        (
            "backend-api",
            "backend-api",
            {"java", "spring-boot", "oracle", "docker"},
            {".claude/agents/toolkit-backend.md"},
        ),
        (
            "automation",
            "automation",
            {"python"},
            {".agent-toolkit/skills/testing-verification/SKILL.md"},
        ),
    ],
)
def test_examples(example, profile, stacks, signals, tmp_path):
    root = tmp_path / "target"
    source = EXAMPLES / f"{example}.yml"
    assert call(root, "init", "--config", source, "--dry-run") == 0
    assert not root.exists()
    assert call(root, "init", "--config", source) == 0
    assert call(root, "validate") == 0
    record = lock(root)
    assert record["schema_version"] == 1
    assert record["profile"] == profile
    assert set(record["stacks"]) == stacks
    assert signals <= record["managed_files"].keys()
    for file in root.glob(".codex/agents/*.toml"):
        agent = tomllib.loads(file.read_text(encoding="utf-8"))
        assert agent.keys() == {"name", "description", "developer_instructions"}
        assert agent["name"] == file.stem
    for file in root.glob(".claude/agents/*.md"):
        front = yaml.safe_load(file.read_text(encoding="utf-8").split("---\n", 2)[1])
        assert front["name"] == file.stem
    if profile == "automation":
        assert record["agents"] == ["orchestrator"]
        assert not (root / "docs").exists()
        assert not (root / ".agent-toolkit/workflows").exists()


def test_selective_skills_and_determinism(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    for root in (first, second):
        assert (
            call(
                root,
                "init",
                "--name",
                "same",
                "--profile",
                "web-service",
                "--skills",
                "parallel-development",
                "--tools",
                "codex,claude,grok,generic",
            )
            == 0
        )
        assert lock(root)["skills"] == ["task-decomposition", "handoff", "parallel-development"]
    assert snapshot(first) == snapshot(second)
    expected = lock(first)["skills"]
    for path in (".agents", ".claude", ".grok", ".agent-toolkit"):
        candidates = sorted(root.name for root in (first / path / "skills").iterdir())
        assert candidates == sorted(expected)


def test_adopt_existing_preserves_originals_and_applies_changed_selection(tmp_path, capsys):
    root = tmp_path / "existing"
    shutil.copytree(EXAMPLES / "existing", root)
    (root / "CLAUDE.md").write_bytes(b"# Original Claude memory\n")
    modified = root / "previous-user-edit.md"
    modified.write_bytes(b"Uncommitted existing material\n")
    before = snapshot(root)
    assert call(root, "inspect") == 0
    report = capsys.readouterr().out
    for signal in ("AGENTS.md", ".github/workflows", "requirements.txt", "tests"):
        assert signal in report
    assert call(root, "adopt", "--tools", "codex,claude") == 0
    assert snapshot(root) == before
    assert call(root, "adopt", "--tools", "codex,claude", "--apply") == 0
    assert {path: snapshot(root)[path] for path in before} == before
    assert "AGENTS.md" not in lock(root)["managed_files"]
    assert "CLAUDE.md" not in lock(root)["managed_files"]
    assert call(root, "validate") == 0
    config_path = root / "agent-toolkit.yml"
    config = yaml.safe_load(config_path.read_bytes())
    config["project"]["purpose"] = "Revised purpose"
    config["tools"] = ["generic"]
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    preview = snapshot(root)
    assert call(root, "status") == 1
    assert call(root, "update", "--dry-run") == 0
    assert snapshot(root) == preview
    capsys.readouterr()
    assert call(root, "diff") == 1
    assert "+Revised purpose" in capsys.readouterr().out
    assert call(root, "update", "--apply") == 0
    assert call(root, "validate") == 0
    assert not (root / ".claude/agents/toolkit-orchestrator.md").exists()
    assert {path: snapshot(root)[path] for path in before} == before
    result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=root)
    assert result.returncode == 0


def test_conflict_with_existing_native_skill_blocks_entire_adoption(tmp_path, capsys):
    existing = tmp_path / ".agents/skills/code-review/SKILL.md"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"User-only skill\n")
    before = snapshot(tmp_path)
    assert call(tmp_path, "adopt", "--tools", "codex", "--profile", "web-service", "--apply") == 1
    assert "Existing unmanaged file" in capsys.readouterr().out
    assert snapshot(tmp_path) == before


def test_local_edits_and_missing_managed_files_are_preserved(tmp_path, capsys):
    assert call(tmp_path, "init") == 0
    entry = tmp_path / "AGENTS.md"
    entry.write_bytes(b"Sensitive edited content\n")
    (tmp_path / ".agent-toolkit/agents/orchestrator.md").unlink()
    before = snapshot(tmp_path)
    capsys.readouterr()
    for command, opts in (("diff", []), ("status", []), ("validate", []), ("update", ["--apply"])):
        assert call(tmp_path, command, *opts) == 1
        output = capsys.readouterr().out
        assert "User-modified managed file: AGENTS.md" in output
        assert "Missing managed file:" in output
        assert "Sensitive edited content" not in output
        assert snapshot(tmp_path) == before


def test_existing_config_is_never_reformatted(tmp_path):
    configuration = (
        b"# human notes\nschema_version: 1\nproject: {name: old}\n"
        b"skills: {enabled: []}\nagents: {enabled: []}\n"
    )
    (tmp_path / "agent-toolkit.yml").write_bytes(configuration)
    assert call(tmp_path, "init") == 0
    assert (tmp_path / "agent-toolkit.yml").read_bytes() == configuration
    assert lock(tmp_path)["skills"] == []
    assert lock(tmp_path)["agents"] == []
    assert call(tmp_path, "validate") == 0


def test_cross_platform_checkout_line_endings_are_stable(tmp_path):
    assert call(tmp_path, "init", "--tools", "codex,claude") == 0
    for name in lock(tmp_path)["managed_files"]:
        file = tmp_path / name
        file.write_bytes(file.read_bytes().replace(b"\n", b"\r\n"))
    before = snapshot(tmp_path)
    assert call(tmp_path, "validate") == 0
    assert call(tmp_path, "update", "--apply") == 0
    assert snapshot(tmp_path) == before


def test_declared_stack_overlap_and_protected_quality_gates(tmp_path, capsys):
    assert call(tmp_path, "init", "--stack", "opensearch,elasticsearch") == 1
    assert "Stack conflict" in capsys.readouterr().err
    configuration = tmp_path / "my plans.yml"
    data = {
        "project": {"name": "migration"},
        "stacks": ["opensearch", "elasticsearch"],
        "stack_conflict_notes": {
            "elasticsearch+opensearch": "Dual-read migration, compare results"
        },
        "quality_gates": {"not_applicable": ["security"]},
    }
    configuration.write_text(yaml.safe_dump(data), encoding="utf-8")
    root = tmp_path / "project"
    assert call(root, "init", "--config", configuration) == 1
    assert "Conflicting quality gate classification: security" in capsys.readouterr().err
    del data["quality_gates"]
    configuration.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert call(root, "init", "--config", configuration) == 0
    assert "Stack overlap declared" in capsys.readouterr().out
    assert call(root, "validate") == 0


@pytest.mark.parametrize(
    "data",
    [
        b"project: {name: one, name: two}",
        b"project: &root {name: root, purpose: *root}",
        b"project: !!python/object:example.Class {}",
        b"project: {name: example}\nschema_version: true",
        b"project: {name: example, ignored: true}",
    ],
)
def test_invalid_config_does_not_write_generated_files(data, tmp_path):
    file = tmp_path / "agent-toolkit.yml"
    file.write_bytes(data)
    assert call(tmp_path, "init") == 1
    assert snapshot(tmp_path) == {"agent-toolkit.yml": data}


@pytest.mark.parametrize("name", ["../user.md", "AGENTS.md:secret", ".grok/skills/fake/SKILL.md"])
def test_invalid_manifest_cannot_claim_arbitrary_files(name, tmp_path):
    assert call(tmp_path, "init") == 0
    record = lock(tmp_path)
    record["managed_files"][name] = "1" * 64
    (tmp_path / "toolkit.lock").write_text(json.dumps(record), encoding="utf-8")
    before = snapshot(tmp_path)
    assert call(tmp_path, "update", "--apply") == 1
    assert snapshot(tmp_path) == before


def test_unsafe_root_and_nonregular_output_are_blocked(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(root, target_is_directory=True)
        (root / ".agent-toolkit").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks is unavailable")
    assert call(alias, "init") == 1
    assert call(root, "init") == 1
    assert call(root / ".agent-toolkit" / "new-project", "init") == 1
    assert not (root / "agent-toolkit.yml").exists()
    assert not list(outside.iterdir())


def test_case_conflicts_and_hardlinks_are_blocked(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    lowercase = root / "agents.md"
    lowercase.write_bytes(b"Owner file")
    assert call(root, "init") == 1
    assert lowercase.read_bytes() == b"Owner file"
    lowercase.unlink()
    private = tmp_path / "private.md"
    private.write_bytes(b"Owner file")
    try:
        (root / "AGENTS.md").hardlink_to(private)
    except OSError:
        pytest.skip("Creating hard links is unavailable")
    assert call(root, "init") == 1
    assert private.read_bytes() == b"Owner file"


def test_quality_execution_is_explicit_and_reports_required_failure(tmp_path, capsys):
    marker = tmp_path / "ran"
    source = tmp_path / "input.yml"
    config = {
        "project": {"name": "gate-test"},
        "quality_gates": {
            "optional": ["documentation"],
            "commands": {
                "test-quality": [
                    {
                        "argv": [
                            sys.executable,
                            "-c",
                            "from pathlib import Path; Path('ran').touch(); raise SystemExit(7)",
                        ]
                    }
                ],
                "documentation": [{"argv": [sys.executable, "-c", "raise SystemExit(8)"]}],
            },
        },
    }
    source.write_text(yaml.safe_dump(config), encoding="utf-8")
    assert call(tmp_path, "init", "--config", source) == 0
    assert call(tmp_path, "validate") == 0
    assert not marker.exists()
    assert call(tmp_path, "validate", "--run") == 1
    assert marker.exists()
    result = capsys.readouterr().out
    assert "test-quality (required) #1: exit 7" in result
    assert "documentation (optional) #1: exit 8" in result


def test_optional_gate_does_not_fail_required_checks(tmp_path, capsys):
    config = {
        "project": {"name": "optional"},
        "quality_gates": {
            "optional": ["documentation"],
            "commands": {
                "documentation": [{"argv": [sys.executable, "-c", "raise SystemExit(9)"]}]
            },
        },
    }
    (tmp_path / "agent-toolkit.yml").write_text(yaml.safe_dump(config), encoding="utf-8")
    assert call(tmp_path, "init") == 0
    assert call(tmp_path, "validate", "--run") == 0
    assert "documentation (optional) #1: exit 9" in capsys.readouterr().out


def test_upgrade_uses_new_adapter_outputs_and_preserves_record_on_downgrade(
    tmp_path, monkeypatch, capsys
):
    from agent_toolkit import project

    assert call(tmp_path, "init", "--tools", "codex") == 0
    old = snapshot(tmp_path)
    installed_version = project.VERSION
    with monkeypatch.context() as patch:
        patch.setattr(project, "VERSION", "0.2.0")
        assert call(tmp_path, "update", "--dry-run") == 0
        assert snapshot(tmp_path) == old
        result = capsys.readouterr().out
        assert f"{installed_version} → 0.2.0" in result
        assert "release notes" in result
        assert call(tmp_path, "update", "--apply") == 0
        assert lock(tmp_path)["toolkit_version"] == "0.2.0"
        assert call(tmp_path, "validate") == 0
    upgraded = snapshot(tmp_path)
    assert call(tmp_path, "update", "--apply") == 1
    assert "Downgrade is unsupported" in capsys.readouterr().err
    assert snapshot(tmp_path) == upgraded


def test_catalog_references_resolve_for_each_profile():
    from agent_toolkit.catalog import RESOURCES, catalog, resolve, skill_catalog
    from agent_toolkit.models import Project, ProjectConfig

    for profile in catalog().profiles:
        selection = resolve(
            ProjectConfig(project=Project(name=profile, profile=profile, complexity="extended"))
        )
        assert all(
            RESOURCES.joinpath("workflows", f"{step}.md").is_file() for step in selection.workflows
        )
    assert "langgraph-js" in catalog().stacks
    assert len(skill_catalog()) == 10


def test_managed_commands_find_parent_and_nested_creation_requires_opt_in(
    tmp_path, monkeypatch, capsys
):
    assert call(tmp_path, "init") == 0
    nested = tmp_path / "src"
    nested.mkdir()
    monkeypatch.chdir(nested)
    for args in (["status"], ["validate"], ["diff"], ["update", "--dry-run"]):
        assert main(args) == 0
    assert call(nested, "status") == 1
    for command in ("init", "adopt"):
        assert main([command]) == 1
        assert "--allow-nested" in capsys.readouterr().err
    assert not (nested / "toolkit.lock").exists()
    assert main(["init", "--allow-nested"]) == 0
    assert main(["validate"]) == 0


def test_root_search_stops_at_independent_git_checkout(tmp_path, monkeypatch):
    assert call(tmp_path, "init") == 0
    nested = tmp_path / "other-checkout"
    (nested / ".git").mkdir(parents=True)
    monkeypatch.chdir(nested)
    assert main(["validate"]) == 1
    assert main(["init"]) == 0


def test_adopt_claude_preserves_and_imports_existing_agents(tmp_path):
    agents = tmp_path / "AGENTS.md"
    agents.write_bytes(b"# Project build and test commands\n")
    assert call(tmp_path, "adopt", "--tools", "claude", "--apply") == 0
    assert agents.read_bytes() == b"# Project build and test commands\n"
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8").splitlines() == [
        "@AGENTS.md",
        "@.agent-toolkit/GUIDE.md",
    ]


def test_adopt_npm_stacks_from_dependency_keys(tmp_path, capsys):
    manifest = {
        "scripts": {"react": "fastapi run"},
        "dependencies": {
            "@langchain/langgraph": "1.0.0",
            "@supabase/supabase-js": "2.0.0",
        },
        "devDependencies": {"typescript": "5.0.0"},
    }
    (tmp_path / "package.json").write_bytes(json.dumps(manifest).encode())
    assert call(tmp_path, "adopt", "--apply") == 0
    assert set(lock(tmp_path)["stacks"]) == {"langgraph-js", "supabase", "postgresql", "typescript"}
    assert lock(tmp_path)["profile"] == "ai-agent"
    output = capsys.readouterr().out
    assert "langgraph-js: package.json (@langchain/langgraph)" in output
    assert "supabase: package.json (@supabase/supabase-js)" in output


def test_validate_older_lock_runs_gates_and_update_migrates_claude(tmp_path):
    from agent_toolkit.project import text_checksum

    config = {
        "project": {"name": "legacy"},
        "tools": ["claude"],
        "quality_gates": {
            "commands": {
                "test-quality": [
                    {
                        "argv": [
                            sys.executable,
                            "-c",
                            "from pathlib import Path; Path('ran').touch()",
                        ]
                    }
                ]
            }
        },
    }
    config_path = tmp_path / "agent-toolkit.yml"
    config_path.write_bytes(yaml.safe_dump(config).encode())
    (tmp_path / "AGENTS.md").write_bytes(b"# Existing project\n")
    assert call(tmp_path, "adopt", "--apply") == 0
    old_claude = b"@.agent-toolkit/GUIDE.md\n"
    (tmp_path / "CLAUDE.md").write_bytes(old_claude)
    record = lock(tmp_path)
    record["toolkit_version"] = "0.1.0"
    record["managed_files"]["CLAUDE.md"] = text_checksum(old_claude)
    (tmp_path / "toolkit.lock").write_bytes(json.dumps(record).encode())
    before = snapshot(tmp_path)
    assert call(tmp_path, "update", "--dry-run") == 0
    assert call(tmp_path, "validate", "--run") == 0
    marker = tmp_path / "ran"
    assert marker.exists()
    marker.unlink()
    assert snapshot(tmp_path) == before
    config["project"]["purpose"] = "Unapplied change"
    config_path.write_bytes(yaml.safe_dump(config).encode())
    assert call(tmp_path, "validate", "--run") == 1
    assert not marker.exists()
    assert call(tmp_path, "update", "--apply") == 0
    assert (tmp_path / "CLAUDE.md").read_bytes().startswith(b"@AGENTS.md\n")
    assert call(tmp_path, "validate") == 0


def test_inspect_suggests_rules_from_settings_without_executing_or_writing(tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths=["tests"]\n[tool.ruff]\n', encoding="utf-8"
    )
    (tmp_path / "uv.lock").touch()
    (tmp_path / "AGENTS.md").write_bytes(b"Private instruction body")
    (tmp_path / "package.json").write_bytes(
        json.dumps(
            {
                "scripts": {
                    "test": "touch unexpected; echo SECRET_SCRIPT_BODY",
                    "ignored": "command",
                },
            }
        ).encode()
    )
    before = snapshot(tmp_path)
    assert call(tmp_path, "inspect") == 0
    assert "프로젝트 전용 규칙 초안" not in capsys.readouterr().out
    assert call(tmp_path, "inspect", "--suggest-rules") == 0
    output = capsys.readouterr().out
    for rule in ("uv run --locked pytest", "uv run --locked ruff check .", "`test`", "`AGENTS.md`"):
        assert rule in output
    assert "SECRET_SCRIPT_BODY" not in output
    assert "Private instruction body" not in output
    assert snapshot(tmp_path) == before


def test_inspect_suggestions_tolerate_malformed_project_manifests(tmp_path, capsys):
    (tmp_path / "package.json").write_bytes(b"{")
    (tmp_path / "pyproject.toml").write_bytes(b"[tool.pytest")
    assert call(tmp_path, "inspect", "--suggest-rules") == 0
    assert "제안할 규칙을 찾지 못했습니다" in capsys.readouterr().out
