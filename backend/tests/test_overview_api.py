"""Testes da API do panorama sobre as fixtures.

Fixtures (todas em 15/09/2026, UTC):
  12:00:00  10.0.0.1 -> 203.0.113.10:443  TCP   1000 B  10 pkts  (indicador)
  12:01:00  10.0.0.1 -> 203.0.113.11:80   TCP   2000 B  20 pkts  (indicador)
  12:02:00  10.0.0.2 -> 198.51.100.5      ICMP    84 B   1 pkt   (duas amostras iguais)
  12:03:00  10.0.0.3 -> 192.0.2.7:33000   UDP   5000 B   4 pkts
"""

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def test_summary_totals_and_indicator_share(client: TestClient) -> None:
    body = client.get("/api/overview/summary").json()
    assert body["period"] == {"from": "2026-09-15T12:00:00Z", "to": "2026-09-15T12:03:01Z"}
    assert (body["bytes"], body["packets"], body["flows"]) == (8168, 36, 5)
    assert (body["sources"], body["destinations"]) == (3, 4)
    assert body["indicators"] == {
        "bytes": 3000,
        "packets": 30,
        "flows": 2,
        "sources": 1,
        "bytes_pct": 36.73,
    }


def test_summary_respects_period(client: TestClient) -> None:
    body = client.get(
        "/api/overview/summary",
        params={"from": "2026-09-15T12:01:00Z", "to": "2026-09-15T12:03:00Z"},
    ).json()
    assert (body["bytes"], body["flows"]) == (2168, 3)


def test_summary_empty_period_returns_zeros(client: TestClient) -> None:
    body = client.get(
        "/api/overview/summary",
        params={"from": "2026-09-16T00:00:00Z", "to": "2026-09-16T01:00:00Z"},
    ).json()
    assert body["bytes"] == 0
    assert body["indicators"]["bytes_pct"] == 0.0


def test_period_rejects_inverted_range(client: TestClient) -> None:
    response = client.get(
        "/api/overview/summary",
        params={"from": "2026-09-15T13:00:00Z", "to": "2026-09-15T12:00:00Z"},
    )
    assert response.status_code == 422


def test_naive_datetimes_are_utc(client: TestClient) -> None:
    body = client.get(
        "/api/overview/summary",
        params={"from": "2026-09-15T12:03:00", "to": "2026-09-15T12:04:00"},
    ).json()
    assert body["bytes"] == 5000


def test_timeseries_fixed_bucket(client: TestClient) -> None:
    body = client.get("/api/overview/timeseries", params={"bucket": 60}).json()
    assert body["bucket_seconds"] == 60
    assert [(p["bytes"], p["packets"], p["flows"]) for p in body["points"]] == [
        (1000, 10, 1),
        (2000, 20, 1),
        (168, 2, 2),
        (5000, 4, 1),
    ]


def test_timeseries_fills_empty_buckets_with_zero(client: TestClient) -> None:
    body = client.get(
        "/api/overview/timeseries",
        params={"from": "2026-09-15T12:00:00Z", "to": "2026-09-15T12:06:00Z", "bucket": 60},
    ).json()
    assert [p["ts"] for p in body["points"]][-1] == "2026-09-15T12:05:00Z"
    assert [p["bytes"] for p in body["points"]] == [1000, 2000, 168, 5000, 0, 0]


def test_timeseries_auto_bucket_for_six_hours(client: TestClient) -> None:
    body = client.get(
        "/api/overview/timeseries",
        params={"from": "2026-09-15T12:00:00Z", "to": "2026-09-15T18:00:00Z"},
    ).json()
    assert body["bucket_seconds"] == 120
    assert len(body["points"]) == 180
    assert sum(p["bytes"] for p in body["points"]) == 8168


def test_timeseries_rejects_too_many_points(client: TestClient) -> None:
    response = client.get(
        "/api/overview/timeseries",
        params={"from": "2026-09-15T00:00:00Z", "to": "2026-09-16T00:00:00Z", "bucket": 1},
    )
    assert response.status_code == 422


def test_protocols(client: TestClient) -> None:
    items = client.get("/api/overview/protocols").json()["items"]
    assert items == [
        {"protocol": "UDP", "bytes": 5000, "packets": 4, "flows": 1},
        {"protocol": "TCP", "bytes": 3000, "packets": 30, "flows": 2},
        {"protocol": "ICMP", "bytes": 168, "packets": 2, "flows": 2},
    ]


def test_top_ports_excludes_icmp(client: TestClient) -> None:
    items = client.get("/api/overview/top-ports").json()["items"]
    assert 0 not in [item["port"] for item in items]
    assert [item["port"] for item in items] == [33000, 80, 443]


def test_top_ports_limit_and_order(client: TestClient) -> None:
    body = client.get("/api/overview/top-ports", params={"limit": 1, "order_by": "bytes"}).json()
    assert body["order_by"] == "bytes"
    assert body["items"] == [{"port": 33000, "flows": 1, "bytes": 5000, "packets": 4, "sources": 1}]
