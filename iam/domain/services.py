"""
iam/domain/services.py

Interfaz de repositorio y domain service del bounded context IAM.

IDeviceRepository define el contrato que debe cumplir cualquier
implementación de persistencia de dispositivos (SQLite via Peewee,
in-memory para tests, etc.).

DeviceDomainService encapsula la lógica de negocio de autenticación:
dado un par (device_id, api_key), determina si corresponde a un
dispositivo registrado y activo.
"""

from abc import ABC, abstractmethod
from typing import Optional

from iam.domain.model import Device


class IDeviceRepository(ABC):
    """Contrato de acceso a datos para Device."""

    @abstractmethod
    def find_by_device_id(self, device_id: str) -> Optional[Device]:
        """
        Busca un dispositivo por su identificador.

        Args:
            device_id: Identificador del dispositivo.

        Returns:
            Device si existe, None si no está registrado.
        """
        raise NotImplementedError


class DeviceDomainService:
    """
    Lógica de dominio para autenticación de dispositivos.

    Verifica que el par (device_id, api_key) corresponda a un
    dispositivo registrado en el repositorio.
    """

    def __init__(self, device_repository: IDeviceRepository) -> None:
        self._repo = device_repository

    def authenticate(self, device_id: str, api_key: str) -> bool:
        """
        Valida las credenciales de un dispositivo.

        Args:
            device_id: Identificador del dispositivo.
            api_key:   API key enviada en el header X-API-Key.

        Returns:
            True si las credenciales son válidas, False en caso contrario.
        """
        device = self._repo.find_by_device_id(device_id)
        if device is None:
            return False
        return device.matches_credentials(device_id, api_key)
