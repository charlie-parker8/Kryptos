"""The Alembic chain is a short linear sequence of greenfield revisions. This guards that it
stays linear with a single head and that it creates exactly the tables the models declare —
without needing a live DB (the migrations are also exercised for real on every deploy by
docker-entrypoint.sh, and `Base.metadata.create_all` covers the schema in every other test).
"""

import importlib.util
import re
from pathlib import Path
from types import ModuleType

from app.db import Base

_VERSIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"


def _migration_files() -> list[Path]:
    return sorted(p for p in _VERSIONS.glob("*.py") if p.name != "__init__.py")


def _load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_chain_is_linear_with_one_head() -> None:
    modules = [_load(p) for p in _migration_files()]
    by_rev = {m.revision: m for m in modules}

    roots = [m for m in modules if m.down_revision is None]
    assert len(roots) == 1, [m.revision for m in roots]

    downs = {m.down_revision for m in modules if m.down_revision is not None}
    heads = [m for m in modules if m.revision not in downs]
    assert len(heads) == 1, [m.revision for m in heads]

    seen: set[str] = set()
    cursor: str | None = heads[0].revision
    while cursor is not None:
        assert cursor in by_rev and cursor not in seen, cursor
        seen.add(cursor)
        cursor = by_rev[cursor].down_revision
    assert seen == set(by_rev)

    for m in modules:
        assert callable(m.upgrade) and callable(m.downgrade)


def test_migration_creates_every_model_table() -> None:
    source = "\n".join(p.read_text() for p in _migration_files())
    created = set(re.findall(r'op\.create_table\(\s*"([^"]+)"', source))
    model_tables = set(Base.metadata.tables)
    assert created == model_tables, {
        "in_migration_not_models": created - model_tables,
        "in_models_not_migration": model_tables - created,
    }


def test_migration_drops_no_obsolete_spot_tables() -> None:
    source = "\n".join(p.read_text() for p in _migration_files())
    assert "holdings" not in source
    assert '"orders"' not in source
