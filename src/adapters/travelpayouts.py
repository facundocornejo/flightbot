"""Travelpayouts / Aviasales Data API price adapter.

Segunda fuente de precios (señal de tendencia): devuelve los tickets más
baratos que usuarios reales de Aviasales encontraron en las últimas 48 horas.
Son precios CACHEADOS (retención de hasta 7 días), no búsquedas en vivo —
sirven como red de seguridad y señal barata, no reemplazan a Google Flights.

Endpoint: GET https://api.travelpayouts.com/aviasales/v3/prices_for_dates
Docs: https://support.travelpayouts.com/hc/en-us/articles/203956163

Requiere token gratuito de https://www.travelpayouts.com (Profile → API token):
- TRAVELPAYOUTS_TOKEN (env var o GitHub secret)
- TRAVELPAYOUTS_MARKET (opcional): fuerza el market del cache (ej: "br", "us").
  Sin definir, la API lo infiere del origen.

Si no hay token configurado, el adapter se saltea con un log claro
(no rompe el run — Google Flights sigue siendo la fuente principal).
"""

import asyncio
import logging
import os
from datetime import date, datetime, timedelta

import httpx

from src.adapters.base import BaseAdapter
from src.adapters.scan_dates import departure_in_window
from src.models import AppSettings, PriceResult, RouteConfig

logger = logging.getLogger(__name__)

BASE_URL = "https://api.travelpayouts.com"
PRICES_PATH = "/aviasales/v3/prices_for_dates"

REQUEST_TIMEOUT_SECONDS = 30

# Máximo de registros por página (el máximo documentado de la API es 1000).
# Con un request por mes alcanza: la API devuelve lo más barato primero.
PAGE_LIMIT = 1000

# Nombres de aerolíneas por código IATA (la API devuelve solo el código).
# Cubre las que operan AR→BR; para el resto se muestra el código pelado.
AIRLINE_NAMES = {
    "G3": "GOL",
    "LA": "LATAM",
    "AR": "Aerolíneas Argentinas",
    "JA": "JetSmart",
    "FO": "Flybondi",
    "H2": "Sky Airline",
    "AD": "Azul",
    "CM": "Copa",
    "AV": "Avianca",
}


