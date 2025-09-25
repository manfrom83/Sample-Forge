"""
Schema Sanitizer Utility

This utility cleans common Unicode artifacts from the API schema file so UI tooltips
and descriptions are human-friendly at the source. It is safe to run multiple times.

Usage (from project root):
  python -m utils.sanitize_schema

It will update config/openai_api_schema.json in place (backing up a .bak copy).
"""

import json
import unicodedata
from pathlib import Path
from utils.logger import logger


def _clean_text(text: str) -> str:
    if not isinstance(text, str):
        return text
    try:
        s = unicodedata.normalize('NFKC', text)
        # Drop Unicode replacement character variants
        s = s.replace("\uFFFD", "").replace("\ufffd", "")
        # Remove control characters except newline/tab
        cleaned = "".join(
            ch for ch in s
            if (ch in "\n\t") or (unicodedata.category(ch)[0] != 'C')
        )
        return cleaned
    except Exception:
        return text


def sanitize_schema_file(schema_path: Path) -> bool:
    try:
        raw = schema_path.read_text(encoding="utf-8")
        data = json.loads(raw)

        # Walk categories -> params -> fields
        changed = False
        if isinstance(data, dict):
            for _cat, params in data.items():
                if not isinstance(params, dict):
                    continue
                for _name, pdef in params.items():
                    if not isinstance(pdef, dict):
                        continue
                    for key in ("tooltip", "description"):
                        if key in pdef and isinstance(pdef[key], str):
                            cleaned = _clean_text(pdef[key])
                            if cleaned != pdef[key]:
                                pdef[key] = cleaned
                                changed = True

        if not changed:
            return True

        # Backup and write
        backup = schema_path.with_suffix(schema_path.suffix + ".bak")
        if not backup.exists():
            backup.write_text(raw, encoding="utf-8")
        schema_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception as e:
        logger.error(f"Failed to sanitize schema: {e}")
        return False


def main():
    # Locate project root by this file location
    root = Path(__file__).resolve().parents[1]
    schema = root / "config" / "openai_api_schema.json"
    if not schema.exists():
        logger.error(f"Schema not found: {schema}")
        return 1
    ok = sanitize_schema_file(schema)
    if ok:
        logger.info("Schema sanitized.")
    else:
        logger.error("Schema sanitation failed.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

