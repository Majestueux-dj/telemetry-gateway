# Les objets qui circulent entre les couches, toujours en vraies unités

from __future__ import annotations

# lib standard
import math  # pour sqrt
from dataclasses import dataclass
from enum import IntEnum


# ces valeurs partent telles quelles dans les trames
# si on les change il faut monter VERSION (frame.py)
class IdCapteur(IntEnum):
    BMP280 = 1
    MPU6050 = 2


class EtatCapteur(IntEnum):
    NON_INITIALISE = 0
    OK = 1
    DEGRADE = 2     # quelques erreurs, mais on continue de le lire
    EN_PANNE = 3    # trop d'erreurs d'affilée, on attend la ré-init


# frozen : une mesure ne bouge plus, slots : vers_dict() s'en sert
@dataclass(frozen=True, slots=True)
class MesureEnvironnement:
    temperature_c: float
    pression_pa: float
    altitude_m: float


@dataclass(frozen=True, slots=True)
class MesureInertielle:
    ax_g: float
    ay_g: float
    az_g: float
    gx_dps: float
    gy_dps: float
    gz_dps: float
    temperature_c: float

    # la norme plutôt qu'un axe, un choc peut venir de partout (~1 g au repos)
    @property
    def norme_accel_g(self) -> float:
        return math.sqrt(self.ax_g**2 + self.ay_g**2 + self.az_g**2)

    @property
    def norme_gyro_dps(self) -> float:
        return math.sqrt(self.gx_dps**2 + self.gy_dps**2 + self.gz_dps**2)


@dataclass(frozen=True, slots=True)
class RapportSante:
    duree_marche_s: int
    etat_bmp280: EtatCapteur
    etat_mpu6050: EtatCapteur
    trames_envoyees: int
    erreurs_envoi: int
    erreurs_capteurs: int


class CodeAlarme(IntEnum):
    TEMPERATURE_HAUTE = 1
    TEMPERATURE_BASSE = 2
    PRESSION_BASSE = 3
    CHOC = 4
    GYRO_EXCESSIF = 5
    CAPTEUR_EN_PANNE = 6
    CAPTEUR_RETABLI = 7


# valeur : celle qui a déclenché l'alarme (ou le nb d'erreurs pour CAPTEUR_EN_PANNE)
@dataclass(frozen=True, slots=True)
class Alarme:
    capteur: IdCapteur
    code: CodeAlarme
    valeur: float
