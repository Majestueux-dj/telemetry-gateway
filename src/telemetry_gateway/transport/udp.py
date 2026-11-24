# Envoi des trames en UDP

from __future__ import annotations

# lib standard
import logging
import socket

log = logging.getLogger(__name__)


class EmetteurUdp:
    def __init__(self, hote: str, port: int) -> None:
        self.destination = (hote, port)
        self.envoyees = 0
        self.erreurs = 0
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setblocking(False)

    # False si l'envoi a raté
    def envoyer(self, datagramme: bytes) -> bool:
        try:
            self._sock.sendto(datagramme, self.destination)
        except OSError as err:
            # réseau coupé, pas de route... on compte et on continue
            self.erreurs += 1

            # on log 1 erreur sur 100, sinon à ~22 trames/s ça inonde les logs
            if self.erreurs == 1 or self.erreurs % 100 == 0:
                log.warning("envoi UDP vers %s:%d impossible (%d erreurs) : %s",
                            *self.destination, self.erreurs, err)
            return False

        self.envoyees += 1
        return True

    def fermer(self) -> None:
        self._sock.close()
