"""
telemetry/infrastructure/cloud_client.py

Cliente HTTP hacia el Web Service central (SmartPalmPlatform.API).

CloudApiClient encapsula toda la comunicación saliente del Edge API
con la nube. Falla silenciosamente: si el cloud no está disponible,
los métodos retornan valores seguros en lugar de propagar excepciones,
permitiendo que el Edge API opere en modo offline.

Endpoints del Web Service utilizados:
  GET  /api/v1/device/edge/{edgeMac}/iot/{iotMac}/threshold
         — Obtiene el umbral agronómico configurado para el par edge/iot.
         — Respuesta: { "edgeMac", "iotMac", "min", "max", "description", "type" }
  POST /api/v1/device/edge/{edgeMac}/digest
         — Envía el lote de lecturas en formato ReadDeviceSensorsDataResource.
         — Respuesta: 200 OK (sin cuerpo).

Payload esperado por el endpoint /digest:
  {
      "readings": [
          {"sensorType": "Temperature",  "measuredAt": "...", "value": 25.5},
          {"sensorType": "Humidity",     "measuredAt": "...", "value": 65.0},
          {"sensorType": "SoilMoisture", "measuredAt": "...", "value": 45.0},
          {"sensorType": "Luminosity",   "measuredAt": "...", "value": 78.0}
      ],
      "measuredAt": "..."
  }

Configuración (variables de entorno):
  CLOUD_BASE_URL  — URL base del Web Service, sin slash final.
                    Por defecto: http://localhost:5000
  EDGE_MAC        — Dirección MAC de este nodo edge tal como fue registrada
                    en el backend (p.ej. AA:BB:CC:DD:EE:FF).
                    Requerida para construir las rutas de ambos endpoints.
  IOT_MAC         — Dirección MAC del dispositivo IoT asociado, registrada
                    en el backend (p.ej. BB:CC:DD:EE:FF:AA).
                    Requerida únicamente para el endpoint de umbrales.
  CLOUD_API_KEY   — API key opcional para autenticación con el Web Service.
                    Por defecto: vacío (sin autenticación en desarrollo).
  CLOUD_TIMEOUT   — Timeout en segundos para cada request.
                    Por defecto: 5
"""

import logging
import os
from typing import Optional

import requests

from telemetry.domain.model import AgronomicThreshold, TelemetryRecord

logger = logging.getLogger(__name__)

_BASE_URL = os.getenv("CLOUD_BASE_URL", "http://localhost:5000")
_EDGE_MAC = os.getenv("EDGE_MAC", "")
_IOT_MAC  = os.getenv("IOT_MAC", "")
_API_KEY  = os.getenv("CLOUD_API_KEY", "")
_TIMEOUT  = int(os.getenv("CLOUD_TIMEOUT", "5"))

# ─── Mapeo bidireccional entre nombres de variable del Edge API ─────────────
# y SensorType del Web Service.
# Edge API usa camelCase (p.ej. "soilMoisture"); backend usa PascalCase
# (p.ej. "SoilMoisture"), con la excepción de "light" → "Luminosity".
# ───────────────────────────────────────────────────────────────────────────
_VARIABLE_TO_SENSOR_TYPE: dict[str, str] = {
    "temperature":  "Temperature",
    "humidity":     "Humidity",
    "soilMoisture": "SoilMoisture",
    "light":        "Luminosity",
}

_SENSOR_TYPE_TO_VARIABLE: dict[str, str] = {
    v: k for k, v in _VARIABLE_TO_SENSOR_TYPE.items()
}


def _to_sensor_type(variable: str) -> str:
    """Convierte el nombre de variable del Edge API al SensorType del backend."""
    return _VARIABLE_TO_SENSOR_TYPE.get(variable, variable)


def _to_variable(sensor_type: str) -> str:
    """Convierte el SensorType del backend al nombre de variable del Edge API."""
    return _SENSOR_TYPE_TO_VARIABLE.get(sensor_type, sensor_type.lower())


