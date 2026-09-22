"""Offline project consistency gate. Run from any directory."""
import pathlib
import re
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def check():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    source = (ROOT / "src/aixsecurity/__init__.py").read_text(encoding="utf-8")
    version = re.search(r'__version__ = "([^"]+)"', source).group(1)
    assert metadata["project"]["version"] == version, "Package version mismatch"
    assert f"## {version} " in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), "Missing changelog version"
    for document in [ROOT / "README.md", *(ROOT / "docs").glob("*.md")]:
        for target in re.findall(r'\]\(([^)]+)\)', document.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            assert (document.parent / target.split("#")[0]).exists(), f"Broken link: {document.name}: {target}"
    print(f"PROJECT_CHECK_OK version={version}")


if __name__ == "__main__":
    check()
