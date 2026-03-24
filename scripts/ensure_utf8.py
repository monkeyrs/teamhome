from __future__ import annotations

import argparse
from pathlib import Path


TARGET_SUFFIXES = {
    ".js",
    ".json",
    ".vue",
    ".py",
    ".java",
    ".ts",
    ".tsx",
    ".jsx",
    ".mjs",
    ".cjs",
}

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".run",
    "dist",
    "build",
}


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in path.parts)


def decode_text(raw: bytes) -> tuple[str, str] | None:
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return None


def normalize_file(path: Path, check_only: bool) -> tuple[bool, str]:
    raw = path.read_bytes()
    decoded = decode_text(raw)
    if not decoded:
        return False, "skip:decode-failed"

    text, source_encoding = decoded
    normalized = text.encode("utf-8")
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    changed = raw != normalized or has_bom
    if changed and not check_only:
        path.write_bytes(normalized)
    if changed:
        return True, f"normalized:{source_encoding}"
    return False, "ok"


def iter_targets(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in TARGET_SUFFIXES:
            continue
        if should_skip(path):
            continue
        yield path


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize source files to UTF-8 without BOM.")
    parser.add_argument("--check", action="store_true", help="Check only, do not rewrite files.")
    parser.add_argument("--root", default=".", help="Project root path.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    changed_count = 0
    skipped_count = 0

    for file_path in iter_targets(root):
        changed, status = normalize_file(file_path, check_only=args.check)
        if changed:
            changed_count += 1
            print(f"[CHANGED] {file_path} ({status})")
        elif status.startswith("skip:"):
            skipped_count += 1
            print(f"[SKIP] {file_path} ({status})")

    mode = "CHECK" if args.check else "FIX"
    print(f"[{mode}] changed={changed_count} skipped={skipped_count}")
    return 1 if args.check and changed_count > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
