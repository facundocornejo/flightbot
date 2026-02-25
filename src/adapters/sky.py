"""Sky Airline (H2) price adapter.

Sky Airline expone una API REST con autenticación via API key pública
de Azure API Management. La key está hardcodeada en su frontend web.

Endpoint: POST https://api.skyairline.com/shopping-lowest-fares/lowest-fares/v1/search
Auth: Header ocp-apim-subscription-key (API key pública)
"""

import asyncio
import logging
from datetime import date, timedelta

import httpx

from src.adapters.base import BaseAdapter
from src.models import AppSettings, PriceResult, RouteConfig

logger = logging.getLogger(__name__)

# Endpoint de búsqueda de tarifas bajas de Sky
SKY_API_URL = "https://api.skyairline.com/shopping-lowest-fares/lowest-fares/v1/search"

# API key pública extraída del frontend de Sky (Azure APIM)
# NOTA: Esta key es pública (visible en el JavaScript del sitio de Sky).
# Si deja de funcionar (401/403), hay que extraer la nueva key del sitio.
SKY_API_KEY = "4c998b33d2aa4e8aba0f9a63d4c04d7d"

# Sky usa códigos de CIUDAD en vez de aeropuerto para origen
# Mapeo: código IATA de aeropuerto → código de ciudad que usa Sky
AIRPORT_TO_CITY_CODE: dict[str, str] = {
    "EZE": "BUE",
    "AEP": "BUE",
    "ROS": "ROS",
    "COR": "COR",
    "MDZ": "MDZ",
}

# Cada request con dateFlexibility=14 cubre ±14 días = ~28 días de ventana
DAYS_PER_REQUEST = 28
FLEXIBILITY_DAYS = 14


class SkyAdapter(BaseAdapter):
    """Adapter for Sky Airline lowest fares API."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__(settings)
        self._api_key_failed = False  # Flag para no reintentar si la key expiró

    @property
    def source_name(self) -> str:
        return "sky"

    async def fetch_prices(self, route: RouteConfig) -> list[PriceResult]:
        """Fetch prices from Sky Airline API.

        Escanea en ventanas de ~28 días (dateFlexibility=14) hasta cubrir
        todos los meses configurados en months_ahead.
        """
        # Si ya detectamos que la API key no funciona, no reintentar
        if self._api_key_failed:
            logger.warning("Sky: API key marcada como inválida, salteando.")
            return []

        results: list[PriceResult] = []
        seen_dates: set[str] = set()

        today = date.today()
        total_days = route.months_ahead * 30  # Aproximación de días totales

        # Calcular cuántos requests necesitamos para cubrir el rango
        num_requests = (total_days // DAYS_PER_REQUEST) + 1

        # Mapear código de aeropuerto a código de ciudad para Sky
        city_origin = AIRPORT_TO_CITY_CODE.get(route.origin, route.origin)

        logger.info(
            "Sky: escaneando %s(%s) → %s (%d requests de %d días)",
            route.origin, city_origin, route.destination,
            num_requests, DAYS_PER_REQUEST,
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            for i in range(num_requests):
                # Centrar cada request 28 días después del anterior
                center_date = today + timedelta(days=FLEXIBILITY_DAYS + (i * DAYS_PER_REQUEST))

                try:
                    prices = await self._fetch_window(
                        client, route, city_origin, center_date, seen_dates,
                    )
                    results.extend(prices)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code in (401, 403):
                        # La API key probablemente fue rotada
                        logger.error(
                            "Sky: API key rechazada (HTTP %d). "
                            "Probablemente fue rotada. Actualizar SKY_API_KEY.",
                            e.response.status_code,
                        )
                        self._api_key_failed = True
                        return results  # Devolver lo que tengamos hasta ahora
                    logger.warning("Sky: error HTTP %d: %s", e.response.status_code, e)
                except Exception as e:
                    logger.warning(
                        "Sky: error al consultar %s→%s ventana %s: %s",
                        route.origin, route.destination, center_date, e,
                    )

                await asyncio.sleep(self.settings.delay_between_requests_seconds)

        logger.info(
            "Sky: encontrados %d precios para %s → %s",
            len(results), route.origin, route.destination,
        )
        return results

    @property
    def api_key_failed(self) -> bool:
        """Whether the API key has been detected as invalid."""
        return self._api_key_failed

    async def _fetch_window(
        self,
        client: httpx.AsyncClient,
        route: RouteConfig,
        city_origin: str,
        center_date: date,
        seen_dates: set[str],
    ) -> list[PriceResult]:
        """Fetch prices for a ~28-day window centered on center_date.

        Hace un POST a la API de Sky y parsea la respuesta.
        Solo incluye vuelos con isAvailable=True y fechas no duplicadas.
        """
        body = {
            "currency": "ARS",
            "passengerCount": [{"ptc": "ADT", "quantity": 1}],
            "itineraryParts": [
                {
                    "origin": city_origin,
                    "destination": route.destination,
                    "departureDate": center_date.isoformat(),
                    "dateFlexibility": FLEXIBILITY_DAYS,
                }
            ],
        }

        headers = {
            "Content-Type": "application/json",
            "ocp-apim-subscription-key": SKY_API_KEY,
            "channel": "WEB",
            "homemarket": "AR",
            "pointofsale": "AR",
            "User-Agent": self.settings.user_agent,
        }

        response = await client.post(SKY_API_URL, json=body, headers=headers)
        response.raise_for_status()

        data = response.json()

        # La respuesta tiene itineraryParts como lista en el primer nivel
        itinerary_parts = data.get("itineraryParts", [])

        results: list[PriceResult] = []
        for part in itinerary_parts:
            # Solo procesar vuelos disponibles
            if not part.get("isAvailable", False):
                continue

            flight_date = part.get("departureDate", "")
            if not flight_date or flight_date in seen_dates:
                continue

            seen_dates.add(flight_date)

            # Extraer información de pricing
            pricing = part.get("pricingInfo", {})
            price = pricing.get("baseFareWithTaxes", 0)
            seats_info = pricing.get("seatsRemaining", {})
            seats = seats_info.get("number") if seats_info else None

            # Extraer número de vuelo del primer segmento
            segments = part.get("segments", [])
            flight_number = ""
            if segments:
                airline_code = segments[0].get("operatingAirlineCode", "H2")
                flight_num = segments[0].get("flightNumber", "")
                flight_number = f"{airline_code}{flight_num}"

            # Calcular duración total
            duration = part.get("totalDuration")

            results.append(
                PriceResult(
                    source=self.source_name,
                    airline="Sky Airline",
                    origin=part.get("origin", route.origin),
                    destination=part.get("destination", route.destination),
                    date=flight_date,
                    price=float(price),
                    currency="ARS",
                    stops=int(part.get("stops", 0)),
                    flight_number=flight_number,
                    seats_remaining=int(seats) if seats is not None else None,
                    duration_minutes=int(duration) if duration else None,
                )
            )

        return results
