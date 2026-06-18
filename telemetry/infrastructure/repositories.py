"""
telemetry/infrastructure/repositories.py

Implementaciones SQLite de los repositorios del bounded context Telemetry.

TelemetryRepository          — persiste TelemetryRecord y sus SensorReadingValue
                               en una transacción atómica.
AgronomicThresholdRepository — persiste y consulta umbrales agronómicos sincronizados
                               desde la nube.
"""

import logging
from typing import Optional

from telemetry.domain.model import AgronomicThreshold, TelemetryRecord
from telemetry.domain.services import IAgronomicThresholdRepository, ITelemetryRepository
from telemetry.infrastructure.database import (
    AgronomicThresholdModel,
    SensorReadingModel,
    TelemetryRecordModel,
)
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


class AgronomicThresholdRepository(IAgronomicThresholdRepository):
    """
    Implementación de IAgronomicThresholdRepository sobre SQLite via Peewee.

    Almacena los umbrales sincronizados desde la nube. La tabla tiene un
    unique constraint en `variable`, por lo que save() hace upsert: crea
    si no existe o actualiza min_value/max_value si ya hay un registro.
    """

    @staticmethod
    def find_by_variable(variable: str) -> Optional[AgronomicThreshold]:
        """
        Busca el umbral agronómico activo para una variable.

        Args:
            variable: Nombre de la variable (p.ej. "temperature").

        Returns:
            AgronomicThreshold si existe en la tabla, None si no hay
            umbral sincronizado para esa variable.
        """
        try:
            record = AgronomicThresholdModel.get(
                AgronomicThresholdModel.variable == variable
            )
            return AgronomicThreshold(
                variable=record.variable,
                min_value=record.min_value,
                max_value=record.max_value,
            )
        except AgronomicThresholdModel.DoesNotExist:
            return None

    @staticmethod
    def save(threshold: AgronomicThreshold) -> None:
        """
        Persiste o actualiza un umbral agronómico (upsert por variable).

        Si ya existe un registro para la variable, actualiza min_value y
        max_value. Si no existe, lo crea.

        Args:
            threshold: Entidad AgronomicThreshold a guardar.
        """
        record, created = AgronomicThresholdModel.get_or_create(
            variable=threshold.variable,
            defaults={
                "min_value": threshold.min_value,
                "max_value": threshold.max_value,
            },
        )

        if not created:
            record.min_value = threshold.min_value
            record.max_value = threshold.max_value
            record.save()
            logger.debug(
                "Umbral actualizado: variable='%s' [%.1f, %.1f].",
                threshold.variable,
                threshold.min_value,
                threshold.max_value,
            )
        else:
            logger.debug(
                "Umbral creado: variable='%s' [%.1f, %.1f].",
                threshold.variable,
                threshold.min_value,
                threshold.max_value,
            )
