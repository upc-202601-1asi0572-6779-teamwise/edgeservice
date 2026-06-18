"""
telemetry/infrastructure/repositories.py

Implementaciones SQLite de los repositorios del bounded context Telemetry.

TelemetryRepository — persiste TelemetryRecord y sus SensorReadingValue
                      en una transacción atómica.
"""

import logging

from telemetry.domain.model import TelemetryRecord
from telemetry.domain.services import ITelemetryRepository
from telemetry.infrastructure.database import SensorReadingModel, TelemetryRecordModel
from shared.infrastructure.database import db

logger = logging.getLogger(__name__)


class TelemetryRepository(ITelemetryRepository):
    """
    Implementación de ITelemetryRepository sobre SQLite via Peewee.

    Inserta el encabezado del lote (TelemetryRecordModel) y cada lectura
    individual (SensorReadingModel) dentro de una misma transacción atómica.
    Si cualquier inserción falla, toda la operación se revierte.
    """

    @staticmethod
    def save(record: TelemetryRecord) -> int:
        """
        Persiste un TelemetryRecord completo en la base de datos.

        Crea primero el registro de encabezado y luego inserta cada
        SensorReadingValue asociado en bulk para minimizar round-trips.

        Args:
            record: Aggregate root con las lecturas del dispositivo.

        Returns:
            ID entero del TelemetryRecordModel creado.

        Raises:
            Exception: Propaga cualquier error de base de datos tras revertir
                       la transacción.
        """
        with db.atomic():
            telemetry_model = TelemetryRecordModel.create(
                device_id=record.device_id,
                recorded_at=record.recorded_at,
            )

            reading_rows = [
                {
                    "record": telemetry_model.id,
                    "variable": reading.variable,
                    "value": reading.value,
                    "unit": reading.unit,
                    "timestamp": reading.timestamp,
                }
                for reading in record.readings
            ]

            if reading_rows:
                SensorReadingModel.insert_many(reading_rows).execute()

            logger.debug(
                "TelemetryRecord id=%d guardado: device_id='%s', %d lecturas.",
                telemetry_model.id,
                record.device_id,
                len(reading_rows),
            )

        return telemetry_model.id
