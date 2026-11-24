# Alarmes sur seuils

from __future__ import annotations

# lib standard
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# nos modules
from ..models import Alarme, CodeAlarme, IdCapteur, MesureEnvironnement, MesureInertielle


# valeurs par défaut, gateway.toml peut les changer
@dataclass
class Seuils:
    temperature_max_c: float = 60.0
    temperature_min_c: float = -20.0
    pression_min_pa: float = 30000.0
    choc_g: float = 3.0          # norme de l'accél (1 g au repos)
    gyro_max_dps: float = 500.0


# La valeur qu'on regarde plus à partir de quand c'est une alarme.
# active si la valeur est déjà hors limites (il nous servira pour le front montant)
@dataclass
class _Regle:
    capteur: IdCapteur
    code: CodeAlarme
    valeur: Callable[[Any], float]   # mesure BMP280 ou MPU selon la règle
    declenchee: Callable[[float], bool]
    active: bool = False


class SurveillanceAlarmes:

    # les règles rangées par capteur
    def __init__(self, seuils: Seuils) -> None:
        self._regles: dict[type, list[_Regle]] = {
            MesureEnvironnement: [
                _Regle(IdCapteur.BMP280, CodeAlarme.TEMPERATURE_HAUTE,
                       lambda m: m.temperature_c, lambda v: v > seuils.temperature_max_c),
                _Regle(IdCapteur.BMP280, CodeAlarme.TEMPERATURE_BASSE,
                       lambda m: m.temperature_c, lambda v: v < seuils.temperature_min_c),
                _Regle(IdCapteur.BMP280, CodeAlarme.PRESSION_BASSE,
                       lambda m: m.pression_pa, lambda v: v < seuils.pression_min_pa),
            ],
            MesureInertielle: [
                _Regle(IdCapteur.MPU6050, CodeAlarme.CHOC,
                       lambda m: m.norme_accel_g, lambda v: v > seuils.choc_g),
                _Regle(IdCapteur.MPU6050, CodeAlarme.GYRO_EXCESSIF,
                       lambda m: m.norme_gyro_dps, lambda v: v > seuils.gyro_max_dps),
            ],
        }

    # renvoie seulement les nouvelles alarmes sur front montant
    # sinon on en enverrait une toutes les 50 ms tant que ça dépasse
    def verifier(self, mesure: MesureEnvironnement | MesureInertielle) -> list[Alarme]:
        alarmes = []
        for regle in self._regles.get(type(mesure), []):
            valeur = regle.valeur(mesure)
            declenchee = regle.declenchee(valeur)
            if declenchee and not regle.active:
                alarmes.append(Alarme(regle.capteur, regle.code, valeur))
            regle.active = declenchee
        return alarmes
