# Classe de base commune aux drivers

from __future__ import annotations

# lib standard
from abc import ABC, abstractmethod  # initialiser() et lire() obligatoires
from typing import Generic, TypeVar

# nos modules
from ..hal import BusI2C
from ..models import IdCapteur

T = TypeVar("T")


# Levée dès qu'un capteur pose problème (mauvais ID, erreur I2C, valeur bizarre...)
class ErreurCapteur(Exception):
    pass


# initialiser() une fois puis lire() en boucle
# on peut rappeler initialiser() pour relancer un capteur qui a planté
class Capteur(ABC, Generic[T]):
    id_capteur: IdCapteur

    def __init__(self, bus: BusI2C, adresse: int) -> None:
        self.bus = bus
        self.adresse = adresse

    # nom affiché dans les logs, ex : BMP280@0x76
    @property
    def nom(self) -> str:
        return f"{self.id_capteur.name}@0x{self.adresse:02X}"

    # vérifie que le composant répond, reset et config
    @abstractmethod
    def initialiser(self) -> None: ...

    # une mesure en vraies unités
    @abstractmethod
    def lire(self) -> T: ...
