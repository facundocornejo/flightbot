"""Tests for the Sky Airline adapter.

Tests del adapter de Sky: verifica parseo de respuesta, filtrado de vuelos
no disponibles, y manejo de API key expirada.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.adapters.sky import SkyAdapter
from src.models import AppSettings, RouteConfig

# Respuesta de ejemplo real de la API de Sky (fragmento)
MOCK_SKY_RESPONSE = {
    "code": 0,
    "message": "Success",
    "currency": "ARS",
    "itineraryParts": [
        {
            "stops": 0,
            "directionInd": "OneWay",
            "resBookDesigCode": None,
            "totalDuration": 0,
            "origin": "EZE",
            "destination": "SSA",
            "departureDate": "2026-02-24",
            "isAvailable": False,
            "segments": [],
            "pricingInfo": None,
        },
        {
            "directionInd": "OneWay",
            "resBookDesigCode": "A",
            "stops": 0,
            "totalDuration": 270,
            "origin": "EZE",
            "departureDate": "2026-02-27",
            "destination": "SSA",
            "isAvailable": True,
            "segments": [
                {
                    "departureDateTime": "2026-02-27T07:45:00",
                    "arrivalDateTime": "2026-02-27T12:15:00",
                    "flightNumber": "1820",
                    "operatingAirlineCode": "H2",
                    "elapsedTime": "270",
                    "origin": "EZE",
                    "destination": "SSA",
                }
            ],
            "pricingInfo": {
                "baseFare": 215450,
                "taxes": 185912.5,
                "baseFareWithTaxes": 401362.5,
                "seatsRemaining": {"number": 9, "belowMin": False},
            },
        },
    ],
}


@pytest.fixture
def settings():
    return AppSettings(delay_between_requests_seconds=0)


@pytest.fixture
def route():
    return RouteConfig(
        origin="EZE",
        destination="SSA",
        sources=["sky"],
        threshold_ars=500000,
        months_ahead=1,
    )


@pytest.mark.asyncio
async def test_sky_parses_available_flights(settings, route):
    """Verifica que solo parsea vuelos con isAvailable=True."""
    adapter = SkyAdapter(settings)

    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_SKY_RESPONSE
    mock_response.raise_for_status = MagicMock()

    with patch("src.adapters.sky.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await adapter.fetch_prices(route)

    # Solo 1 vuelo disponible de los 2 en la respuesta
    assert len(results) == 1
    assert results[0].price == 401362.5
    assert results[0].currency == "ARS"
    assert results[0].seats_remaining == 9
    assert results[0].flight_number == "H21820"
    assert results[0].stops == 0


@pytest.mark.asyncio
async def test_sky_handles_api_key_expired(settings, route):
    """Verifica que detecta API key expirada (401) y no reintenta."""
    adapter = SkyAdapter(settings)

    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Unauthorized", request=MagicMock(), response=mock_response,
    )

    with patch("src.adapters.sky.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        results = await adapter.fetch_prices(route)

    assert results == []
    assert adapter.api_key_failed is True
