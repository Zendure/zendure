"""Architecture guards for rules a reviewer checks first."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "zendure"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def test_library_never_imports_homeassistant() -> None:
    offenders = [
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if any(m.split(".")[0] == "homeassistant" for m in _imported_modules(path))
    ]
    assert offenders == []


def _resolved_imports(path: Path) -> set[str]:
    """Fully-qualified module names imported by ``path``, relative ones resolved."""
    package = ["zendure", *path.relative_to(SRC).parent.parts]
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                modules.add(node.module or "")
                continue
            base = package[: len(package) - node.level + 1]
            modules.add(".".join([*base, *([node.module] if node.module else [])]))
    return modules


# Layers that must stay protocol-agnostic (coding standard rule 3 / section 7).
_PROTOCOL_AGNOSTIC = (
    "client.py",
    "models.py",
    "events.py",
    "exceptions.py",
    "catalog/",
    "state/",
)
_CONCRETE = ("zendure.protocols.local_http", "zendure.transport.http")


def test_agnostic_layers_do_not_import_concrete_protocol() -> None:
    offenders = []
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if not rel.startswith(_PROTOCOL_AGNOSTIC):
            continue
        offenders.extend(
            f"{rel} -> {module}"
            for module in _resolved_imports(path)
            if module.startswith(_CONCRETE)
        )
    assert offenders == []


def test_only_transport_imports_aiohttp_client() -> None:
    # Protocol code and the factory may reference the session type; only
    # transport performs I/O.
    allowed = {
        "transport/http.py",
        "protocols/local_http/protocol.py",
        "local.py",
    }
    offenders = [
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if "aiohttp" in _imported_modules(path)
        and path.relative_to(SRC).as_posix() not in allowed
    ]
    assert offenders == []
