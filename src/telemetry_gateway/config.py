# Lecture et vérification de config/gateway.toml

from __future__ import annotations

# lib standard
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# les dataclass de réglages sont définies là où elles servent
from .core.alarms import Seuils
from .core.health import PolitiqueSante


class ErreurConfig(ValueError):
    pass


@dataclass
class ConfigBMP280:
    actif: bool = True
    adresse: int = 0x76
    periode_s: float = 0.5
    pression_mer_pa: float = 101325.0


@dataclass
class ConfigMPU6050:
    actif: bool = True
    adresse: int = 0x68
    periode_s: float = 0.05
    gamme_accel_g: int = 2
    gamme_gyro_dps: int = 250


# valeurs par défaut si la clé manque dans le toml
@dataclass
class Config:
    id_noeud: int = 1
    periode_sante_s: float = 5.0
    fichier_signal_vie: str = "/tmp/telemetry-gateway.heartbeat"
    niveau_log: str = "INFO"
    bus_i2c: int = 1
    hote: str = "127.0.0.1"
    port: int = 5005
    bmp280: ConfigBMP280 = field(default_factory=ConfigBMP280)
    mpu6050: ConfigMPU6050 = field(default_factory=ConfigMPU6050)
    sante: PolitiqueSante = field(default_factory=PolitiqueSante)
    seuils: Seuils = field(default_factory=Seuils)

    # on vérifie tout au démarrage, mieux vaut refuser de démarrer que planter plus tard
    def valider(self) -> None:
        # id_noeud est sur 16 bits dans l'en-tête des trames
        if not 0 <= self.id_noeud <= 0xFFFF:
            raise ErreurConfig("passerelle.id_noeud doit tenir sur 16 bits")
        if not 1 <= self.port <= 65535:
            raise ErreurConfig("transport.port hors limites")
        for nom, periode in (
            ("bmp280", self.bmp280.periode_s),
            ("mpu6050", self.mpu6050.periode_s),
            ("sante", self.periode_sante_s),
        ):
            if periode <= 0:
                raise ErreurConfig(f"la période {nom} doit être > 0")


def _construire(cls: type, section: dict[str, Any], nom: str):
    try:
        return cls(**section)
    except TypeError as err:
        raise ErreurConfig(f"[{nom}]: {err}") from err


def charger_config(chemin: str | Path) -> Config:
    try:
        with open(chemin, "rb") as f:   # tomllib veut un fichier ouvert en binaire
            brut = tomllib.load(f)
    except FileNotFoundError as err:
        raise ErreurConfig(f"fichier de config introuvable : {chemin}") from err
    except tomllib.TOMLDecodeError as err:
        raise ErreurConfig(f"TOML invalide dans {chemin} : {err}") from err

    passerelle = brut.get("passerelle", {})
    i2c = brut.get("i2c", {})
    transport = brut.get("transport", {})
    capteurs = brut.get("capteurs", {})
    # copie pour retirer seuils sans toucher à brut
    surveillance = dict(brut.get("surveillance", {}))
    seuils = surveillance.pop("seuils", {})

    conf = Config(
        id_noeud=passerelle.get("id_noeud", 1),
        periode_sante_s=passerelle.get("periode_sante_s", 5.0),
        fichier_signal_vie=passerelle.get("fichier_signal_vie", Config.fichier_signal_vie),
        niveau_log=passerelle.get("niveau_log", "INFO"),
        bus_i2c=i2c.get("bus", 1),
        hote=transport.get("hote", "127.0.0.1"),
        port=transport.get("port", 5005),
        bmp280=_construire(ConfigBMP280, capteurs.get("bmp280", {}), "capteurs.bmp280"),
        mpu6050=_construire(ConfigMPU6050, capteurs.get("mpu6050", {}), "capteurs.mpu6050"),
        sante=PolitiqueSante(
            max_erreurs_consecutives=surveillance.get("max_erreurs_consecutives", 3),
            delai_s=surveillance.get("delai_reinit_s", 2.0),
            delai_max_s=surveillance.get("delai_reinit_max_s", 30.0),
        ),
        seuils=_construire(Seuils, seuils, "surveillance.seuils"),
    )
    conf.valider()
    return conf
