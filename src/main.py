"""Entry point for the flight price alert bot.

Punto de entrada principal. Carga la configuración, variables de entorno,
y ejecuta el engine principal.

Uso:
    python -m src.main              # Modo normal (envía a Telegram)
    python -m src.main --dry-run    # Modo prueba (imprime en consola)
"""

import argparse
import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

from src.config import load_config
from src.engine import run

# Configurar logging con formato legible
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def main(dry_run: bool = False) -> None:
    """Main execution flow.

    Flujo:
    1. Cargar configuración de rutas
    2. Obtener credenciales de Telegram (si no es dry-run)
    3. Ejecutar el engine
    """
    logger.info("🛫 Flight Price Alert Bot iniciando...")
    logger.info("Modo: %s", "DRY RUN (sin Telegram)" if dry_run else "PRODUCCIÓN")

    # === Cargar configuración ===
    try:
        routes, settings = load_config()
    except (FileNotFoundError, ValueError) as e:
        logger.error("Error de configuración: %s", e)
        sys.exit(1)

    logger.info(
        "Configuración: %d rutas, tipo de cambio USD/ARS: %.0f",
        len(routes), settings.manual_usd_to_ars,
    )

    # === Obtener credenciales de Telegram ===
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not dry_run and (not telegram_token or not telegram_chat_id):
        logger.error(
            "TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID son requeridos en modo producción. "
            "Configurá el archivo .env o las variables de entorno. "
            "Usá --dry-run para probar sin Telegram."
        )
        sys.exit(1)

    # === Ejecutar el engine ===
    try:
        await run(
            routes=routes,
            settings=settings,
            telegram_token=telegram_token,
            telegram_chat_id=telegram_chat_id,
            dry_run=dry_run,
        )
    except Exception as e:
        logger.error("Error fatal en el engine: %s", e, exc_info=True)
        sys.exit(1)

    logger.info("✅ Flight Price Alert Bot finalizado.")


if __name__ == "__main__":
    # Cargar .env para ejecución local (en GitHub Actions se usan secrets)
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Flight Price Alert Bot — Busca precios de vuelos y alerta via Telegram",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Modo prueba: imprime alertas en consola sin enviar a Telegram",
    )
    args = parser.parse_args()

    # DRY_RUN puede venir del CLI o de la variable de entorno
    is_dry_run = args.dry_run or os.getenv("DRY_RUN", "false").lower() == "true"

    asyncio.run(main(dry_run=is_dry_run))
