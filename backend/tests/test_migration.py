"""The Alembic chain is a single greenfield revision. This guards that it stays that way
and that it creates exactly the tables the models declare — without needing a live DB
(the migration is also exercised for real on every deploy by docker-entrypoint.sh, and
`Base.metadata.create_all` covers the schema in every other test).
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


def test_exactly_one_migration_with_no_down_revision() -> None:
    files = _migration_files()
    assert len(files) == 1, [p.name for p in files]

    module = _load(files[0])
    assert module.down_revision is None
    assert callable(module.upgrade)
    assert callable(module.downgrade)


def test_migration_creates_every_model_table() -> None:
    source = _migration_files()[0].read_text()
    created = set(re.findall(r'op\.create_table\(\s*"([^"]+)"', source))
    model_tables = set(Base.metadata.tables)
    assert created == model_tables, {
        "in_migration_not_models": created - model_tables,
        "in_models_not_migration": model_tables - created,
    }


def test_migration_drops_no_obsolete_spot_tables() -> None:
    source = _migration_files()[0].read_text()
    assert "holdings" not in source
    assert '"orders"' not in source
