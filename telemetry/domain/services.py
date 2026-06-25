"""
telemetry/domain/services.py

Interfaz de repositorio y domain service del bounded context Telemetry.

IAgronomicThresholdRepository — contrato de acceso a datos para umbrales.
ITelemetryRepository          — contrato de persistencia de TelemetryRecord.
TelemetryDomainService        — evalúa lecturas contra umbrales agronómicos
                                 y genera el mapa alert_flags.

Los umbrales hardcodeados sirven como fallback cuando la sincronización
con la nube no está disponible.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional

from telemetry.domain.model import AgronomicThreshold, TelemetryRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Umbrales agronómicos de referencia para palma aceitera
# Fuente: literatura agronómica estándar (fallback cuando cloud no disponible)
# ---------------------------------------------------------------------------
_DEFAULT_THRESHOLDS: dict[str, AgronomicThreshold] = {
    "temperature": AgronomicThreshold(
        variable="temperature", min_value=24.0, max_value=32.0
    ),
    "humidity": AgronomicThreshold(
        variable="humidity", min_value=75.0, max_value=100.0
    ),
    "soilMoisture": AgronomicThreshold(
        variable="soilMoisture", min_value=30.0, max_value=80.0
    ),
    "light": AgronomicThreshold(
        variable="light", min_value=10.0, max_value=90.0
    ),
}


# ---------------------------------------------------------------------------
# Interfaces de repositorio
# ---------------------------------------------------------------------------

class IAgronomicThresholdRepository(ABC):
    """Contrato de acceso a datos para AgronomicThreshold."""

    @staticmethod
    @abstractmethod
    def find_by_variable(variable: str) -> Optional[AgronomicThreshold]:
        """
        Busca el umbral agronómico activo para una variable.

        Args:
            variable: Nombre de la variable (p.ej. "temperature").

        Returns:
            AgronomicThreshold si existe en la base de datos, None si no hay
            umbral sincronizado para esa variable.
        """
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def save(threshold: AgronomicThreshold) -> None:
        """
        Persiste o actualiza un umbral agronómico.

        Args:
            threshold: Entidad AgronomicThreshold a guardar.
        """
        raise NotImplementedError


class ITelemetryRepository(ABC):
    """Contrato de persistencia para TelemetryRecord."""

    @staticmethod
    @abstractmethod
    def save(record: TelemetryRecord) -> int:
        """
        Persiste un TelemetryRecord y retorna su ID generado.

        Args:
            record: Aggregate root a persistir.

        Returns:
            ID entero del registro creado en la base de datos.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Domain service
# ---------------------------------------------------------------------------

class TelemetryDomainService:
    """
    Evalúa las lecturas de un TelemetryRecord contra los umbrales agronómicos.

    Resuelve el umbral aplicable para cada variable con la siguiente prioridad:
    1. Umbral sincronizado desde la nube (IAgronomicThresholdRepository).
    2. Umbral hardcodeado (_DEFAULT_THRESHOLDS) si no hay dato sincronizado.

    El resultado es un mapa alert_flags que el ESP32 usa para activar
    alertas LED sin necesidad de conocer los umbrales directamente.
    """

    def __init__(
        self,
        threshold_repository: IAgronomicThresholdRepository,
    ) -> None:
        self._threshold_repo = threshold_repository

    def evaluate_alerts(self, record: TelemetryRecord) -> dict[str, bool]:
        """
        Genera el mapa de alertas para un lote de lecturas.

        Para cada lectura en el record, determina si el valor está fuera
        del rango aceptable. Si no hay umbral configurado para la variable,
        alert_flag se marca como False (sin alerta).

        Args:
            record: TelemetryRecord con las lecturas del dispositivo.

        Returns:
            Diccionario {variable: True si hay alerta, False si está en rango}.
            Ejemplo: {"temperature": False, "humidity": True, "soil_moisture": False}
        """
        alert_flags: dict[str, bool] = {}

        for reading in record.readings:
            threshold = self._resolve_threshold(reading.variable)
            if threshold is None:
                logger.debug(
                    "Sin umbral configurado para variable='%s', alerta=False.",
                    reading.variable,
                )
                alert_flags[reading.variable] = False
                continue

            in_range = threshold.is_within_range(reading.value)
            alert_flags[reading.variable] = not in_range

            if not in_range:
                logger.warning(
                    "Alerta: variable='%s' value=%.2f fuera de rango [%.1f, %.1f].",
                    reading.variable,
                    reading.value,
                    threshold.min_value,
                    threshold.max_value,
                )

        return alert_flags

    def _resolve_threshold(
        self, variable: str
    ) -> Optional[AgronomicThreshold]:
        """
        Resuelve el umbral para una variable con fallback a valores por defecto.

        Args:
            variable: Nombre de la variable a resolver.

        Returns:
            AgronomicThreshold sincronizado si existe, hardcodeado si no,
            None si tampoco hay valor por defecto.
        """
        synced = self._threshold_repo.find_by_variable(variable)
        if synced is not None:
            return synced

        default = _DEFAULT_THRESHOLDS.get(variable)
        if default is not None:
            logger.debug(
                "Usando umbral por defecto para variable='%s'.", variable
            )
        return default
