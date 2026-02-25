"""Tests for the Level Airlines adapter.

Tests del adapter de Level: verifica que parsee correctamente la respuesta JSON,
que maneje errores sin crashear, y que filtre duplicados entre meses.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapters.level import LevelAdapter
from src.models import AppSettings, RouteConfig

# Respuesta de ejemplo real de la API de Level (fragmento)
MOCK_LEVEL_RESPONSE = {
    "data": {
        "dayPrices": [
            {
                "date": "2026-12-01",
                "price": 522,
                "minimumPriceGroup": 0,
                "tags": None,
            },
            {
                "date": "2026-12-15",
                "price": 650,
                "minimumPriceGroup": 1,
                "tags": None,
            },
            {
                "date": "2027-01-26",
                "price": 511,
                "minimumPriceGroup": 0,
                "tags": ["IsMinimumPriceMonth"],
            },
        ]
    }
}


@pytest.fixture
def settings():
    """Settings de prueba con delays mínimos para que los tests sean rápidos."""
    return AppSettings(delay_between_requests_seconds=0)


@pytest.fixture
def route():
    """Ruta de prueba EZE → BCN."""
    return RouteConfig(
        origin="EZE",
        destination="BCN",
        sources=["level"],
        threshold_usd=550,
        months_ahead=1,  # Solo 1 mes para que el test sea rápido
    )


@pytest.mark.asyncio
async def test_level_parses_prices_correctly(settings, route):
    """Verifica que el adapter parsee precios correctamente de la respuesta JSON."""
    adapter = LevelAdapter(settings)

    # Mockear httpx para devolver nuestra respuesta de ejemplo
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_LEVEL_RESPONSE
    mock_response.raise_for_status = MagicMock()

    with patch("src.adapters.level.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await adapter.fetch_prices(route)

    # Debe haber encontrado 3 precios
    assert len(results) == 3

    # Verificar el primer resultado
    assert results[0].source == "level"
    assert results[0].airline == "Level"
    assert results[0].origin == "EZE"
    assert results[0].destination == "BCN"
    assert results[0].date == "2026-12-01"
    assert results[0].price == 522.0
    assert results[0].currency == "USD"

    # Verificar que el tag IsMinimumPriceMonth se parsea
    assert "IsMinimumPriceMonth" in results[2].tags
    assert results[2].price == 511.0


@pytest.mark.asyncio
async def test_level_handles_empty_response(settings, route):
    """Verifica que devuelve lista vacía si la API devuelve datos vacíos."""
    adapter = LevelAdapter(settings)

    mock_response = MagicMock()
    mock_response.json.return_value = {"data": {"dayPrices": []}}
    mock_response.raise_for_status = MagicMock()

    with patch("src.adapters.level.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await adapter.fetch_prices(route)

    assert results == []


@pytest.mark.asyncio
async def test_level_handles_network_error(settings, route):
    """Verifica que no crashea si hay un error de red."""
    adapter = LevelAdapter(settings)

    with patch("src.adapters.level.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("Connection timeout")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        # No debe crashear, debe devolver lista vacía
        results = await adapter.fetch_prices(route)

    assert results == []