class CloudApiClient:
    """
    Cliente HTTP para comunicación con el Web Service central.

    Todos los métodos capturan excepciones de red y retornan valores
    seguros (lista vacía, False) para garantizar que el Edge API nunca
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
        Obtiene el umbral agronómico configurado para el par edge/iot.

        Hace GET a /api/v1/device/edge/{edgeMac}/iot/{iotMac}/threshold.
        Si el cloud no responde o retorna un error, retorna lista vacía
        para que TelemetryDomainService use los valores por defecto.

        El backend identifica los dispositivos por MAC address (EDGE_MAC e
        IOT_MAC), no por el device_id interno del Edge API. El parámetro
        device_id se conserva para compatibilidad con ThresholdSyncService
        pero no se utiliza en la construcción de la URL.

        Args:
            device_id: Identificador interno del dispositivo (no utilizado
                       en la ruta; la identificación en el cloud se realiza
                       mediante las variables de entorno EDGE_MAC e IOT_MAC).

        Returns:
            Lista con un AgronomicThreshold sincronizado desde el cloud,
            o lista vacía si el cloud no está disponible o las variables
            de entorno no están configuradas.
        """
        if not _EDGE_MAC or not _IOT_MAC:
            logger.debug(
                "EDGE_MAC o IOT_MAC no configurados — sincronización de umbrales omitida."
            )
            return []

        url = (
            f"{_BASE_URL}/api/v1/device/edge/{_EDGE_MAC}"
            f"/iot/{_IOT_MAC}/threshold"
        )
        try:
            response = requests.get(
                url,
                headers=CloudApiClient._headers(),
                timeout=_TIMEOUT,
            )
            response.raise_for_status()

            data = response.json()

            # El backend devuelve un objeto único AgronomicThresholdViewResource:
            # { "edgeMac", "iotMac", "min", "max", "description", "type" }
            # Normalizar a lista para procesar uniformemente.
            if isinstance(data, dict):
                data = [data]

            if not isinstance(data, list) or len(data) == 0:
                logger.info("Sin umbrales configurados en el cloud para este par edge/iot.")
                return []

            thresholds = []
            for item in data:
                threshold = AgronomicThreshold(
                    variable=_to_variable(item.get("type", "")),
                    min_value=float(item.get("min", 0.0)),
                    max_value=float(item.get("max", 100.0)),
                )
                logger.info(
                    "Umbral obtenido del cloud: variable='%s' [%.1f, %.1f].",
                    threshold.variable,
                    threshold.min_value,
                    threshold.max_value,
                )
                thresholds.append(threshold)
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
    def post_telemetry_batch(record: TelemetryRecord) -> bool:
        """
        Reenvía un lote de lecturas al Web Service central.

        Hace POST a /api/v1/device/edge/{edgeMac}/digest con el payload
        en formato ReadDeviceSensorsDataResource esperado por el backend.
        Si el cloud no responde, retorna False sin interrumpir el flujo
        principal del Edge API (el lote ya fue persistido localmente).

        Los nombres de variable del Edge API (p.ej. "soilMoisture") se
        convierten automáticamente al SensorType del backend (p.ej.
        "SoilMoisture") mediante el mapeo _VARIABLE_TO_SENSOR_TYPE.

        Args:
            record: TelemetryRecord con las lecturas a reenviar.

        Returns:
            True si el cloud respondió con HTTP 200 o 201, False si falló.
        """
        if not _EDGE_MAC:
            logger.debug("EDGE_MAC no configurado — reenvío al cloud omitido.")
            return False

        url = f"{_BASE_URL}/api/v1/device/edge/{_EDGE_MAC}/digest"
        timestamp = record.recorded_at.isoformat()

        payload = {
            "readings": [
                {
                    "sensorType": _to_sensor_type(r.variable),
                    "measuredAt": r.timestamp.isoformat(),
                    "value": r.value,
                }
                for r in record.readings
            ],
            "measuredAt": timestamp,
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers=CloudApiClient._headers(),
                timeout=_TIMEOUT,
            )
            response.raise_for_status()

            logger.info(
                "Lote reenviado al cloud: device_id='%s', edge='%s', lecturas=%d. HTTP %d.",
                record.device_id,
                _EDGE_MAC,
                len(record.readings),
                response.status_code,
            )
            return True

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

        return False
