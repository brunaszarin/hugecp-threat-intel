import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from app.core.config import settings

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def db_conn() -> Iterator[psycopg.Connection[tuple[object, ...]]]:
    """Conexão isolada num schema temporário, apagado ao final do teste.

    Assim os testes nunca tocam nos dados carregados para desenvolvimento.
    """
    url = os.environ.get("DATABASE_URL", settings.database_url)
    schema = f"test_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(f"CREATE SCHEMA {schema}")
    try:
        with psycopg.connect(url, options=f"-c search_path={schema}") as conn:
            yield conn
    finally:
        with psycopg.connect(url, autocommit=True) as admin:
            admin.execute(f"DROP SCHEMA {schema} CASCADE")
