"""Alert state manager — prevents duplicate Telegram notifications.

Guarda un registro de las alertas ya enviadas en un archivo JSON.
Antes de enviar una alerta nueva, verifica si ya se envió una similar
dentro del período de cooldown configurado.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.models import AlertRecord, PriceResult

logger = logging.getLogger(__name__)

# Ruta al archivo de estado (relativa a la raíz del proyecto)
STATE_FILE = Path(__file__).parent.parent / "data" / "alert_state.json"


class AlertStateManager:
    """Manages alert history to avoid sending duplicate notifications."""

    def __init__(self, cooldown_hours: int = 48, state_path: Path | None = None) -> None:
        """Initialize the state manager.

        Args:
            cooldown_hours: Horas de cooldown antes de re-alertar la misma ruta+fecha.
            state_path: Ruta al archivo de estado. Si es None, usa la ruta por defecto.
        """
        self.cooldown_hours = cooldown_hours
        self.state_path = state_path or STATE_FILE
        self._state: dict[str, AlertRecord] = {}
        self._load()

    def _load(self) -> None:
        """Load state from JSON file.

        Carga el estado previo. Si el archivo no existe o está corrupto,
        empieza con estado vacío (primera ejecución o cache perdido).
        """
        if not self.state_path.exists():
            logger.info("Estado de alertas no encontrado, empezando vacío.")
            return

        try:
            with open(self.state_path, encoding="utf-8") as f:
                raw = json.load(f)

            for key, data in raw.items():
                self._state[key] = AlertRecord.from_dict(key, data)

            logger.info("Estado de alertas cargado: %d registros.", len(self._state))
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Error al cargar estado de alertas: %s. Empezando vacío.", e)
            self._state = {}

    def save(self) -> None:
        """Save current state to JSON file.

        Guarda el estado actual en disco. Crea el directorio si no existe.
        También limpia registros expirados antes de guardar.
        """
        self._cleanup_expired()

        # Crear directorio si no existe
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

        data = {key: record.to_dict() for key, record in self._state.items()}

        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info("Estado de alertas guardado: %d registros.", len(self._state))

    def should_alert(self, result: PriceResult) -> bool:
        """Check if we should send an alert for this price result.

        Reglas:
        1. Si nunca alertamos esta ruta+fecha → alertar
        2. Si el precio BAJÓ desde la última alerta → alertar ("bajó más!")
        3. Si pasó el cooldown desde la última alerta → alertar (refresh)
        4. Si el precio es igual o mayor y no pasó el cooldown → NO alertar
        """
        key = result.route_key
        existing = self._state.get(key)

        if existing is None:
            # Nunca alertamos esta ruta+fecha → alertar
            return True

        # Verificar si el precio bajó desde la última alerta
        if result.price < existing.price:
            logger.info(
                "Precio bajó para %s: %s %.0f → %.0f %s",
                key, existing.currency, existing.price, result.price, result.currency,
            )
            return True

        # Verificar si pasó el cooldown
        try:
            last_alert_time = datetime.fromisoformat(existing.alerted_at)
            cooldown_delta = timedelta(hours=self.cooldown_hours)
            now = datetime.now(timezone.utc)

            if now - last_alert_time > cooldown_delta:
                return True
        except (ValueError, TypeError):
            # Si no podemos parsear la fecha, alertar por las dudas
            return True

        return False

    def record_alert(self, result: PriceResult) -> None:
        """Record that an alert was sent for this price result.

        Guarda el registro en memoria. Llamar a save() después para persistir.
        """
        self._state[result.route_key] = AlertRecord(
            route_key=result.route_key,
            price=result.price,
            currency=result.currency,
            alerted_at=datetime.now(timezone.utc).isoformat(),
        )

    def _cleanup_expired(self) -> None:
        """Remove alert records older than 7 days.

        Limpia registros viejos para que el archivo de estado no crezca
        indefinidamente. Los registros de más de 7 días ya no son relevantes.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        expired_keys = []

        for key, record in self._state.items():
            try:
                alert_time = datetime.fromisoformat(record.alerted_at)
                if alert_time < cutoff:
                    expired_keys.append(key)
            except (ValueError, TypeError):
                expired_keys.append(key)

        for key in expired_keys:
            del self._state[key]

        if expired_keys:
            logger.info("Limpiados %d registros de alerta expirados.", len(expired_keys))
