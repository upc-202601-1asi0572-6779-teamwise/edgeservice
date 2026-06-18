"""
telemetry/infrastructure/database.py

Modelos Peewee para las tablas de telemetría.

TelemetryRecordModel — tabla `telemetry_records`: encabezado del lote de lecturas.
SensorReadingModel   — tabla `sensor_readings`: lecturas individuales de sensores,
                       con FK a telemetry_records.
"""

from datetime import datetime, timezone
from peewee import (
    Model,
    CharField,
    DateTimeField,
    FloatField,
    ForeignKeyField,
    AutoField,
)

from shared.infrastructure.database import db


class TelemetryRecordModel(Model):
    """
    Tabla `telemetry_records`.

    Encabezado de un lote de lecturas enviado por un dispositivo IoT.

    Columns:
        id:          Clave primaria autoincremental.
        device_id:   Identificador del dispositivo que generó las lecturas.
        recorded_at: Fecha y hora UTC en que el Edge API recibió el lote.
    """

    id = AutoField()
    device_id = CharField(max_length=100, index=True)
    recorded_at = DateTimeField(
        default=lambda: datetime.now(timezone.utc)
    )

    class Meta:
        database = db
        table_name = "telemetry_records"


class SensorReadingModel(Model):
    """
    Tabla `sensor_readings`.

    Lectura individual de un sensor asociada a un lote de telemetría.

    Columns:
        id:        Clave primaria autoincremental.
        record:    FK a TelemetryRecordModel (CASCADE delete).
        variable:  Nombre de la variable medida (p.ej. "temperature").
        value:     Valor numérico registrado.
        unit:      Unidad de medida (p.ej. "°C", "%", "lux").
        timestamp: Fecha y hora UTC en que el sensor tomó la lectura.
    """

    id = AutoField()
    record = ForeignKeyField(
        TelemetryRecordModel,
        backref="readings",
        on_delete="CASCADE",
    )
    variable = CharField(max_length=50, index=True)
    value = FloatField()
    unit = CharField(max_length=20)
    timestamp = DateTimeField()

    class Meta:
        database = db
        table_name = "sensor_readings"
