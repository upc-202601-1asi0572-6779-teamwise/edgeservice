"""
telemetry/infrastructure/cloud_client.py

Cliente HTTP hacia el Web Service central (SmartPalmPlatform.API).

CloudApiClient encapsula toda la comunicación saliente del Edge API
con la nube. Falla silenciosamente: si el cloud no está disponible,
los métodos retornan valores vacíos en lugar de propagar excepciones,
permitiendo que el Edge API opere en modo offline.

Endpoints esperados en el Web Service (Sprint 3):
  GET  /api/v1/agronomic-thresholds          — obtiene umbrales por device
  POST /api/v1/telemetry/batch               — reenvía lote de lecturas

Configuración:
  CLOUD_BASE_URL  — URL base del Web Service (sin slash final)
                    Por defecto: http://localhost:5000
  CLOUD_API_KEY   — API key para autenticación con el Web Service
                    Por defecto: vacío (sin autenticación en desarrollo)
  CLOUD_TIMEOUT   — Timeout en segundos para cada request
                    Por defecto: 5
"""

import logging
import os
from typing import Optional

import requests

from telemetry.domain.model import AgronomicThreshold, TelemetryRecord

logger = logging.getLogger(__name__)

_BASE_URL = os.getenv("CLOUD_BASE_URL", "http://localhost:5000")
_API_KEY = os.getenv("CLOUD_API_KEY", "")
_TIMEOUT = int(os.getenv("CLOUD_TIMEOUT", "5"))


class CloudApiClient:
    """
    Cliente HTTP para comunicación con el Web Service central.

    Todos los métodos capturan excepciones de red y retornan valores
    seguros (lista vacía, None) para garantizar que el Edge API nunca
    falle por indisponibilidad del cloud.
    """

    @staticmethod
    def _headers() -> dict:
        """Construye los headers HTTP comunes para todas las peticiones."""
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if _API_KEY:
            headers["X-Api-Key"] = _API_KEY
        return headers

    @staticmethod
    def get_thresholds(device_id: str) -> list[AgronomicThreshold]:
        """
        Obtiene los umbrales agronómicos configurados para un dispositivo.

        Hace GET a /api/v1/agronomic-thresholds?deviceId=<device_id>.
        Si el cloud no responde o retorna un error, retorna lista vacía
        para que TelemetryDomainService use los valores por defecto.

        Args:
            device_id: Identificador del dispositivo para filtrar umbrales.

        Returns:
            Lista de AgronomicThreshold sincronizados. Lista vacía si el
            cloud no está disponible o retorna error.
        """
        url = f"{_BASE_URL}/api/v1/agronomic-thresholds"
        try:
            response = requests.get(
                url,
                params={"deviceId": device_id},
                headers=CloudApiClient._headers(),
                timeout=_TIMEOUT,
            )
            response.raise_for_status()

            data = response.json()
            thresholds = [
                AgronomicThreshold(
                    variable=item["variable"],
                    min_value=float(item["minValue"]),
                    max_value=float(item["maxValue"]),
                )
                for item in data
                if "variable" in item and "minValue" in item and "maxValue" in item
            ]

            logger.info(
                "Umbrales obtenidos del cloud: %d registros para device_id='%s'.",
                len(thresholds),
                device_id,
            )
            return thresholds

        except requests.exceptions.ConnectionError:
            logger.warning(
                "Cloud no disponible al obtener umbrales (ConnectionError). "
                "Se usarán umbrales por defecto."
            )
        except requests.exceptions.Timeout:
            logger.warning(
                "Timeout al obtener umbrales del cloud (>%ds). "
                "Se usarán umbrales por defecto.",
                _TIMEOUT,
            )
        except requests.exceptions.HTTPError as exc:
            logger.warning(
                "Error HTTP %s al obtener umbrales del cloud: %s.",
                exc.response.status_code,
                exc,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error inesperado al obtener umbrales del cloud: %s.", exc)

        return []

    @staticmethod
    def post_telemetry_batch(record: TelemetryRecord) -> Optional[int]:
        """
        Reenvía un lote de lecturas al Web Service central.

        Hace POST a /api/v1/telemetry/batch con el lote serializado.
        Si el cloud no responde, retorna None sin interrumpir el flujo
        principal del Edge API (el lote ya fue persistido localmente).

        Args:
            record: TelemetryRecord con las lecturas a reenviar.

        Returns:
            ID del registro creado en el cloud si fue exitoso, None si falló.
        """
        url = f"{_BASE_URL}/api/v1/telemetry/batch"
        payload = {
            "deviceId": record.device_id,
            "recordedAt": record.recorded_at.isoformat(),
            "readings": [
                {
                    "variable": r.variable,
                    "value": r.value,
                    "unit": r.unit,
                    "timestamp": r.timestamp.isoformat(),
                }
                for r in record.readings
            ],
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers=CloudApiClient._headers(),
                timeout=_TIMEOUT,
            )
            response.raise_for_status()

            cloud_id: Optional[int] = response.json().get("id")
            logger.info(
                "Lote reenviado al cloud: device_id='%s', cloud_id=%s.",
                record.device_id,
                cloud_id,
            )
            return cloud_id

        except requests.exceptions.ConnectionError:
            logger.warning(
                "Cloud no disponible al reenviar lote (ConnectionError). "
                "El lote quedó persistido localmente."
            )
        except requests.exceptions.Timeout:
            logger.warning(
                "Timeout al reenviar lote al cloud (>%ds). "
                "El lote quedó persistido localmente.",
                _TIMEOUT,
            )
        except requests.exceptions.HTTPError as exc:
            logger.warning(
                "Error HTTP %s al reenviar lote al cloud: %s.",
                exc.response.status_code,
                exc,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error inesperado al reenviar lote al cloud: %s.", exc)

        return None
