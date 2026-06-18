"""
app.py — Smart Palm Edge Service

Entrypoint del Edge API. Crea la aplicación Flask, registra los Blueprints
y ejecuta el bootstrap en el primer request entrante.

Bootstrap (before_request, ejecutado una sola vez):
  1. Inicializa la base de datos SQLite y crea las tablas si no existen.
  2. Siembra el dispositivo de prueba (smart-palm-001) si no está registrado.
  3. Sincroniza umbrales agronómicos desde el Web Service central.

Variables de entorno:
  DATABASE_PATH   — Ruta al archivo SQLite (default: edge_data.db)
  CLOUD_BASE_URL  — URL base del Web Service (default: http://localhost:5000)
  CLOUD_API_KEY   — API key para el Web Service (default: vacío)
  CLOUD_TIMEOUT   — Timeout HTTP en segundos (default: 5)
"""

import logging
import os

from flask import Flask

from iam.application.services import AuthApplicationService
from iam.infrastructure.database import DeviceModel
from iam.infrastructure.repositories import DeviceRepository
from iam.interfaces.routes import iam_api
from shared.infrastructure.database import init_db
from telemetry.application.threshold_sync import ThresholdSyncService
from telemetry.infrastructure.database import (
    AgronomicThresholdModel,
    SensorReadingModel,
    TelemetryRecordModel,
)
from telemetry.infrastructure.repositories import AgronomicThresholdRepository
from telemetry.interfaces.routes import telemetry_api

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
_DATABASE_PATH = os.getenv("DATABASE_PATH", "edge_data.db")
_TEST_DEVICE_ID = "smart-palm-001"

# ---------------------------------------------------------------------------
# Modelos que init_db debe registrar (orden respeta FKs)
# ---------------------------------------------------------------------------
_DB_MODELS = [
    DeviceModel,
    TelemetryRecordModel,
    SensorReadingModel,
    AgronomicThresholdModel,
]

# ---------------------------------------------------------------------------
# Servicios de bootstrap (instanciados una vez)
# ---------------------------------------------------------------------------
_auth_service = AuthApplicationService(DeviceRepository())
_sync_service = ThresholdSyncService(AgronomicThresholdRepository())


def create_app() -> Flask:
    """
    Factoría de la aplicación Flask.

    Registra Blueprints y configura el hook before_request para bootstrap.

    Returns:
        Instancia de Flask lista para ejecutar.
    """
    app = Flask(__name__)

    # Registrar blueprints
    app.register_blueprint(iam_api)
    app.register_blueprint(telemetry_api)

    # Flag de bootstrap: se ejecuta solo en el primer request
    _bootstrapped: dict = {"done": False}

    @app.before_request
    def bootstrap():
        if _bootstrapped["done"]:
            return

        logger.info("Iniciando bootstrap del Edge API...")

        # 1. Inicializar base de datos
        init_db(_DATABASE_PATH, _DB_MODELS)

        # 2. Sembrar dispositivo de prueba
        _auth_service.seed_test_device()

        # 3. Sincronizar umbrales desde el cloud
        synced = _sync_service.sync(_TEST_DEVICE_ID)
        if synced == 0:
            logger.info(
                "Sin umbrales del cloud — se usarán valores agronómicos por defecto."
            )

        _bootstrapped["done"] = True
        logger.info("Bootstrap completado.")

    return app


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
