"""
iam/infrastructure/database.py

Modelo Peewee para la tabla `devices`.
DeviceModel es la representación de infraestructura de la entidad Device.
"""

from datetime import datetime, timezone
from peewee import Model, CharField, DateTimeField

from shared.infrastructure.database import db


class DeviceModel(Model):
    """
    Tabla `devices` en SQLite.

    Columns:
        device_id:  Identificador único del dispositivo (PK lógica).
        api_key:    Clave de autenticación del dispositivo.
        created_at: Fecha y hora UTC de registro.
    """

    device_id = CharField(max_length=100, unique=True, index=True)
    api_key = CharField(max_length=255)
    created_at = DateTimeField(
        default=lambda: datetime.now(timezone.utc)
    )

    class Meta:
        database = db
        table_name = "devices"
