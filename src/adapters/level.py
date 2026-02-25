"""Level Airlines price adapter.

Level (aerolínea low-cost del grupo IAG) expone una API pública de calendario
de precios sin autenticación. Devuelve precios en USD para rutas Europa-América.

Endpoint: GET https://www.flylevel.com/nwe/flights/api/calendar/
Params: triptype, origin, destination, month, year, currencyCode, originType
Auth: Ninguna
"""

import asyncio
import logging
from datetime import date

import httpx

from src.adapters.base import BaseAdapter
from src.models import AppSettings, PriceResult, RouteConfig

logger = logging.getLogger(__name__)

# URL base de la API de calendario de Level
LEVEL_CALENDAR_URL = "https://www.flylevel.com/nwe/flights/api/calendar/"

# Level solo soporta estas monedas; si pedís otra devuelve EUR
LEVEL_CURRENCY = "USD"


class LevelAdapter(BaseAdapter):
    """Adapter for Level Airlines flight calendar API."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__(settings)

    @property
    def source_name(self) -> str:
        return "level"

    async def fetch_prices(self, route: RouteConfig) -> list[PriceResult]:
        """Fetch monthly calendar prices from Level API.

        Escanea mes por mes desde el mes actual hasta months_ahead meses
        en el futuro. Cada request devuelve precios por día del mes.
        Usa un set para evitar duplicados entre meses solapados.
        """
        results: list[PriceResult] = []
        seen_dates: set[str] = set()  # Para evitar duplicados entre meses solapados

        today = date.today()

        # Generar lista de meses a consultar
        months_to_check: list[tuple[int, int]] = []
        for i in range(route.months_ahead):
            # Calcular mes/año sumando i meses al actual
            target_month = today.month + i
            target_year = today.year + (target_month - 1) // 12
            target_month = ((target_month - 1) % 12) + 1
            months_to_check.append((target_year, target_month))

        logger.info(
            "Level: escaneando %s → %s (%d meses)",
            route.origin, route.destination, len(months_to_check),
        )

        # Determinar tipo de viaje para el parámetro triptype
        trip_type = "RT" if route.trip_type == "round_trip" else "OW"

        async with httpx.AsyncClient(timeout=30.0) as client:
            for year, month in months_to_check:
                try:
                    prices = await self._fetch_month(
                        client, route, year, month, trip_type, seen_dates,
                    )
                    results.extend(prices)
                except Exception as e:
                    # Si falla un mes, loggear y seguir con el siguiente
                    logger.warning(
                        "Level: error al consultar %s→%s %d/%d: %s",
                        route.origin, route.destination, month, year, e,
                    )

                # Delay entre requests para no sobrecargar la API
                await asyncio.sleep(self.settings.delay_between_requests_seconds)

        logger.info(
            "Level: encontrados %d precios para %s → %s",
            len(results), route.origin, route.destination,
        )
        return results

    async def _fetch_month(
        self,
        client: httpx.AsyncClient,
        route: RouteConfig,
        year: int,
        month: int,
        trip_type: str,
        seen_dates: set[str],
    ) -> list[PriceResult]:
        """Fetch prices for a specific month.

        Hace el request HTTP y parsea la respuesta para un mes específico.
        Filtra fechas ya vistas (por solapamiento entre meses).
        """
        params = {
            "triptype": trip_type,
            "origin": route.origin,
            "destination": route.destination,
            "month": month,
            "year": year,
            "currencyCode": LEVEL_CURRENCY,
            "originType": "flights",
        }

        response = await client.get(
            LEVEL_CALENDAR_URL,
            params=params,
            headers={"User-Agent": self.settings.user_agent},
        )
        response.raise_for_status()

        data = response.json()

        # La respuesta tiene estructura: {"data": {"dayPrices": [...]}}
        day_prices = data.get("data", {}).get("dayPrices", [])

        results: list[PriceResult] = []
        for day in day_prices:
            flight_date = day.get("date", "")
            price = day.get("price")

            # Saltar si no hay fecha o precio, o si ya procesamos esta fecha
            if not flight_date or price is None or flight_date in seen_dates:
                continue

            seen_dates.add(flight_date)

            # Extraer tags (puede ser null o una lista)
            tags = day.get("tags") or []

            results.append(
                PriceResult(
                    source=self.source_name,
                    airline="Level",
                    origin=route.origin,
                    destination=route.destination,
                    date=flight_date,
                    price=float(price),
                    currency=LEVEL_CURRENCY,
                    stops=0,  # Level vuela directo en sus rutas principales
                    tags=tags,
                )
            )

        return results
