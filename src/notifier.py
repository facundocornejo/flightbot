"""Telegram notification sender.

Envía alertas de precio al chat de Telegram configurado.
Usa la API HTTP de Telegram directamente (sin librerías externas)
para mantener las dependencias al mínimo.
"""

import logging

import httpx

from src.models import PriceResult

logger = logging.getLogger(__name__)

# URL base de la API de Telegram
TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


async def send_alert(
    token: str,
    chat_id: str,
    result: PriceResult,
    is_price_drop: bool = False,
) -> bool:
    """Send a price alert via Telegram.

    Envía un mensaje formateado con los detalles del vuelo barato.
    Usa MarkdownV2 para formato bonito en Telegram.

    Args:
        token: Token del bot de Telegram (de @BotFather).
        chat_id: ID del chat donde enviar el mensaje.
        result: El PriceResult que disparó la alerta.
        is_price_drop: Si es True, indica que el precio bajó aún más.

    Returns:
        True si se envió correctamente, False si hubo error.
    """
    message = _format_message(result, is_price_drop)

    url = TELEGRAM_API_URL.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()

        logger.info("Alerta enviada a Telegram: %s", result.route_key)
        return True

    except httpx.HTTPStatusError as e:
        logger.error(
            "Error HTTP al enviar a Telegram (%d): %s",
            e.response.status_code, e.response.text,
        )
        return False
    except Exception as e:
        logger.error("Error al enviar a Telegram: %s", e)
        return False


async def send_error_alert(token: str, chat_id: str, message: str) -> bool:
    """Send an error/warning message via Telegram.

    Para enviar alertas de errores críticos (ej: API key expirada de Sky).
    """
    url = TELEGRAM_API_URL.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": f"⚠️ <b>Flight Bot — Error</b>\n\n{_escape_html(message)}",
        "parse_mode": "HTML",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
        return True
    except Exception as e:
        logger.error("Error al enviar alerta de error a Telegram: %s", e)
        return False


def print_alert(result: PriceResult, is_price_drop: bool = False) -> None:
    """Print alert to console (dry-run mode).

    Imprime en consola en vez de enviar a Telegram. Útil para testing local.
    """
    message = _format_message(result, is_price_drop)
    # Limpiar tags HTML para consola
    clean = message.replace("<b>", "").replace("</b>", "")
    clean = clean.replace("<i>", "").replace("</i>", "")
    # Manejar emojis en Windows (cp1252 no los soporta)
    try:
        print(f"\n{'='*50}")
        print("[DRY RUN] Alerta que se enviaría:")
        print(clean)
        print(f"{'='*50}\n")
    except UnicodeEncodeError:
        # Reemplazar emojis con equivalentes de texto para Windows
        clean = clean.encode("ascii", errors="ignore").decode("ascii")
        print(f"\n{'='*50}")
        print("[DRY RUN] Alerta que se enviaria:")
        print(clean)
        print(f"{'='*50}\n")


def _format_message(result: PriceResult, is_price_drop: bool = False) -> str:
    """Format a PriceResult into a Telegram message.

    Crea un mensaje bonito con emojis y formato HTML para Telegram.
    """
    # Emoji según si es primera alerta o bajada de precio
    header_emoji = "📉" if is_price_drop else "🔥"
    header_text = "BAJÓ MÁS" if is_price_drop else "ALERTA DE PRECIO"

    lines = [
        f"{header_emoji} <b>{header_text} — {result.origin} → {result.destination}</b>",
        "",
        f"💰 <b>{result.display_price}</b> ({result.airline})",
        f"📅 {result.date}",
    ]

    # Escalas
    stops_text = "Directo" if result.stops == 0 else f"{result.stops} escala(s)"
    lines.append(f"✈️ {stops_text}")

    # Número de vuelo (si está disponible)
    if result.flight_number:
        lines.append(f"🔢 Vuelo: {result.flight_number}")

    # Asientos restantes (solo Sky)
    if result.seats_remaining is not None:
        urgency = "⚡" if result.seats_remaining <= 3 else "🪑"
        lines.append(f"{urgency} {result.seats_remaining} asientos restantes")

    # Duración (si está disponible)
    if result.duration_minutes:
        hours = result.duration_minutes // 60
        minutes = result.duration_minutes % 60
        lines.append(f"⏱️ {hours}h {minutes}m")

    # Tags especiales de Level
    if "IsMinimumPriceMonth" in result.tags:
        lines.append("🏷️ <i>Precio más bajo del mes</i>")

    lines.extend([
        "",
        f"📊 Fuente: {result.source}",
        f"⏰ {result.fetched_at[:19]} UTC",
    ])

    return "\n".join(lines)


def _escape_html(text: str) -> str:
    """Escape special HTML characters for Telegram.

    Telegram usa un subset de HTML; hay que escapar <, >, y &.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
