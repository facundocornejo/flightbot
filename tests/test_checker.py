"""Tests for the price threshold checker.

Tests del checker: verifica comparación directa por moneda,
conversión con tipo de cambio manual, y manejo de aeropuertos alternativos.
"""

import pytest

from src.checker import check_prices
from src.models import AppSettings, PriceResult, RouteConfig


@pytest.fixture
def settings():
    """Settings con tipo de cambio manual 1 USD = 1200 ARS."""
    return AppSettings(manual_usd_to_ars=1200.0)


@pytest.fixture
def routes():
    """Rutas de prueba con umbrales en ambas monedas."""
    return [
        RouteConfig(
            origin="EZE",
            destination="BCN",
            sources=["level"],
            threshold_usd=550,
        ),
        RouteConfig(
            origin="EZE",
            destination="SSA",
            sources=["sky"],
            threshold_ars=500000,
            threshold_usd=400,
        ),
    ]


def _make_result(origin: str, dest: str, price: float, currency: str) -> PriceResult:
    """Helper para crear PriceResult de prueba."""
    return PriceResult(
        source="test",
        airline="TestAir",
        origin=origin,
        destination=dest,
        date="2026-06-01",
        price=price,
        currency=currency,
    )


def test_usd_below_threshold(settings, routes):
    """Precio en USD bajo el umbral USD → debe alertar."""
    results = [_make_result("EZE", "BCN", 500, "USD")]
    alerts = check_prices(results, routes, settings)
    assert len(alerts) == 1
    assert alerts[0].price == 500


def test_usd_above_threshold(settings, routes):
    """Precio en USD sobre el umbral USD → no debe alertar."""
    results = [_make_result("EZE", "BCN", 600, "USD")]
    alerts = check_prices(results, routes, settings)
    assert len(alerts) == 0


def test_ars_below_threshold(settings, routes):
    """Precio en ARS bajo el umbral ARS → debe alertar."""
    results = [_make_result("EZE", "SSA", 400000, "ARS")]
    alerts = check_prices(results, routes, settings)
    assert len(alerts) == 1


def test_ars_above_threshold(settings, routes):
    """Precio en ARS sobre el umbral ARS → no debe alertar."""
    results = [_make_result("EZE", "SSA", 600000, "ARS")]
    alerts = check_prices(results, routes, settings)
    assert len(alerts) == 0


def test_cross_currency_usd_to_ars(settings, routes):
    """Precio en USD convertido a ARS cae bajo el umbral ARS → debe alertar."""
    # USD 350 × 1200 = ARS 420,000 < umbral ARS 500,000
    results = [_make_result("EZE", "SSA", 350, "USD")]
    alerts = check_prices(results, routes, settings)
    assert len(alerts) == 1


def test_cross_currency_ars_to_usd(settings, routes):
    """Precio en ARS convertido a USD cae bajo el umbral USD → debe alertar."""
    # ARS 400,000 ÷ 1200 = USD 333 < umbral USD 400
    results = [_make_result("EZE", "SSA", 400000, "ARS")]
    alerts = check_prices(results, routes, settings)
    assert len(alerts) == 1


def test_alternative_airport_aep_matches_eze(settings, routes):
    """AEP (Aeroparque) debe matchear con ruta configurada como EZE."""
    results = [_make_result("AEP", "SSA", 400000, "ARS")]
    alerts = check_prices(results, routes, settings)
    # AEP es equivalente a EZE, debe encontrar la ruta EZE→SSA
    assert len(alerts) == 1


def test_unknown_route_ignored(settings, routes):
    """Ruta que no está configurada → debe ignorarse sin error."""
    results = [_make_result("GRU", "MIA", 300, "USD")]
    alerts = check_prices(results, routes, settings)
    assert len(alerts) == 0


def test_exact_threshold_triggers(settings, routes):
    """Precio exactamente igual al umbral → debe alertar (<=)."""
    results = [_make_result("EZE", "BCN", 550, "USD")]
    alerts = check_prices(results, routes, settings)
    assert len(alerts) == 1
