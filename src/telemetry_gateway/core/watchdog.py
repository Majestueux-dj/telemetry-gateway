# Signal de vie pour le healthcheck Docker

from __future__ import annotations

# lib standard
import os
from pathlib import Path


# on touche un fichier à chaque tour de boucle, le healthcheck docker regarde son âge
class SignalVie:
    def __init__(self, chemin: str | os.PathLike, intervalle_min_s: float = 1.0) -> None:
        self.chemin = Path(chemin)
        self.intervalle_min_s = intervalle_min_s
        self._dernier = float("-inf")

    # pas plus d'une fois par seconde, inutile d'écrire sur la SD à chaque tour
    def signaler(self, maintenant: float) -> None:
        if maintenant - self._dernier < self.intervalle_min_s:
            return
        self._dernier = maintenant
        try:
            self.chemin.touch()
        except OSError:
            pass  # pas grave, au pire docker le voit unhealthy
