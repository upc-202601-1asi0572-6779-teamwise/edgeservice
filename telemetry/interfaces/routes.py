"""
telemetry/interfaces/routes.py

Blueprint Flask para el endpoint de telemetría.

Expone:
  POST /api/v1/telemetry
    Headers: X-Device-Id  — identificador del dispositivo
             X-Api-Key    — clave de autenticación del dispositivo
    Body:    { "readings": [ { "variable", "value", "unit", "timestamp" } ] }
    201:     { "id": <int>, "alert_flags": { "variable": <bool> } }
    400:     { "error": "<mensaje>" }
    401:     { "error": "Unauthorized" }
    500:     { "error": "<mensaje>" }

La autenticación se realiza en cada request validando el par
(X-Device-Id, X-Api-Key) contra el repositorio local de dispositivos.
"""

import logging

from flask import Blueprint, jsonify, request

from iam.application.services import AuthApplicationService
from iam.infrastructure.repositories import DeviceRepository
from telemetry.application.services import TelemetryApplicationService
from telemetry.infrastructure.repositories import (
    AgronomicThresholdRepository,
    TelemetryRepository,
)

logger = logging.getLogger(__name__)

telemetry_api = Blueprint("telemetry_api", __name__)

# ---------------------------------------------------------------------------
# Instancias de servicios (stateless — seguro compartir entre requests)
# ---------------------------------------------------------------------------
_auth_service = AuthApplicationService(DeviceRepository())
_telemetry_service = TelemetryApplicationService(
    telemetry_repository=TelemetryRepository(),
    threshold_repository=AgronomicThresholdRepository(),
)


@telemetry_api.post("/api/v1/telemetry")
def post_telemetry():
    """
    Recibe un lote de lecturas de sensores desde un dispositivo IoT.

    Autentica el dispositivo con los headers X-Device-Id y X-Api-Key,
    persiste las lecturas localmente, evalúa alertas agronómicas y
    reenvía el lote al Web Service central.

    Returns:
        201: Lote registrado con éxito.
             { "id": <record_id>, "alert_flags": { "variable": <bool> } }
        400: Body inválido o lecturas malformadas.
        401: Credenciales ausentes o incorrectas.
        500: Error interno del servidor.
    """
    device_id = request.headers.get("X-Device-Id", "").strip()
    api_key = request.headers.get("X-Api-Key", "").strip()

    if not device_id or not api_key:
        return jsonify({"error": "Unauthorized"}), 401

    if not _auth_service.authenticate(device_id, api_key):
        logger.warning("Autenticación fallida en endpoint: device_id='%s'.", device_id)
        return jsonify({"error": "Unauthorized"}), 401

    body = request.get_json(silent=True)
    if body is None:
        return jsonify({"error": "El body debe ser JSON válido."}), 400

    readings_data = body.get("readings")
    if not isinstance(readings_data, list) or len(readings_data) == 0:
        return jsonify({"error": "El campo 'readings' debe ser una lista no vacía."}), 400

    try:
        record_id, alert_flags = _telemetry_service.record_telemetry(
            device_id=device_id,
            readings_data=readings_data,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Error interno al registrar telemetría: %s", exc)
        return jsonify({"error": "Error interno del servidor."}), 500

    return jsonify({"id": record_id, "alert_flags": alert_flags}), 201
