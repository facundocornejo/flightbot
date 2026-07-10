"""Tests for the Travelpayouts / Aviasales Data API adapter.

Tests del adapter de Travelpayouts: skip sin token, mapeo de tickets
cacheados a PriceResult, filtros de ventana/duración, y manejo de errores.
Usa httpx.MockTransport para no pegarle a la API real.
"""

import httpx
import pytest

from src.adapters.travelpayouts import TravelpayoutsAdapter
from src.models import AppSettings, RouteConfig

# Ticket de ejemplo con la forma real de aviasales/v3/prices_for_dates
MOCK_TICKET = {
    "origin": "EZE",
    "destination": "GIG",
    "origin_airport": "EZE",
    "destination_airport": "GIG",
    "price": 320,
    "currency": "usd",
    "airline": "G3",
    "flight_number": "7621",
    "departure_at": "2099-12-01T07:00:00-03:00",
    "return_at": "2099-12-06T14:30:00-03:00",
    "transfers": 1,
    "return_transfers": 0,
    "duration": 780,
    "link": "/search/EZE0112GIG0612...",
}


def _make_response(tickets: list[dict]) -> dict:
    return {"success": True, "data": tickets, "error": None}


def _make_settings() -> AppSettings:
    # delay 0 para que los tests no duerman
    return AppSettings(
        delay_between_requests_seconds=0,
        trip_duration_min_days=5,
        trip_duration_max_days=7,
    )


def _make_route(**overrides) -> RouteConfig:
    defaults = dict(
        origin="EZE",
        destination="GIG",
        sources=["travelpayouts"],
        threshold_usd=400,
        depart_from="2099-12-01",
        depart_to="2099-12-03",
        scan_step_days=1,
        trip_type="round_trip",
    )
    defaults.update(overrides)
    return RouteConfig(**defaults)


def _make_adapter(
    monkeypatch,
    transport: httpx.MockTransport | None,
    with_token: bool = True,
) -> TravelpayoutsAdapter:
    if with_token:
        monkeypatch.setenv("TRAVELPAYOUTS_TOKEN", "test-token")
    else:
        monkeypatch.delenv("TRAVELPAYOUTS_TOKEN", raising=False)
    monkeypatch.delenv("TRAVELPAYOUTS_MARKET", raising=False)
    adapter = TravelpayoutsAdapter(_make_settings())
    adapter._transport = transport
    return adapter


@pytest.mark.asyncio
async def test_skips_without_token(monkeypatch):
    """Sin token: devuelve vacío sin hacer ningún request."""
    adapter = _make_adapter(monkeypatch, transport=None, with_token=False)
    results = await adapter.fetch_prices(_make_route())
    assert results == []


