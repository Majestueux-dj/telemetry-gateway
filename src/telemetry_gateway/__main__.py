# Point d'entrée de la passerelle : telemetry-gateway -c config/gateway.toml

from __future__ import annotations

# lib standard
import argparse  # options -c, --hote...
import logging
import sys

# nos modules
from .app import Passerelle
from .config import ErreurConfig, charger_config
from .hal import ErreurI2C


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(prog="telemetry-gateway")
    analyseur.add_argument("-c", "--config", default="config/gateway.toml")
    # pour changer l'hôte ou le port sans toucher au toml
    analyseur.add_argument("--hote", help="remplace transport.hote")
    analyseur.add_argument("--port", type=int, help="remplace transport.port")
    analyseur.add_argument("-v", "--verbeux", action="store_true")
    options = analyseur.parse_args(argv)

    try:
        conf = charger_config(options.config)
    except ErreurConfig as err:
        print(f"erreur de configuration : {err}", file=sys.stderr)
        return 2
    if options.hote:
        conf.hote = options.hote
    if options.port:
        conf.port = options.port

    # le niveau de log vient de la config, donc on configure après
    logging.basicConfig(
        level=logging.DEBUG if options.verbeux else conf.niveau_log,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    try:
        passerelle = Passerelle(conf)
    except (ErreurI2C, RuntimeError) as err:
        # souvent I2C pas activé ou pas les droits, pas besoin de la trace complète
        print(f"impossible de démarrer : {err}", file=sys.stderr)
        return 1
    passerelle.executer()
    return 0


if __name__ == "__main__":
    sys.exit(main())
