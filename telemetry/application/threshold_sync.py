"""
telemetry/application/threshold_sync.py

Servicio de sincronización de umbrales agronómicos desde la nube.

ThresholdSyncService orquesta la obtención de umbrales del Web Service
central y su persistencia local en SQLite. Se invoca durante el bootstrap
de la aplicación (before_request) para mantener los umbrales actualizados.

Si el cloud no está disponible, el servicio falla silenciosamente: los
umbrales locales existentes se conservan y TelemetryDomainService usará
los valores hardcodeados como fallback de último nivel.
"""

import logging

from telemetry.domain.services import IAgronomicThresholdRepository
from telemetry.infrastructure.cloud_client import CloudApiClient

logger = logging.getLogger(__name__)


class ThresholdSyncService:
    """
    Orquestador de sincronización de umbrales agronómicos.

    Recupera los umbrales configurados en el Web Service central para un
    dispositivo y los persiste localmente para uso offline.

    Attributes:
        _threshold_repo: Repositorio local de umbrales agronómicos.
    """

    def __init__(self, threshold_repository: IAgronomicThresholdRepository) -> None:
        self._threshold_repo = threshold_repository

    def sync(self, device_id: str) -> int:
        """
        Sincroniza los umbrales agronómicos del cloud al repositorio local.

        Flujo:
        1. Llama a CloudApiClient.get_thresholds(device_id).
        2. Si la lista está vacía (cloud no disponible), no modifica los
           umbrales locales existentes y retorna 0.
        3. Para cada umbral recibido, llama a save() en el repositorio
           (upsert: crea o actualiza por variable).

        Args:
            device_id: Identificador del dispositivo para filtrar umbrales.

        Returns:
            Número de umbrales sincronizados. 0 si el cloud no respondió.
        """
        thresholds = CloudApiClient.get_thresholds(device_id)

        if not thresholds:
            logger.info(
                "Sincronización de umbrales omitida: cloud no disponible "
                "o sin umbrales para device_id='%s'.",
                device_id,
            )
            return 0

        for threshold in thresholds:
            self._threshold_repo.save(threshold)

        logger.info(
            "Sincronización completada: %d umbrales actualizados para device_id='%s'.",
            len(thresholds),
            device_id,
        )
        return len(thresholds)
