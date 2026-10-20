"""Create a source-only development snapshot without local state or credentials."""

import argparse
import hashlib
import zipfile
from pathlib import Path

EXCLUDED = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "data",
    "dist",
    "test-results",
    "playwright-report",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.output.resolve().is_relative_to(root):
        raise ValueError("Write the snapshot outside the source tree")
    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root)
            if (
                EXCLUDED.intersection(relative.parts)
                or relative.is_relative_to("build/cache")
                or path.is_symlink()
                or not path.is_file()
            ):
                continue
            if path.name in (
                ".env",
                ".env.existing",
                ".DS_Store",
                "backup.password",
                "setup.token",
                "master.key",
            ) or path.suffix in (".pyc", ".apm", ".sqlite3"):
                continue
            archive.write(path, str(Path(root.name) / relative))
    with zipfile.ZipFile(args.output) as archive:
        assert not archive.testzip()
        assert all(not EXCLUDED.intersection(Path(name).parts) for name in archive.namelist())
        print(
            f"Source snapshot verified: {len(archive.namelist())} files, {args.output.stat().st_size} bytes"
        )
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        hashlib.sha256(args.output.read_bytes()).hexdigest() + "  " + args.output.name + "\n"
    )


if __name__ == "__main__":
    main()
