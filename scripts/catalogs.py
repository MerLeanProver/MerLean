"""Optional local catalog artifacts; never register, install, or edit personal catalogs."""
import json
import os
from pathlib import Path
import tempfile


def write_catalogs(packages: Path) -> tuple[Path, Path]:
    try:
        from build_bundles import AGENTS, PROVIDERS, verify_generated
    except ModuleNotFoundError:
        from scripts.build_bundles import AGENTS, PROVIDERS, verify_generated
    packages = packages.resolve()
    if packages.name != "plugins":
        raise ValueError("catalog generation requires --out <marketplace-root>/plugins")
    root = packages.parent
    for provider in PROVIDERS:
        for agent in AGENTS:
            package = packages / f"{agent}-{provider}"
            verify_generated(package)
            manifest = json.loads((package / f".{provider}-plugin/plugin.json").read_text())
            if manifest["name"] != package.name:
                raise ValueError(f"catalog manifest mismatch: {package}")
    codex = {"name": "merlean", "interface": {"displayName": "MerLean"}, "plugins": [
        {"name": f"{agent}-codex", "source": {"source": "local", "path": f"./plugins/{agent}-codex"},
         "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
         "category": "Productivity"} for agent in AGENTS
    ]}
    claude = {"name": "merlean", "description": "Three mathematics agents for Claude Code: Lite, Heavy, and Paper-writing.",
              "owner": {"name": "MerLean authors", "url": "https://github.com/MerLeanProver"}, "plugins": [
        {"name": f"{agent}-claude", "source": f"./plugins/{agent}-claude"} for agent in AGENTS
    ]}
    outputs = [(root / ".agents/plugins/marketplace.json", codex),
               (root / ".claude-plugin/marketplace.json", claude)]
    prepared = []
    for path, content in outputs:
        for ancestor in [path, *path.parents]:
            if ancestor == root:
                break
            if ancestor.is_symlink():
                raise ValueError(f"catalog symlink preserved: {ancestor}")
        payload = (json.dumps(content, indent=2) + "\n").encode()
        if path.exists() and (not path.is_file() or path.stat().st_nlink != 1 or path.read_bytes() != payload):
            raise ValueError(f"existing different catalog preserved: {path}")
        prepared.append((path, payload))
    for path, payload in prepared:
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".merlean-catalog-", dir=path.parent) as temp:
            staged = Path(temp) / "catalog.json"
            staged.write_bytes(payload)
            os.link(staged, path)
    return tuple(path for path, _ in prepared)
