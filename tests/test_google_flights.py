"""Tests for the Google Flights adapter (the only active source).

Tests de la lógica pura del adapter: generación de fechas de escaneo
(ventana explícita y modo clásico) y serialización de resultados v3
que cruza la frontera del subproceso.
"""

from dataclasses import dataclass, field
from datetime import date

from src.adapters.google_flights import (
    DAYS_BETWEEN_SCANS,
    GoogleFlightsAdapter,
    _serialize_flights,
)
from src.models import RouteConfig

TODAY = date(2026, 7, 8)


def _make_route(**overrides) -> RouteConfig:
    """Helper para crear rutas de prueba estilo BA→REC."""
    defaults = dict(
        origin="EZE",
        destination="REC",
        sources=["google_flights"],
        threshold_usd=550,
    )
    defaults.update(overrides)
    return RouteConfig(**defaults)


# ─── _build_scan_dates: modo ventana explícita ───


def test_window_scans_between_from_and_to():
    """Ventana futura completa: escanea desde depart_from cada N días."""
    route = _make_route(depart_from="2026-08-01", depart_to="2026-08-31")
    dates = GoogleFlightsAdapter._build_scan_dates(route, TODAY)
    assert dates[0] == date(2026, 8, 1)
    assert all(d <= date(2026, 8, 31) for d in dates)
    assert (dates[1] - dates[0]).days == DAYS_BETWEEN_SCANS


def test_window_start_in_past_is_clamped_to_tomorrow():
    """Si la ventana ya empezó, arranca mañana (nunca escanear el pasado)."""
    route = _make_route(depart_from="2026-07-01", depart_to="2026-07-20")
    dates = GoogleFlightsAdapter._build_scan_dates(route, TODAY)
    assert dates[0] == TODAY + (date(2026, 7, 9) - TODAY)  # mañana
    assert all(d > TODAY for d in dates)


def test_window_fully_in_past_yields_no_dates():
    """Ventana ya vencida: no hay nada que escanear."""
    route = _make_route(depart_from="2026-05-01", depart_to="2026-06-01")
    dates = GoogleFlightsAdapter._build_scan_dates(route, TODAY)
    assert dates == []


def test_invalid_window_falls_back_to_classic_mode():
    """Fechas malformadas: cae al modo clásico (months_ahead) sin crashear."""
    route = _make_route(depart_from="not-a-date", depart_to="2026-08-31", months_ahead=2)
    dates = GoogleFlightsAdapter._build_scan_dates(route, TODAY)
    assert dates  # generó fechas igual
    assert dates[0] > TODAY
    assert (dates[-1] - TODAY).days <= 2 * 30


# ─── _build_scan_dates: modo clásico ───


def test_classic_mode_respects_active_months():
    """Con active_months, solo genera fechas de esos meses."""
    route = _make_route(months_ahead=6, active_months=[9, 10])
    dates = GoogleFlightsAdapter._build_scan_dates(route, TODAY)
    assert dates
    assert all(d.month in (9, 10) for d in dates)


def test_classic_mode_without_active_months_scans_everything():
    """Sin active_months, genera fechas continuas cada N días."""
    route = _make_route(months_ahead=1, active_months=[])
    dates = GoogleFlightsAdapter._build_scan_dates(route, TODAY)
    assert dates[0] == date(2026, 7, 9)  # mañana
    assert (dates[-1] - TODAY).days <= 30


# ─── _serialize_flights (resultados fast-flights v3) ───


@dataclass
class _FakeSegment:
    duration: int = 180


@dataclass
class _FakeFlight:
    """Imita el modelo Flights de fast-flights v3."""

    price: int = 601
    airlines: list = field(default_factory=lambda: ["Ethiopian", "Azul"])
    flights: list = field(default_factory=lambda: [_FakeSegment(), _FakeSegment()])


def test_serialize_joins_airlines_and_counts_stops():
    """Aerolíneas unidas por coma; N segmentos = N-1 escalas."""
    data = _serialize_flights([_FakeFlight()])
    assert data == [{"name": "Ethiopian, Azul", "price": 601, "stops": 1}]


def test_serialize_direct_flight_has_zero_stops():
    """Un solo segmento = vuelo directo (0 escalas)."""
    data = _serialize_flights([_FakeFlight(airlines=["Gol"], flights=[_FakeSegment()])])
    assert data[0]["stops"] == 0
    assert data[0]["name"] == "Gol"


def test_serialize_empty_airlines_gives_none_name():
    """Sin aerolíneas conocidas, name queda None (el engine pone 'Unknown')."""
    data = _serialize_flights([_FakeFlight(airlines=[])])
    assert data[0]["name"] is None


def test_serialize_empty_result_list():
    """Lista vacía (FlightsNotFound) no rompe."""
    assert _serialize_flights([]) == []
