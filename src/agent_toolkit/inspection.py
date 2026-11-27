"""Bounded, read-only discovery for adopting an existing project."""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .files import CONFIG, LOCK, is_link, lstat, read_file
from .git_ops import checkout_root, git_state, head
from .models import ToolkitError, load_json

SIGNALS = {
    "README or product docs": ("README.md", "README.rst", "README", "docs", "SPEC.md"),
    "Agent instructions": (
        "AGENTS.md",
        "CLAUDE.md",
        "AGENTS.override.md",
        "CLAUDE.local.md",
        ".claude/CLAUDE.md",
        CONFIG,
        LOCK,
    ),
    "Existing Skills and agents": (
        ".agents/skills",
        ".codex/agents",
        ".claude/skills",
        ".claude/agents",
        ".grok/skills",
        ".grok/agents",
        ".agent-toolkit",
    ),
    "Dependency manifests": (
        "pyproject.toml",
        "requirements.txt",
        "package.json",
        "Cargo.toml",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "supabase/config.toml",
        "src-tauri/Cargo.toml",
    ),
    "Test entry points": ("tests", "test", "spec", "e2e", "pytest.ini", "playwright.config.ts"),
    "CI and deployment": (
        ".github/workflows",
        ".gitlab-ci.yml",
        "Jenkinsfile",
        "Dockerfile",
        "compose.yaml",
        "docker-compose.yml",
        ".circleci",
        "azure-pipelines.yml",
    ),
    "Formatting and local policy": (
        ".editorconfig",
        ".prettierrc",
        "ruff.toml",
        ".ruff.toml",
        "eslint.config.js",
        "Makefile",
        "CONTRIBUTING.md",
    ),
}


@dataclass(frozen=True)
class Inspection:
    lines: list[str]
    stacks: list[str]
    profile: str


def present(root: Path, relative: str) -> bool:
    path = root
    for part in relative.split("/"):
        path /= part
        info = lstat(path)
        if info is None or is_link(info):
            return False
    return True


def manifests(root: Path, paths: list[str]) -> str:
    pieces = []
    for path in paths:
        try:
            if present(root, path) and (value := read_file(root, path)):
                pieces.append(value.decode("utf-8", errors="replace"))
        except (OSError, ToolkitError):
            continue
    return "\n".join(pieces).lower()


def npm_manifest(root: Path) -> dict:
    data = read_file(root, "package.json")
    if data is None:
        return {}
    manifest = load_json(data, "package.json")
    if not isinstance(manifest, dict):
        raise ToolkitError("Expected an object in package.json")
    return manifest


def npm_dependencies(manifest: dict) -> set[str]:
    packages = set()
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        group = manifest.get(key, {})
        if not isinstance(group, dict):
            raise ToolkitError(f"Expected an object for package.json {key}")
        packages.update(group)
    return packages


def rule_suggestions(root: Path, package: dict) -> list[str]:
    rules = []
    existing = [
        path
        for path in ("AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md", ".agent-toolkit/project-rules.md")
        if present(root, path)
    ]
    if existing:
        paths = ", ".join(f"`{path}`" for path in existing)
        rules.append(
            f"- 변경 전에 기존 프로젝트 지침을 확인하고 새 규칙과의 충돌을 검토한다. 근거 {paths}."
        )

    if present(root, ".github/workflows"):
        rules.append(
            "- 검증 절차를 바꿀 때 GitHub Actions의 관련 작업과 로컬 검증 절차를 함께 확인한다. 근거 `.github/workflows/`."
        )

    try:
        data = read_file(root, "pyproject.toml")
        project = tomllib.loads(data.decode("utf-8")) if data else {}
    except (OSError, ToolkitError, ValueError, RecursionError):
        project = {}
    python_tools = project.get("tool")
    using_uv = present(root, "uv.lock")
    prefix = "uv run --locked " if using_uv else ""
    uv_evidence = " 및 `uv.lock`" if using_uv else ""
    configurations = (
        ("pytest", ("pytest.ini",), f"{prefix}pytest" if using_uv else "python -m pytest"),
        ("ruff", ("ruff.toml", ".ruff.toml"), f"{prefix}ruff check ."),
    )
    for tool, standalone, command in configurations:
        source = next((path for path in standalone if present(root, path)), None)
        if source is None and isinstance(python_tools, dict) and tool in python_tools:
            source = "pyproject.toml"
        if source:
            rules.append(
                f"- Python 코드가 바뀌면 `{command}`를 검증에 사용한다. "
                f"근거 `{source}`{uv_evidence}."
            )

    scripts = package.get("scripts")
    if isinstance(scripts, dict):
        available = [
            f"`{name}`"
            for name in ("lint", "typecheck", "test", "build")
            if isinstance(scripts.get(name), str) and scripts[name].strip()
        ]
        if available:
            names = ", ".join(available)
            rules.append(
                f"- 변경 범위에 맞는 프로젝트 스크립트 {names}를 기존 패키지 매니저로 검증한다. 근거 `package.json`의 `scripts`."
            )
    return rules


