"""Stage 7 — validate the generated schema against the Avram metaschema."""

from __future__ import annotations

import json
from pathlib import Path


def _load_metaschema(path: str | Path) -> dict:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        import yaml
        return yaml.safe_load(text)
    return json.loads(text)


def validate_schema(schema: dict, metaschema_path: str | Path) -> list[str]:
    """Return a list of human-readable validation error strings (empty = valid).

    Underscore bookkeeping keys are stripped before validation so the internal
    ``_skipped_docs`` etc. don't trip ``additionalProperties: false``."""
    import jsonschema

    meta = _load_metaschema(metaschema_path)
    cleaned = {k: v for k, v in schema.items() if not k.startswith("_")}

    validator_cls = jsonschema.validators.validator_for(meta)
    validator_cls.check_schema(meta)
    validator = validator_cls(meta)

    errors = []
    for err in sorted(validator.iter_errors(cleaned), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "(root)"
        errors.append(f"{loc}: {err.message}")
    return errors
