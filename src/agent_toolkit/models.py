"""Configuration and manifest models shared by the CLI and exported schemas."""

import json
import re
from typing import Annotated, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

SLUG = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
SEMVER = r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$"
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=SLUG)]
Version = Annotated[str, StringConstraints(pattern=SEMVER)]
Commit = Annotated[str, StringConstraints(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Name = Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=r"^[^\r\n\x00]+$")]
Text = Annotated[str, StringConstraints(min_length=1, max_length=1024, pattern=r"^[^\x00]+$")]
Arg = Annotated[str, StringConstraints(max_length=4096, pattern=r"^[^\x00]*$")]
SchemaVersion = Annotated[int, Field(ge=1, le=1)]
Tool = Literal["codex", "claude", "grok", "generic"]
Complexity = Literal["minimal", "standard", "extended"]
TaskSize = Literal["small", "medium", "large", "critical"]


class ToolkitError(Exception):
    """An actionable error that can be rendered without a traceback."""


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class Project(Model):
    name: Name
    purpose: Text | None = None
    profile: Identifier = "minimal"
    complexity: Complexity = "minimal"
    team_size: int = Field(default=1, ge=1, le=10000)
    deployment: Name | None = None
    security_requirements: list[Text] = Field(default_factory=list)
    testing_requirements: list[Text] = Field(default_factory=list)
    multi_agent: Literal["auto", "off", "on"] = "auto"


class Selection(Model):
    enabled: list[Identifier] | None = None


class GateCommand(Model):
    argv: list[Arg] = Field(min_length=1, max_length=64)
    timeout_seconds: int = Field(default=300, ge=1, le=3600)

    @model_validator(mode="after")
    def executable(self) -> "GateCommand":
        if not self.argv[0].strip():
            raise ValueError("argv[0] must name an executable")
        return self


class QualityGates(Model):
    required: list[Identifier] = Field(default_factory=list)
    optional: list[Identifier] = Field(default_factory=list)
    not_applicable: list[Identifier] = Field(default_factory=list)
    commands: dict[Identifier, list[GateCommand]] = Field(default_factory=dict)


class ProjectConfig(Model):
    schema_version: SchemaVersion = 1
    project: Project
    stacks: list[Identifier] = Field(default_factory=list)
    stack_conflict_notes: dict[str, Text] = Field(default_factory=dict)
    tools: list[Tool] = Field(default_factory=lambda: ["generic"], min_length=1)
    agents: Selection = Field(default_factory=Selection)
    skills: Selection = Field(default_factory=Selection)
    quality_gates: QualityGates = Field(default_factory=QualityGates)


class Profile(Model):
    description: Text
    guidance: Text
    agents: list[Identifier]
    skills: list[Identifier]
    gates: list[Identifier]
    workflows: list[Identifier]


class Agent(Model):
    description: Text
    trigger: Text
    input: Text
    scope: Text
    tools: Text
    changes: Text
    verification: Text
    read_only: bool = False


class Skill(Model):
    name: Identifier
    description: Text
    metadata: dict[str, str] = Field(default_factory=dict)


class ToolkitLock(Model):
    schema_version: SchemaVersion = 1
    toolkit_version: Version
    source_commit: Commit | None
    config_sha256: Digest
    profile: Identifier
    stacks: list[Identifier]
    skills: list[Identifier]
    agents: list[Identifier]
    workflows: list[Identifier]
    adapters: dict[Tool, int]
    managed_files: dict[str, Digest] = Field(min_length=1)


class StrictLoader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        # Aliases can expand a small input into a deeply nested structure.
        if self.check_event(yaml.AliasEvent):
            raise ToolkitError("YAML aliases are not supported")
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):
        keys = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise ToolkitError("YAML mapping keys must be strings")
            if key in keys:
                raise ToolkitError(f"Duplicate YAML key on line {key_node.start_mark.line + 1}")
            keys.add(key)
        return super().construct_mapping(node, deep=deep)


def load_yaml(data: bytes | str, location: str):
    try:
        return yaml.load(data, Loader=StrictLoader)
    except yaml.MarkedYAMLError as exc:
        line = f" on line {exc.problem_mark.line + 1}" if exc.problem_mark else ""
        raise ToolkitError(f"Invalid YAML in {location}{line}") from exc
    except (yaml.YAMLError, RecursionError, UnicodeError) as exc:
        raise ToolkitError(f"Invalid YAML in {location}") from exc


def load_json(data: bytes | str, location: str):
    def unique_keys(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ToolkitError(f"Duplicate JSON key in {location}")
            result[key] = value
        return result

    try:
        return json.loads(data, object_pairs_hook=unique_keys)
    except (ValueError, RecursionError) as exc:
        raise ToolkitError(f"Invalid JSON in {location}") from exc


def validated[T: Model](model: type[T], data, location: str) -> T:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = []
        for entry in exc.errors(include_input=False, include_url=False):
            field = ".".join(map(str, entry["loc"])) or "<root>"
            problems.append(f"{field}: {entry['msg']}")
        raise ToolkitError(f"Invalid {location}: " + "; ".join(problems)) from exc


def is_identifier(value: str) -> bool:
    return len(value) <= 64 and re.fullmatch(SLUG, value) is not None


SCHEMAS = {
    "project": ProjectConfig,
    "agent": Agent,
    "profile": Profile,
    "skill": Skill,
    "toolkit-lock": ToolkitLock,
}
