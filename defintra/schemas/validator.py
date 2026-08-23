"""
DIR (Defintra Intermediate Representation) Validator.
Validates exported DIR data structures against the canonical JSON Schema.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple
import jsonschema


def load_dir_schema() -> Dict[str, Any]:
    schema_file = Path(__file__).parent / "dir_v1.schema.json"
    return json.loads(schema_file.read_text(encoding="utf-8"))


def validate_dir(dir_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    schema = load_dir_schema()
    validator = jsonschema.Draft202012Validator(schema)
    errors = []
    for err in validator.iter_errors(dir_data):
        errors.append(f"{err.json_path}: {err.message}")
    return (len(errors) == 0, errors)