def inspect(root: Path, *, suggest_rules: bool = False) -> Inspection:
    lines = ["Project: " + str(root)]
    if not root.is_dir():
        return Inspection([*lines, "Directory does not exist"], [], "minimal")
    skip = {".git", ".venv", "node_modules", ".env", ".agent-toolkit-transaction"}
    names = sorted(
        entry.name
        for entry in root.iterdir()
        if entry.name not in skip and not entry.name.startswith(".env.")
    )
    lines.append("Top-level entries: " + (", ".join(map(repr, names[:24])) or "none"))
    if len(names) > 24:
        lines.append(f"Additional top-level entries: {len(names) - 24}")
    for label, paths in SIGNALS.items():
        found = [path for path in paths if present(root, path)]
        lines.append(f"{label}: " + (", ".join(found) or "none at known locations"))
    evidence: dict[str, list[str]] = {}
    indicators = [
        ("python", ("pyproject.toml", "requirements.txt")),
        ("rust", ("Cargo.toml",)),
        ("java", ("pom.xml", "build.gradle", "build.gradle.kts")),
        ("typescript", ("tsconfig.json",)),
        ("supabase", ("supabase/config.toml",)),
        ("tauri", ("src-tauri/Cargo.toml",)),
        ("docker", ("Dockerfile", "compose.yaml", "docker-compose.yml")),
    ]
    for stack, paths in indicators:
        if found := [path for path in paths if present(root, path)]:
            evidence[stack] = found
    text = manifests(root, [*SIGNALS["Dependency manifests"][:-2], "Dockerfile", "compose.yaml"])
    styles = [
        name
        for name in ("ruff", "black", "eslint", "prettier", "checkstyle", "spotless")
        if re.search(rf"\b{name}\b", text)
    ]
    if styles:
        lines.append("Style tooling in manifests: " + ", ".join(styles))
    docs = manifests(root, ["README.md", "README.rst", "CONTRIBUTING.md"])
    signals = [
        label for label in ("build", "test", "deploy", "lint") if re.search(rf"\b{label}\b", docs)
    ]
    if signals:
        lines.append("Development topics in existing docs: " + ", ".join(signals))
    package = {}
    try:
        package = npm_manifest(root)
        packages = npm_dependencies(package)
    except (ToolkitError, OSError):
        lines.append("Could not read package.json dependencies")
        packages = set()
    npm_stacks = {
        "next": "nextjs",
        "react": "react",
        "typescript": "typescript",
        "@supabase/supabase-js": "supabase",
        "@supabase/ssr": "supabase",
        "@langchain/langgraph": "langgraph-js",
        "pg": "postgresql",
        "oracledb": "oracle",
        "@elastic/elasticsearch": "elasticsearch",
        "@opensearch-project/opensearch": "opensearch",
        "redis": "redis",
        "ioredis": "redis",
    }
    for dependency, stack in npm_stacks.items():
        if dependency in packages:
            evidence.setdefault(stack, []).append(f"package.json ({dependency})")

    python_files = ("pyproject.toml", "requirements.txt")
    detectors = [
        ("fastapi", r"\bfastapi\b", python_files),
        ("langgraph", r"\blanggraph\b", python_files),
        (
            "spring-boot",
            r"\bspring-boot(?:-starter|-gradle-plugin)\b",
            ("pom.xml", "build.gradle", "build.gradle.kts"),
        ),
    ]
    service_files = (
        *python_files,
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "Dockerfile",
        "compose.yaml",
        "docker-compose.yml",
    )
    detectors.extend(
        (stack, pattern, service_files)
        for stack, pattern in {
            "postgresql": r"\b(?:postgresql|psycopg[23]?)\b",
            "oracle": r"\b(?:ojdbc\d*|oracledb|cx_oracle)\b",
            "elasticsearch": r"\belasticsearch\b",
            "opensearch": r"\bopensearch(?:-py|-java)?\b",
            "redis": r"\bredis\b",
        }.items()
    )
    manifest_text = {path: manifests(root, [path]) for path in service_files}
    for stack, pattern, paths in detectors:
        for path in paths:
            if re.search(pattern, manifest_text[path]):
                evidence.setdefault(stack, []).append(path)
    stacks = list(evidence)
    profile = "minimal"
    if "nextjs" in stacks:
        profile = "web-service"
    elif "langgraph" in stacks or "langgraph-js" in stacks:
        profile = "ai-agent"
    elif "tauri" in stacks:
        profile = "desktop-app"
    elif "react" in stacks:
        profile = "frontend"
    elif "fastapi" in stacks or "spring-boot" in stacks:
        profile = "backend-api"
    lines.append("Suggested profile: " + profile)
    lines.append("Detected stack signals: " + (", ".join(stacks) or "none"))
    lines.extend(f"  {stack}: {', '.join(paths)}" for stack, paths in evidence.items())
    if checkout := checkout_root(root):
        branch, revision = head(root)
        try:
            status = git_state(root)
        except ToolkitError as exc:
            status = str(exc)
        lines.append(f"Git: {branch}, {revision}, {status}; checkout {checkout}")
    else:
        lines.append("Git: no supported checkout detected")
    if suggest_rules:
        lines.extend(["", "## 프로젝트 전용 규칙 초안", ""])
        suggestions = rule_suggestions(root, package)
        lines.extend(suggestions or ["확인한 설정에서 제안할 규칙을 찾지 못했습니다."])
        if suggestions:
            lines.extend(
                ["", "검토한 초안을 `.agent-toolkit/project-rules.md`에 반영할 수 있습니다."]
            )
    return Inspection(lines, stacks, profile)
