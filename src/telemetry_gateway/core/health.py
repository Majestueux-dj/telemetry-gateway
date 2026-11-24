# État des capteurs et ré-init auto

from __future__ import annotations

# lib standard
import logging
from dataclasses import dataclass

# nos modules
from ..drivers import Capteur, ErreurCapteur
from ..models import EtatCapteur

log = logging.getLogger(__name__)


# par défaut, sinon [surveillance] dans gateway.toml
@dataclass
class PolitiqueSante:
    max_erreurs_consecutives: int = 3
    delai_s: float = 2.0        # 1er délai avant de retenter l'init
    delai_max_s: float = 30.0


# un par capteur : OK après l'init, DEGRADE s'il rate une lecture, EN_PANNE s'il en rate trop
class SanteCapteur:
    def __init__(self, capteur: Capteur, politique: PolitiqueSante) -> None:
        self.capteur = capteur
        self.politique = politique
        self.etat = EtatCapteur.NON_INITIALISE
        self.erreurs_consecutives = 0
        self.erreurs_totales = 0        # jamais remis à 0, envoyé dans les trames SANTE
        self._delai = politique.delai_s
        self._prochaine_init = 0.0

    # lisible en OK ou DEGRADE
    @property
    def utilisable(self) -> bool:
        return self.etat in (EtatCapteur.OK, EtatCapteur.DEGRADE)

    # retente l'init si le délai est passé, le délai double à chaque échec
    # pour pas spammer le bus si le capteur est débranché
    def tenter_init(self, maintenant: float) -> bool:
        if self.utilisable or maintenant < self._prochaine_init:
            return False
        try:
            self.capteur.initialiser()
        except ErreurCapteur as err:
            self.erreurs_totales += 1
            self._prochaine_init = maintenant + self._delai
            log.warning("%s : init ratée (%s), on réessaie dans %.0f s",
                        self.capteur.nom, err, self._delai)
            self._delai = min(self._delai * 2, self.politique.delai_max_s)
            return False

        log.info("%s ok", self.capteur.nom)
        self.etat = EtatCapteur.OK
        self.erreurs_consecutives = 0
        self._delai = self.politique.delai_s   # ça remarche, on repart du délai de base
        return True

    # lecture ok, on repasse OK
    def noter_succes(self) -> None:
        if self.etat == EtatCapteur.DEGRADE:
            log.info("%s répond de nouveau", self.capteur.nom)
        self.etat = EtatCapteur.OK
        self.erreurs_consecutives = 0

    # lecture ratée, renvoie True seulement au passage en EN_PANNE (pour l'alarme)
    def noter_erreur(self, maintenant: float, err: Exception) -> bool:
        self.erreurs_totales += 1
        self.erreurs_consecutives += 1

        if self.erreurs_consecutives >= self.politique.max_erreurs_consecutives:
            log.error("%s HS, %d erreurs de suite (%s)",
                      self.capteur.nom, self.erreurs_consecutives, err)
            self.etat = EtatCapteur.EN_PANNE
            self._prochaine_init = maintenant + self._delai
            return True

        log.warning("%s : lecture ratée (%s)", self.capteur.nom, err)
        self.etat = EtatCapteur.DEGRADE
        return False
