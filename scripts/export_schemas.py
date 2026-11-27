"""Regenerate or check the checked-in JSON Schemas."""

import argparse
import json
from pathlib import Path

from agent_toolkit.models import SCHEMAS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    directory = Path(__file__).resolve().parents[1] / "schemas"
    stale = []
    for name, model in SCHEMAS.items():
        path = directory / f"{name}.schema.json"
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            **model.model_json_schema(),
        }
        content = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True).encode() + b"\n"
        if args.check:
            if not path.is_file() or path.read_bytes() != content:
                stale.append(path.name)
        else:
            path.write_bytes(content)
    if stale:
        print("Outdated schemas: " + ", ".join(stale))
    return int(bool(stale))


if __name__ == "__main__":
    raise SystemExit(main())
