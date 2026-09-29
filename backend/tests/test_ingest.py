from pathlib import Path

import psycopg
import pytest

from app.ingest.loader import IngestError, IngestResult, run_ingest

pytestmark = pytest.mark.integration

Conn = psycopg.Connection[tuple[object, ...]]


def _ingest(conn: Conn, fixtures: Path) -> IngestResult:
    return run_ingest(conn, fixtures / "flows.csv", fixtures / "indicadores.csv")


def test_ingest_loads_all_rows(db_conn: Conn, fixtures_dir: Path) -> None:
    result = _ingest(db_conn, fixtures_dir)
    # Duas amostras idênticas de ICMP são mantidas: cada linha é uma amostra.
    assert result == IngestResult(flows=5, origins=3, indicators=2)


def test_ingest_twice_does_not_duplicate(db_conn: Conn, fixtures_dir: Path) -> None:
    first = _ingest(db_conn, fixtures_dir)
    second = _ingest(db_conn, fixtures_dir)
    assert first == second


def test_ingest_converts_types(db_conn: Conn, fixtures_dir: Path) -> None:
    _ingest(db_conn, fixtures_dir)
    row = db_conn.execute(
        "SELECT o.asn, o.country, i.category, i.confidence "
        "FROM origins o LEFT JOIN indicators i ON i.ip = o.ip "
        "WHERE o.ip = '10.0.0.1'"
    ).fetchone()
    assert row == (64500, "BR", "scan", 80)


def test_ingest_rejects_unexpected_header(
    db_conn: Conn, fixtures_dir: Path, tmp_path: Path
) -> None:
    bad = tmp_path / "flows.csv"
    bad.write_text("ts,origem\n1,2\n", encoding="utf-8")
    with pytest.raises(IngestError, match="Cabeçalho inesperado"):
        run_ingest(db_conn, bad, fixtures_dir / "indicadores.csv")


def test_failed_ingest_keeps_previous_data(
    db_conn: Conn, fixtures_dir: Path, tmp_path: Path
) -> None:
    _ingest(db_conn, fixtures_dir)
    broken = tmp_path / "flows.csv"
    broken.write_bytes(
        (fixtures_dir / "flows.csv").read_bytes()
        + b"1789473800,not-an-ip,1,203.0.113.1,80,TCP,1,1,1,BR\r\n"
    )
    with pytest.raises(psycopg.errors.InvalidTextRepresentation):
        run_ingest(db_conn, broken, fixtures_dir / "indicadores.csv")
    db_conn.rollback()
    count = db_conn.execute("SELECT count(*) FROM flows").fetchone()
    assert count == (5,)
