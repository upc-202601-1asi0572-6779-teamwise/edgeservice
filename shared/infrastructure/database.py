"""
shared/infrastructure/database.py

Instancia compartida de SQLiteDatabase (Peewee) y función init_db().
Todos los modelos del proyecto importan `db` desde aquí para asociarse
a la misma base de datos.

init_db() recibe las clases de modelos como argumento para evitar
imports circulares: app.py importa los modelos primero y luego
llama a init_db(models).
"""

import logging
from peewee import SqliteDatabase

logger = logging.getLogger(__name__)

# Instancia única de la base de datos.
# La ruta se define en init_db(); hasta entonces permanece sin conectar.
db = SqliteDatabase(None)


def init_db(database_path: str, models: list) -> None:
    """
    Inicializa la conexión SQLite y crea las tablas si no existen.

    Args:
        database_path: Ruta al archivo .db (p.ej. "smart_palm.db").
        models:        Lista de clases Peewee Model a registrar
                       (DeviceModel, TelemetryRecordModel, AgronomicThresholdModel).
    """
    db.init(database_path)
    db.connect(reuse_if_open=True)
    db.create_tables(models, safe=True)
    logger.info(
        "Base de datos inicializada: %s — tablas: %s",
        database_path,
        [m._meta.table_name for m in models],
    )
