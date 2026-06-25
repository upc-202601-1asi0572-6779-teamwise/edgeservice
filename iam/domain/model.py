"""
iam/domain/model.py

Entidades del dominio IAM.
Device es el aggregate root del bounded context de identidad:
representa un dispositivo IoT registrado y autorizado para enviar
lecturas al Edge API.
"""

import hmac
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Device:
    """
    Aggregate root del bounded context IAM.

    Attributes:
        device_id:  Identificador único del dispositivo (p.ej. "smart-palm-001").
        api_key:    Clave de autenticación asociada al dispositivo.
        created_at: Fecha y hora UTC de registro del dispositivo.
    """

    device_id: str
    api_key: str
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def matches_credentials(self, device_id: str, api_key: str) -> bool:
        """
        Verifica si las credenciales proporcionadas coinciden con las del dispositivo.

        Args:
            device_id: Identificador del dispositivo a verificar.
            api_key:   API key a verificar.

        Returns:
            True si ambas credenciales coinciden, False en caso contrario.
        """
        return self.device_id == device_id and hmac.compare_digest(self.api_key, api_key)
