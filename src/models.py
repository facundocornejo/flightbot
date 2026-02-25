"""Shared data models for the flight price alert bot."""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class PriceResult:
    """Standardized flight price result, source-agnostic.

    Resultado estandarizado de precio de vuelo. Todos los adapters devuelven
    objetos de este tipo, sin importar de qué fuente vienen.
    """

    source: str  # "level", "sky", "google_flights"
    airline: str  # "Level", "Sky Airline", "LATAM", etc.
    origin: str  # Código IATA del aeropuerto de origen
    destination: str  # Código IATA del destino
    date: str  # Fecha del vuelo YYYY-MM-DD
    price: float  # Precio del vuelo
    currency: str  # "USD" o "ARS"
    stops: int = 0  # Cantidad de escalas
    flight_number: str = ""  # Número de vuelo (opcional)
    seats_remaining: int | None = None  # Asientos disponibles (solo Sky)
    duration_minutes: int | None = None  # Duración total en minutos
    tags: list[str] = field(default_factory=list)  # Tags extra ("IsMinimumPriceMonth", etc.)
    fetched_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def route_key(self) -> str:
        """Unique key for this route+date combo. Usado para deduplicación de alertas."""
        return f"{self.origin}-{self.destination}-{self.date}"

    @property
    def display_price(self) -> str:
        """Formatted price string for display. Ej: 'USD 511' o 'ARS 401,363'."""
        if self.currency == "USD":
            return f"USD {self.price:,.0f}"
        return f"ARS {self.price:,.0f}"


@dataclass
class RouteConfig:
    """Configuration for a route to monitor.

    Cada ruta define: origen/destino, qué fuentes usar, umbrales de precio,
    y cuántos meses hacia adelante escanear.
    """

    origin: str
    destination: str
    sources: list[str]  # ["level", "sky", "google_flights"]
    threshold_usd: float | None = None
    threshold_ars: float | None = None
    months_ahead: int = 6  # Cuántos meses hacia adelante escanear
    trip_type: str = "round_trip"  # "round_trip" o "one_way"


@dataclass
class AlertRecord:
    """Record of a previously sent alert, used to prevent duplicates.

    Registro de una alerta ya enviada. Se guarda en alert_state.json
    para no mandar la misma alerta varias veces.
    """

    route_key: str  # "EZE-BCN-2026-12-01"
    price: float  # Precio que se alertó
    currency: str  # Moneda del precio
    alerted_at: str  # ISO timestamp de cuándo se envió

    @staticmethod
    def from_dict(key: str, data: dict) -> "AlertRecord":
        """Create AlertRecord from a dict (loaded from JSON state file)."""
        return AlertRecord(
            route_key=key,
            price=data["price"],
            currency=data["currency"],
            alerted_at=data["alerted_at"],
        )

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return {
            "price": self.price,
            "currency": self.currency,
            "alerted_at": self.alerted_at,
        }


@dataclass
class AppSettings:
    """Global application settings loaded from config.

    Configuración global de la app: delays, cooldown de alertas,
    tipo de cambio manual, etc.
    """

    delay_between_requests_seconds: int = 3
    alert_cooldown_hours: int = 48
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/145.0.0.0 Safari/537.36"
    )
    # Tipo de cambio manual USD → ARS. Actualizalo cuando quieras.
    # Se usa para convertir precios y poder comparar contra umbrales en la otra moneda.
    manual_usd_to_ars: float = 1200.0
    # Duración del viaje en días (para búsquedas round-trip)
    trip_duration_min_days: int = 7
    trip_duration_max_days: int = 10
