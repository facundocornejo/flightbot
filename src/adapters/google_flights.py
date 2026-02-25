"""Google Flights price adapter via fast-flights library.

Usa la librería fast-flights para scrapear Google Flights. Cubre TODAS
las aerolíneas en cualquier ruta. Funciona decodificando parámetros
Protobuf de las URLs de Google Flights.

Install: pip install fast-flights
Docs: https://github.com/AWeirdDev/flights
"""

import asyncio
import logging
import re
from datetime import date, timedelta

from src.adapters.base import BaseAdapter
from src.models import AppSettings, PriceResult, RouteConfig

logger = logging.getLogger(__name__)

# Escanear 1 fecha por semana para no hacer demasiados requests
DAYS_BETWEEN_SCANS = 7

# Modo de fetch: "common" es el más rápido y funciona en GitHub Actions
# Si falla consistentemente, cambiar a "fallback" (usa Playwright serverless)
FETCH_MODE = "common"


def _parse_price(price_str: str | None) -> float | None:
    """Parse price string from fast-flights to float.

    fast-flights devuelve precios como strings tipo "$1,234", "ARS 500,000",
    "€ 450", etc. Este parser extrae el número.

    Ejemplos:
        "$1,234" → 1234.0
        "ARS 500,000" → 500000.0
        "€450" → 450.0
        None → None
    """
    if not price_str:
        return None

    # Remover todo excepto dígitos, puntos y comas
    cleaned = re.sub(r"[^\d.,]", "", str(price_str))

    if not cleaned:
        return None

    # Manejar formato con coma como separador de miles (1,234 o 500,000)
    # y punto como separador decimal (1,234.56)
    if "," in cleaned and "." in cleaned:
        # Tiene ambos: 1,234.56 → quitar comas
        cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # Solo comas: podría ser 1,234 (miles) o 1,50 (decimal europeo)
        parts = cleaned.split(",")
        if len(parts[-1]) == 3:
            # Separador de miles: 1,234 o 500,000
            cleaned = cleaned.replace(",", "")
        else:
            # Separador decimal europeo: 1,50
            cleaned = cleaned.replace(",", ".")

    try:
        return float(cleaned)
    except ValueError:
        logger.warning("No se pudo parsear precio: '%s' → '%s'", price_str, cleaned)
        return None


def _parse_stops(stops_str: str | int | None) -> int:
    """Parse stops from fast-flights to int.

    fast-flights puede devolver "Nonstop", "1 stop", "2 stops", o un int.
    """
    if stops_str is None:
        return 0
    if isinstance(stops_str, int):
        return stops_str

    stops_lower = str(stops_str).lower()
    if "nonstop" in stops_lower or "direct" in stops_lower:
        return 0

    # Buscar número en el string
    match = re.search(r"(\d+)", str(stops_str))
    return int(match.group(1)) if match else 0


def _detect_currency(price_str: str | None) -> str:
    """Detect currency from price string.

    Intenta detectar la moneda del precio según el símbolo o prefijo.
    Por defecto asume USD para rutas internacionales desde Argentina.
    """
    if not price_str:
        return "USD"

    price_upper = str(price_str).upper()
    if "ARS" in price_upper or "AR$" in price_upper:
        return "ARS"
    if "€" in price_upper or "EUR" in price_upper:
        return "EUR"
    # USD es el default para Google Flights en rutas internacionales
    return "USD"


class GoogleFlightsAdapter(BaseAdapter):
    """Adapter for Google Flights via fast-flights library."""

    def __init__(self, settings: AppSettings) -> None:
        super().__init__(settings)
        self._available = True  # Se pone en False si fast-flights no está instalado

    @property
    def source_name(self) -> str:
        return "google_flights"

    async def fetch_prices(self, route: RouteConfig) -> list[PriceResult]:
        """Fetch prices from Google Flights for specific dates.

        Escanea fechas durante months_ahead meses. Para round-trip, usa la
        duración configurada en settings (trip_duration_min/max_days).
        """
        # Intentar importar fast_flights (puede no estar instalado)
        try:
            from fast_flights import FlightData, Passengers, get_flights
        except ImportError:
            if self._available:
                logger.error(
                    "fast-flights no está instalado. "
                    "Ejecutá: pip install fast-flights"
                )
                self._available = False
            return []

        results: list[PriceResult] = []
        today = date.today()
        total_days = route.months_ahead * 30

        # Generar fechas a escanear (cada 3 días para marzo, más denso)
        dates_to_scan: list[date] = []
        current = today + timedelta(days=1)  # Empezar desde mañana
        while (current - today).days <= total_days:
            dates_to_scan.append(current)
            current += timedelta(days=3)  # Cada 3 días para mejor cobertura

        # Determinar tipo de viaje y duración
        is_round_trip = route.trip_type == "round_trip"
        trip = "round-trip" if is_round_trip else "one-way"

        # Usar duración promedio para round-trip
        return_days = (self.settings.trip_duration_min_days + self.settings.trip_duration_max_days) // 2

        logger.info(
            "Google Flights: escaneando %s → %s (%d fechas%s)",
            route.origin, route.destination,
            len(dates_to_scan),
            f", vuelta +{return_days} días" if is_round_trip else "",
        )

        for scan_date in dates_to_scan:
            try:
                # Construir flight_data según tipo de viaje
                if is_round_trip:
                    return_date = scan_date + timedelta(days=return_days)
                    flight_data = [
                        FlightData(
                            date=scan_date.isoformat(),
                            from_airport=route.origin,
                            to_airport=route.destination,
                        ),
                        FlightData(
                            date=return_date.isoformat(),
                            from_airport=route.destination,
                            to_airport=route.origin,
                        ),
                    ]
                else:
                    flight_data = [
                        FlightData(
                            date=scan_date.isoformat(),
                            from_airport=route.origin,
                            to_airport=route.destination,
                        ),
                    ]

                # fast-flights es sincrónico, lo ejecutamos en un thread
                flight_results = await asyncio.to_thread(
                    get_flights,
                    flight_data=flight_data,
                    trip=trip,
                    seat="economy",
                    passengers=Passengers(adults=1),
                    fetch_mode=FETCH_MODE,
                )

                # Parsear cada vuelo encontrado
                if flight_results and flight_results.flights:
                    for flight in flight_results.flights:
                        price = _parse_price(flight.price)
                        if price is None:
                            continue

                        currency = _detect_currency(flight.price)

                        # Formatear fecha con duración del viaje
                        date_display = scan_date.isoformat()
                        if is_round_trip:
                            return_date = scan_date + timedelta(days=return_days)
                            date_display = f"{scan_date.isoformat()} → {return_date.isoformat()}"

                        results.append(
                            PriceResult(
                                source=self.source_name,
                                airline=str(flight.name) if flight.name else "Unknown",
                                origin=route.origin,
                                destination=route.destination,
                                date=date_display,
                                price=price,
                                currency=currency,
                                stops=_parse_stops(flight.stops),
                            )
                        )

            except Exception as e:
                # fast-flights puede fallar por muchas razones (rate limit, cambios en Google, etc.)
                logger.warning(
                    "Google Flights: error al consultar %s→%s fecha %s: %s",
                    route.origin, route.destination, scan_date, e,
                )

            # Delay entre requests para evitar rate limiting de Google
            await asyncio.sleep(self.settings.delay_between_requests_seconds)

        logger.info(
            "Google Flights: encontrados %d precios para %s → %s",
            len(results), route.origin, route.destination,
        )
        return results