@pytest.mark.asyncio
async def test_maps_tickets_to_price_results(monkeypatch):
    """Flujo feliz: ticket cacheado → PriceResult correcto."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Access-Token"] == "test-token"
        assert request.url.params["origin"] == "EZE"
        assert request.url.params["destination"] == "GIG"
        assert request.url.params["departure_at"] == "2099-12"
        assert request.url.params["one_way"] == "false"
        return httpx.Response(200, json=_make_response([MOCK_TICKET]))

    adapter = _make_adapter(monkeypatch, httpx.MockTransport(handler))
    results = await adapter.fetch_prices(_make_route())

    assert len(results) == 1
    r = results[0]
    assert r.source == "travelpayouts"
    assert r.price == 320.0
    assert r.currency == "USD"
    assert r.origin == "EZE"
    assert r.destination == "GIG"
    assert r.stops == 1
    assert r.airline == "GOL"
    assert r.flight_number == "7621"
    assert r.duration_minutes == 780
    # round-trip con formato compartido con google_flights (route_key dedup)
    assert r.date == "2099-12-01 → 2099-12-06"


@pytest.mark.asyncio
async def test_filters_departures_outside_window(monkeypatch):
    """Tickets del mismo mes pero fuera de la ventana de salida se descartan."""
    outside = dict(MOCK_TICKET, departure_at="2099-12-15T07:00:00-03:00",
                   return_at="2099-12-20T14:30:00-03:00")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_make_response([MOCK_TICKET, outside]))

    adapter = _make_adapter(monkeypatch, httpx.MockTransport(handler))
    results = await adapter.fetch_prices(_make_route())

    assert len(results) == 1
    assert results[0].date.startswith("2099-12-01")


@pytest.mark.asyncio
async def test_filters_trip_duration(monkeypatch):
    """Round-trips con duración fuera de [min, max] días se descartan."""
    too_long = dict(MOCK_TICKET, return_at="2099-12-25T14:30:00-03:00")  # 24 días
    no_return = {k: v for k, v in MOCK_TICKET.items() if k != "return_at"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_make_response([too_long, no_return]))

    adapter = _make_adapter(monkeypatch, httpx.MockTransport(handler))
    results = await adapter.fetch_prices(_make_route())
    assert results == []


@pytest.mark.asyncio
async def test_accepts_departures_off_scan_step(monkeypatch):
    """El paso de escaneo NO filtra al cache: cualquier salida en ventana vale.

    Con scan_step_days=7 y ventana 1-14 dic, Google solo consultaría el 1 y
    el 8 — pero una oferta cacheada que sale el 5 es señal válida igual.
    """
    off_step = dict(MOCK_TICKET, departure_at="2099-12-05T07:00:00-03:00",
                    return_at="2099-12-10T14:30:00-03:00")  # 5 días

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_make_response([off_step]))

    adapter = _make_adapter(monkeypatch, httpx.MockTransport(handler))
    route = _make_route(depart_to="2099-12-14", scan_step_days=7)
    results = await adapter.fetch_prices(route)

    assert len(results) == 1
    assert results[0].date == "2099-12-05 → 2099-12-10"


@pytest.mark.asyncio
async def test_relaxed_duration_mode(monkeypatch):
    """Con travelpayouts_match_trip_duration=False acepta cualquier vuelta."""
    long_trip = dict(MOCK_TICKET, return_at="2099-12-16T14:30:00-03:00")  # 15 días
    no_return = {k: v for k, v in MOCK_TICKET.items() if k != "return_at"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_make_response([long_trip, no_return]))

    adapter = _make_adapter(monkeypatch, httpx.MockTransport(handler))
    adapter.settings.travelpayouts_match_trip_duration = False
    results = await adapter.fetch_prices(_make_route())

    # El de 15 días entra; el que no tiene vuelta sigue descartado (es round_trip)
    assert len(results) == 1
    assert results[0].date == "2099-12-01 → 2099-12-16"


@pytest.mark.asyncio
async def test_one_way_route(monkeypatch):
    """Rutas one-way: no exige return_at y usa one_way=true."""
    one_way_ticket = {k: v for k, v in MOCK_TICKET.items() if k != "return_at"}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["one_way"] == "true"
        return httpx.Response(200, json=_make_response([one_way_ticket]))

    adapter = _make_adapter(monkeypatch, httpx.MockTransport(handler))
    results = await adapter.fetch_prices(_make_route(trip_type="one_way"))

    assert len(results) == 1
    assert results[0].date == "2099-12-01"


@pytest.mark.asyncio
async def test_invalid_token_aborts_run(monkeypatch):
    """401/403: se marca auth_failed y no se insiste en la corrida."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"success": False, "error": "bad token"})

    adapter = _make_adapter(monkeypatch, httpx.MockTransport(handler))
    results = await adapter.fetch_prices(_make_route())

    assert results == []
    assert adapter._auth_failed is True
    assert calls["n"] == 1

    # Una segunda ruta tampoco consulta (corta al toque)
    results2 = await adapter.fetch_prices(_make_route())
    assert results2 == []
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_api_error_returns_empty(monkeypatch):
    """success=false o 500: warning y lista vacía, nunca crashea."""
    responses = iter([
        httpx.Response(200, json={"success": False, "data": {}, "error": "boom"}),
        httpx.Response(500, text="internal error"),
    ])

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    adapter = _make_adapter(monkeypatch, httpx.MockTransport(handler))
    assert await adapter.fetch_prices(_make_route()) == []
    assert await adapter.fetch_prices(_make_route()) == []


def test_malformed_ticket_is_skipped(monkeypatch):
    """Tickets con formato inesperado se descartan sin romper."""
    from datetime import date

    adapter = _make_adapter(monkeypatch, transport=None)
    bad_ticket = {"airline": "G3"}  # sin price ni departure_at
    result = adapter._ticket_to_result(
        bad_ticket, _make_route(), date(2099, 11, 30), True,
    )
    assert result is None
