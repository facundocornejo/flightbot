"""Abstract base class for all flight price adapters.

Todos los adapters heredan de BaseAdapter y deben implementar fetch_prices().
Esto garantiza una interfaz consistente para el engine.
"""

from abc import ABC, abstractmethod

from src.models import AppSettings, PriceResult, RouteConfig


class BaseAdapter(ABC):
    """Base class for flight price source adapters."""

    def __init__(self, settings: AppSettings) -> None:
        """Initialize with global app settings.

        Recibe los settings globales (delay, user-agent, etc.)
        para que cada adapter pueda usarlos en sus requests.
        """
        self.settings = settings

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unique identifier for this data source (e.g., 'level', 'sky')."""
        ...

    @abstractmethod
    async def fetch_prices(self, route: RouteConfig) -> list[PriceResult]:
        """Fetch prices for a given route.

        Consulta precios para la ruta dada y devuelve una lista de PriceResult.
        Si hay un error, debe loggearlo y devolver lista vacía (nunca crashear).
        """
        ...
