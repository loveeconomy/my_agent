from __future__ import annotations

import os
import sys
from importlib import import_module
from pathlib import Path


def resolve_pywechat_root(pywechat_root: str | None) -> Path:
    candidates: list[Path] = []
    if pywechat_root:
        candidates.append(Path(pywechat_root))

    env_root = os.getenv("PYWECHAT_ROOT")
    if env_root:
        candidates.append(Path(env_root))

    script_dir = Path(__file__).resolve().parent
    candidates.extend(
        [
            Path.cwd() / "pywechat",
            script_dir.parents[3] / "pywechat",
            script_dir.parents[2] / "pywechat",
        ]
    )

    for candidate in candidates:
        candidate = candidate.expanduser().resolve()
        if (candidate / "pyweixin" / "__init__.py").exists():
            return candidate

    raise SystemExit(
        "Unable to find the pywechat repository root. Pass --pywechat-root or set PYWECHAT_ROOT."
    )


def prepare_pyweixin(pywechat_root: str | None):
    try:
        return import_module("pyweixin")
    except ImportError:
        root = resolve_pywechat_root(pywechat_root)
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        return import_module("pyweixin")


def resolve_files_to_send(paths: list[str]) -> list[str]:
    if not paths:
        raise SystemExit("Pass at least one --file path.")

    resolved: list[str] = []
    for raw_path in paths:
        value = str(raw_path).strip().strip('"').strip("'")
        if not value:
            continue

        path = Path(value).expanduser().resolve()
        if path.is_file():
            resolved.append(str(path))
            continue

        if path.is_dir():
            resolved.extend(
                str(child.resolve()) for child in sorted(path.iterdir()) if child.is_file()
            )
            continue

        raise SystemExit(f"Path not found or unsupported: {raw_path}")

    deduped = list(dict.fromkeys(resolved))
    if not deduped:
        raise SystemExit("No files found to send. Use a file path or a folder containing files.")
    return deduped