class TravelpayoutsAdapter(BaseAdapter):
    """Adapter for the Travelpayouts / Aviasales Data API (cached prices)."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__(settings)
        self._token = os.getenv("TRAVELPAYOUTS_TOKEN", "").strip()
        self._market = os.getenv("TRAVELPAYOUTS_MARKET", "").strip().lower()
        self._warned_no_token = False
        self._auth_failed = False
        # Transporte inyectable para tests (httpx.MockTransport)
        self._transport: httpx.AsyncBaseTransport | None = None

    @property
    def source_name(self) -> str:
        return "travelpayouts"

    async def _fetch_month(
        self,
        client: httpx.AsyncClient,
        route: RouteConfig,
        month: str,
        is_round_trip: bool,
    ) -> list[dict]:
        """Query cached prices for one departure month (YYYY-MM).

        Devuelve la lista cruda de tickets de la API (puede ser vacía).
        Lanza httpx.HTTPError ante errores de red; el caller decide.
        """
        params: dict[str, str | int] = {
            "origin": route.origin,
            "destination": route.destination,
            "departure_at": month,
            # one_way=false agrupa menos y devuelve más ofertas round-trip
            "one_way": "false" if is_round_trip else "true",
            "direct": "false",
            "sorting": "price",
            "limit": PAGE_LIMIT,
            # La doc oficial nombra el parámetro "currency" pero su request de
            # ejemplo usa "cy" — se mandan ambos por las dudas (el que sobre
            # se ignora) y la moneda real se lee de la respuesta.
            "currency": "usd",
            "cy": "usd",
        }
        if self._market:
            params["market"] = self._market

        response = await client.get(
            f"{BASE_URL}{PRICES_PATH}",
            params=params,
            headers={"X-Access-Token": self._token},
        )

        if response.status_code in (401, 403):
            # Token inválido: no insistir en esta corrida
            self._auth_failed = True
            logger.error(
                "Travelpayouts: token rechazado (%d). Verificá TRAVELPAYOUTS_TOKEN.",
                response.status_code,
            )
            return []
        if response.status_code == 429:
            logger.warning("Travelpayouts: rate limit (429), salteando consulta.")
            return []
        if response.status_code != 200:
            logger.warning(
                "Travelpayouts: respuesta %d para %s→%s %s: %s",
                response.status_code, route.origin, route.destination,
                month, response.text[:200],
            )
            return []

        payload = response.json()
        if not payload.get("success", False):
            logger.warning(
                "Travelpayouts: request falló para %s→%s %s: %s",
                route.origin, route.destination, month, payload.get("error"),
            )
            return []
        return payload.get("data") or []

    def _ticket_to_result(
        self,
        ticket: dict,
        route: RouteConfig,
        today: date,
        is_round_trip: bool,
    ) -> PriceResult | None:
        """Map a raw cached ticket to a PriceResult, filtering by scan window.

        Devuelve None si el ticket cae fuera de la ventana de fechas de la
        ruta, si la duración del viaje no entra en la configurada, o si el
        formato es inesperado.
        """
        try:
            depart = datetime.fromisoformat(ticket["departure_at"]).date()
            price = float(ticket["price"])
            currency = str(ticket.get("currency", "usd")).upper()
            return_raw = ticket.get("return_at")
            return_date = (
                datetime.fromisoformat(return_raw).date() if return_raw else None
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.debug("Travelpayouts: ticket con formato inesperado, salteado: %s", e)
            return None

        # El cache devuelve el mes entero: quedarse solo con las salidas
        # dentro de la ventana de la ruta. A diferencia de Google Flights,
        # acá NO aplica el paso de escaneo (el cache es gratis y cualquier
        # fecha del rango es señal válida).
        if not departure_in_window(route, depart, today):
            return None

        if is_round_trip:
            if return_date is None:
                return None
            # Filtro de duración configurable: estricto matchea el viaje real;
            # relajado acepta cualquier vuelta como señal de tendencia.
            if self.settings.travelpayouts_match_trip_duration:
                duration_days = (return_date - depart).days
                if not (
                    self.settings.trip_duration_min_days
                    <= duration_days
                    <= self.settings.trip_duration_max_days
                ):
                    return None

        code = str(ticket.get("airline", "")).strip()
        airline = AIRLINE_NAMES.get(code, code) or "Unknown"

        # Mismo formato de fecha que google_flights/amadeus para que la
        # deduplicación de alertas (route_key) funcione entre fuentes.
        date_display = depart.isoformat()
        if is_round_trip and return_date is not None:
            date_display = f"{depart.isoformat()} → {return_date.isoformat()}"

        transfers = int(ticket.get("transfers") or 0)
        duration_minutes = ticket.get("duration")

        return PriceResult(
            source=self.source_name,
            airline=airline,
            origin=route.origin,
            destination=route.destination,
            date=date_display,
            price=price,
            currency=currency,
            stops=transfers,
            flight_number=str(ticket.get("flight_number") or ""),
            duration_minutes=int(duration_minutes) if duration_minutes else None,
        )

    async def fetch_prices(self, route: RouteConfig) -> list[PriceResult]:
        """Fetch cached prices from the Aviasales Data API for the route."""
        if not self._token:
            if not self._warned_no_token:
                logger.info(
                    "Travelpayouts: sin token (TRAVELPAYOUTS_TOKEN), fuente salteada."
                )
                self._warned_no_token = True
            return []
        if self._auth_failed:
            return []

        today = date.today()
        # Meses a consultar: recorrer la ventana día por día (es barato) y
        # quedarse con los meses que tienen al menos una salida válida.
        # Un request por mes cubre todas las fechas de ese mes.
        start = today + timedelta(days=1)
        horizon = today + timedelta(days=route.months_ahead * 30 + 1)
        # La ventana explícita manda sobre months_ahead (igual que build_scan_dates)
        if route.depart_from:
            try:
                start = max(start, date.fromisoformat(route.depart_from))
            except ValueError:
                pass
        if route.depart_to:
            try:
                horizon = max(horizon, date.fromisoformat(route.depart_to))
            except ValueError:
                pass
        months_set: set[str] = set()
        current = start
        while current <= horizon:
            if departure_in_window(route, current, today):
                months_set.add(current.strftime("%Y-%m"))
            current += timedelta(days=1)
        months = sorted(months_set)
        if not months:
            return []
        is_round_trip = route.trip_type == "round_trip"

        logger.info(
            "Travelpayouts: consultando cache %s → %s (%d mes%s)",
            route.origin, route.destination,
            len(months), "es" if len(months) != 1 else "",
        )

        results: list[PriceResult] = []
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT_SECONDS,
            transport=self._transport,
        ) as client:
            for month in months:
                if self._auth_failed:
                    break
                try:
                    tickets = await self._fetch_month(
                        client, route, month, is_round_trip,
                    )
                except httpx.HTTPError as e:
                    logger.warning(
                        "Travelpayouts: error de red en %s→%s %s: %s",
                        route.origin, route.destination, month, e,
                    )
                    tickets = []

                for ticket in tickets:
                    result = self._ticket_to_result(
                        ticket, route, today, is_round_trip,
                    )
                    if result is not None:
                        results.append(result)

                await asyncio.sleep(self.settings.delay_between_requests_seconds)

        logger.info(
            "Travelpayouts: encontrados %d precios para %s → %s",
            len(results), route.origin, route.destination,
        )
        return results
