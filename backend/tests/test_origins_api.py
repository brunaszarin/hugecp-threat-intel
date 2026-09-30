"""Testes das origens (lista B e ficha C).

Além das fixtures base (ver test_overview_api.py), o cenário insere origens que
ficam exatamente em cima e logo acima dos limiares do enunciado:

  10.0.0.9  51 portas no mesmo destino          -> many_ports   (3060 B)
  10.0.0.7  50 portas no mesmo destino          -> nada         (3000 B)
  10.0.0.8  21 destinos distintos               -> many_destinations (1260 B)
  10.0.0.6  20 destinos distintos               -> nada         (1200 B)

Com apenas 7 origens, todas estariam no "top 20 em bytes"; por isso os testes
reduzem esse limite para 2 (ficam 10.0.0.3 com 5000 B e 10.0.0.9 com 3060 B).
"""

from collections.abc import Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.repositories import origins as origins_repo

pytestmark = pytest.mark.integration

Conn = psycopg.Connection[tuple[object, ...]]


@pytest.fixture
def api(client: TestClient, db_conn: Conn, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(origins_repo, "TOP_BYTES_LIMIT", 2)
    db_conn.execute(
        """
        INSERT INTO origins (ip, asn, country) VALUES
            ('10.0.0.9', 64509, 'NL'), ('10.0.0.7', 64507, 'NL'),
            ('10.0.0.8', 64508, 'CN'), ('10.0.0.6', 64506, 'CN');

        INSERT INTO flows (ts, src_ip, src_port, dst_ip, dst_port, protocol, bytes, packets)
        SELECT '2026-09-15 12:10:00+00'::timestamptz + make_interval(secs => p),
               '10.0.0.9'::inet, 50000, '203.0.113.50'::inet, p, 'TCP', 60, 1
        FROM generate_series(1, 51) AS p
        UNION ALL
        SELECT '2026-09-15 12:10:00+00'::timestamptz + make_interval(secs => p),
               '10.0.0.7', 50000, '203.0.113.60', p, 'TCP', 60, 1
        FROM generate_series(1, 50) AS p
        UNION ALL
        SELECT '2026-09-15 12:20:00+00'::timestamptz + make_interval(secs => d),
               '10.0.0.8', 50000, ('198.51.100.' || d)::inet, 22, 'TCP', 60, 1
        FROM generate_series(1, 21) AS d
        UNION ALL
        SELECT '2026-09-15 12:20:00+00'::timestamptz + make_interval(secs => d),
               '10.0.0.6', 50000, ('192.0.2.' || d)::inet, 22, 'TCP', 60, 1
        FROM generate_series(1, 20) AS d;
        """
    )
    yield client


def _by_ip(body: dict[str, object]) -> dict[str, list[str]]:
    items = body["items"]
    assert isinstance(items, list)
    return {item["ip"]: item["criteria"] for item in items}


def test_list_applies_each_criterion_with_strict_thresholds(api: TestClient) -> None:
    body = api.get("/api/origins", params={"page_size": 50}).json()
    assert _by_ip(body) == {
        "10.0.0.3": ["top_bytes"],
        "10.0.0.9": ["many_ports", "top_bytes"],
        "10.0.0.1": ["indicator"],
        "10.0.0.8": ["many_destinations"],
    }
    assert body["total"] == 4
    assert body["criteria_counts"] == {
        "any": 4,
        "indicator": 1,
        "many_destinations": 1,
        "many_ports": 1,
        "top_bytes": 2,
    }


def test_list_item_fields(api: TestClient) -> None:
    items = api.get("/api/origins").json()["items"]
    indicator = next(item for item in items if item["ip"] == "10.0.0.1")
    assert indicator == {
        "ip": "10.0.0.1",
        "asn": 64500,
        "country": "BR",
        "indicator": {
            "category": "scan",
            "source": "feed-otx",
            "confidence": 80,
            "first_seen": "2026-03-14T12:00:00Z",
            "last_seen": "2026-09-14T12:00:00Z",
        },
        "bytes": 3000,
        "packets": 30,
        "flows": 2,
        "destinations": 2,
        "ports": 2,
        "max_ports_per_destination": 1,
        "first_seen": "2026-09-15T12:00:00Z",
        "last_seen": "2026-09-15T12:01:00Z",
        "criteria": ["indicator"],
    }


def test_list_filter_by_criteria_keeps_global_counts(api: TestClient) -> None:
    body = api.get(
        "/api/origins", params=[("criteria", "many_ports"), ("criteria", "indicator")]
    ).json()
    assert set(_by_ip(body)) == {"10.0.0.9", "10.0.0.1"}
    assert body["total"] == 2
    assert body["criteria_counts"]["any"] == 4


def test_list_sort_and_pagination(api: TestClient) -> None:
    page1 = api.get("/api/origins", params={"sort": "destinations", "page_size": 1}).json()
    page2 = api.get(
        "/api/origins", params={"sort": "destinations", "page_size": 1, "page": 2}
    ).json()
    assert [i["ip"] for i in page1["items"]] == ["10.0.0.8"]
    assert [i["ip"] for i in page2["items"]] == ["10.0.0.1"]
    assert page1["total"] == page2["total"] == 4


def test_list_rejects_unknown_sort_and_criterion(api: TestClient) -> None:
    assert api.get("/api/origins", params={"sort": "bytes; DROP TABLE flows"}).status_code == 422
    assert api.get("/api/origins", params={"criteria": "evil"}).status_code == 422


def test_criteria_follow_the_period(api: TestClient) -> None:
    # Antes de 12:10 as origens do cenário ainda não apareceram, então o ranking de
    # bytes é refeito só com as três origens da janela: 10.0.0.1 entra no top 2.
    body = api.get(
        "/api/origins", params={"from": "2026-09-15T12:00:00Z", "to": "2026-09-15T12:05:00Z"}
    ).json()
    assert _by_ip(body) == {"10.0.0.3": ["top_bytes"], "10.0.0.1": ["indicator", "top_bytes"]}


def test_detail_of_flagged_origin(api: TestClient) -> None:
    body = api.get("/api/origins/10.0.0.9").json()
    assert (body["asn"], body["country"], body["indicator"]) == (64509, "NL", None)
    assert body["criteria"] == ["many_ports", "top_bytes"]
    assert body["stats"]["ports"] == 51
    assert body["stats"]["max_ports_per_destination"] == 51


def test_detail_of_origin_without_criteria(api: TestClient) -> None:
    body = api.get("/api/origins/10.0.0.7").json()
    assert body["criteria"] == []
    assert body["stats"]["ports"] == 50


def test_detail_without_traffic_in_period(api: TestClient) -> None:
    body = api.get(
        "/api/origins/10.0.0.1",
        params={"from": "2026-09-15T13:00:00Z", "to": "2026-09-15T14:00:00Z"},
    ).json()
    assert body["stats"] is None
    assert body["criteria"] == []
    assert body["indicator"]["category"] == "scan"


def test_detail_unknown_and_invalid_ip(api: TestClient) -> None:
    assert api.get("/api/origins/10.9.9.9").status_code == 404
    assert api.get("/api/origins/not-an-ip").status_code == 422
    assert api.get("/api/origins/10.9.9.9/flows").status_code == 404


def test_origin_timeseries(api: TestClient) -> None:
    body = api.get("/api/origins/10.0.0.1/timeseries", params={"bucket": 60}).json()
    assert [p["bytes"] for p in body["points"]][:3] == [1000, 2000, 0]
    assert sum(p["flows"] for p in body["points"]) == 2


def test_origin_destinations(api: TestClient) -> None:
    body = api.get("/api/origins/10.0.0.8/destinations", params={"page_size": 5}).json()
    assert body["total"] == 21
    assert len(body["items"]) == 5
    assert body["items"][0]["dst_ip"] == "198.51.100.1"


def test_origin_ports_exclude_icmp_and_group_by_protocol(api: TestClient) -> None:
    assert api.get("/api/origins/10.0.0.2/ports").json()["total"] == 0
    body = api.get("/api/origins/10.0.0.3/ports").json()
    assert body["items"] == [
        {"port": 33000, "protocol": "UDP", "flows": 1, "bytes": 5000, "packets": 4,
         "destinations": 1}
    ]  # fmt: skip


def test_origin_flows_pagination_and_sort(api: TestClient) -> None:
    body = api.get(
        "/api/origins/10.0.0.9/flows", params={"page_size": 10, "page": 6, "order": "desc"}
    ).json()
    assert body["total"] == 51
    assert [f["dst_port"] for f in body["items"]] == [1]
    by_bytes = api.get("/api/origins/10.0.0.1/flows", params={"sort": "bytes"}).json()
    assert [f["bytes"] for f in by_bytes["items"]] == [1000, 2000]
