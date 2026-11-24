# Bus I2C : l'interface pour les drivers et la version smbus2 pour la Pi

from __future__ import annotations

# lib standard (smbus2 est importé dans SMBusI2C)
from typing import Protocol


# une seule exception pour les drivers, smbus2 lève des OSError dans tous les sens
class ErreurI2C(IOError):
    pass


# lire et écrire des registres, les drivers ne voient que ça
# si on change de carte il n'y a que SMBusI2C à refaire
class BusI2C(Protocol):
    def lire_octet(self, adresse: int, registre: int) -> int: ...

    def lire_bloc(self, adresse: int, registre: int, longueur: int) -> bytes: ...

    def ecrire_octet(self, adresse: int, registre: int, valeur: int) -> None: ...

    def fermer(self) -> None: ...


# le vrai bus via smbus2
class SMBusI2C:
    def __init__(self, numero_bus: int) -> None:
        try:
            # import ici pour avoir une erreur claire si smbus2 manque
            from smbus2 import SMBus
        except ImportError as err:
            raise RuntimeError(
                "smbus2 est requis sur la cible : pip install 'telemetry-gateway[rpi]'"
            ) from err
        try:
            self._bus = SMBus(numero_bus)
        except OSError as err:
            # souvent : I2C pas activé dans raspi-config ou pas les droits
            raise ErreurI2C(f"impossible d'ouvrir /dev/i2c-{numero_bus} : {err}") from err

    def lire_octet(self, adresse: int, registre: int) -> int:
        try:
            return self._bus.read_byte_data(adresse, registre)
        except OSError as err:
            raise ErreurI2C(f"lecture 0x{adresse:02X}[0x{registre:02X}] : {err}") from err

    # smbus lit 32 octets max par bloc, on en lit 24 au plus
    def lire_bloc(self, adresse: int, registre: int, longueur: int) -> bytes:
        try:
            return bytes(self._bus.read_i2c_block_data(adresse, registre, longueur))
        except OSError as err:
            raise ErreurI2C(
                f"lecture bloc 0x{adresse:02X}[0x{registre:02X}]x{longueur} : {err}"
            ) from err

    def ecrire_octet(self, adresse: int, registre: int, valeur: int) -> None:
        try:
            # au cas où la valeur dépasse un octet
            self._bus.write_byte_data(adresse, registre, valeur & 0xFF)
        except OSError as err:
            raise ErreurI2C(f"écriture 0x{adresse:02X}[0x{registre:02X}] : {err}") from err

    def fermer(self) -> None:
        self._bus.close()


# ouvre /dev/i2c-<numero_bus>
def ouvrir_bus(numero_bus: int) -> BusI2C:
    return SMBusI2C(numero_bus)
