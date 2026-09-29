import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_conn
from app.core.config import settings
from app.ingest.loader import run_ingest
from app.main import app

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


@pytest.fixture
def client(
    db_conn: psycopg.Connection[tuple[object, ...]], fixtures_dir: Path
) -> Iterator[TestClient]:
    """Cliente HTTP da API usando o schema isolado, já carregado com as fixtures."""
    run_ingest(db_conn, fixtures_dir / "flows.csv", fixtures_dir / "indicadores.csv")
    app.dependency_overrides[get_conn] = lambda: db_conn
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
