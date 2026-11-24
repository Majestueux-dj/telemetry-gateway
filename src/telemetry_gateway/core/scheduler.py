# Petit ordonnanceur à intervalles fixes

from __future__ import annotations

# lib standard
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

log = logging.getLogger(__name__)


# retards = nb de passages sautés parce qu'on était en retard
@dataclass
class TachePeriodique:
    nom: str
    periode_s: float
    fonction: Callable[[float], None]
    prochaine_execution: float = 0.0
    retards: int = 0


# tout dans un seul thread, les deux capteurs partagent le bus donc pas de verrou
class Ordonnanceur:
    # monotonic car time.time() peut sauter avec NTP
    def __init__(self) -> None:
        self._horloge = time.monotonic
        self.taches: list[TachePeriodique] = []

    # lancée une 1re fois au prochain executer_en_attente()
    def ajouter(self, nom: str, periode_s: float, fonction: Callable[[float], None]) -> TachePeriodique:
        if periode_s <= 0:
            raise ValueError("la période doit être > 0")
        tache = TachePeriodique(nom, periode_s, fonction, prochaine_execution=self._horloge())
        self.taches.append(tache)
        return tache

    # lance ce qui est dû et renvoie combien de temps dormir
    def executer_en_attente(self) -> float:
        maintenant = self._horloge()
        for tache in self.taches:
            if maintenant >= tache.prochaine_execution:
                tache.fonction(maintenant)

                # depuis l'échéance d'avant, pas depuis maintenant, sinon ça dérive
                tache.prochaine_execution += tache.periode_s

                # trop en retard : on saute les passages ratés au lieu de tout rattraper
                if tache.prochaine_execution <= maintenant:
                    rates = int((maintenant - tache.prochaine_execution) // tache.periode_s) + 1
                    tache.retards += rates
                    tache.prochaine_execution += rates * tache.periode_s
                    log.warning("%s en retard, %d passage(s) sauté(s)", tache.nom, rates)

        if not self.taches:
            return 0.1
        return max(0.0, min(t.prochaine_execution for t in self.taches) - self._horloge())
