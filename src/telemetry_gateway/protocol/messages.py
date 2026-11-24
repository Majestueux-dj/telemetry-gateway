# Contenu des trames : mesures et alarmes en octets
# format fixe par type plutôt que du JSON, c'est bien plus petit

from __future__ import annotations

# lib standard
import struct
from enum import IntEnum
from typing import Any

# nos modules
from ..models import (
    Alarme,
    CodeAlarme,
    EtatCapteur,
    IdCapteur,
    MesureEnvironnement,
    MesureInertielle,
    RapportSante,
)


# types de messages
class TypeMessage(IntEnum):
    ENVIRONNEMENT = 0x01  # BMP280
    INERTIEL = 0x02       # MPU-6050
    SANTE = 0x10          # état du service, toutes les 5 s
    ALARME = 0x20         # seuil dépassé ou capteur en panne

_ENV = struct.Struct(">fff")          # température, pression, altitude : 12 octets
_IMU = struct.Struct(">7f")           # ax ay az gx gy gz + température : 28 octets
_SANTE = struct.Struct(">IBBIII")     # durée de marche, état bmp, état mpu, compteurs : 18 octets
_ALARME = struct.Struct(">BBf")       # capteur, code, valeur : 6 octets

Message = MesureEnvironnement | MesureInertielle | RapportSante | Alarme


# le type se déduit de la classe
def encoder_charge(msg: Message) -> tuple[TypeMessage, bytes]:
    match msg:
        case MesureEnvironnement():
            return TypeMessage.ENVIRONNEMENT, _ENV.pack(msg.temperature_c, msg.pression_pa, msg.altitude_m)
        case MesureInertielle():
            return TypeMessage.INERTIEL, _IMU.pack(
                msg.ax_g, msg.ay_g, msg.az_g, msg.gx_dps, msg.gy_dps, msg.gz_dps, msg.temperature_c
            )
        case RapportSante():
            return TypeMessage.SANTE, _SANTE.pack(
                msg.duree_marche_s & 0xFFFFFFFF,
                msg.etat_bmp280,
                msg.etat_mpu6050,
                msg.trames_envoyees & 0xFFFFFFFF,
                msg.erreurs_envoi & 0xFFFFFFFF,
                msg.erreurs_capteurs & 0xFFFFFFFF,
            )
        case Alarme():
            return TypeMessage.ALARME, _ALARME.pack(msg.capteur, msg.code, msg.valeur)
    raise TypeError(f"impossible d'encoder {type(msg).__name__}")


# l'inverse, côté station sol. type inconnu ou mauvaise taille : ValueError
def decoder_charge(type_msg: int, charge: bytes) -> Message:
    try:
        match TypeMessage(type_msg):
            case TypeMessage.ENVIRONNEMENT:
                return MesureEnvironnement(*_ENV.unpack(charge))
            case TypeMessage.INERTIEL:
                return MesureInertielle(*_IMU.unpack(charge))
            case TypeMessage.SANTE:
                marche, etat_bmp, etat_mpu, envoyees, err_envoi, err_capteurs = _SANTE.unpack(charge)
                return RapportSante(
                    marche, EtatCapteur(etat_bmp), EtatCapteur(etat_mpu), envoyees, err_envoi, err_capteurs
                )
            case TypeMessage.ALARME:
                capteur, code, valeur = _ALARME.unpack(charge)
                return Alarme(IdCapteur(capteur), CodeAlarme(code), valeur)
    except (struct.error, ValueError) as err:
        raise ValueError(f"charge invalide pour le type 0x{type_msg:02X} : {err}") from err
    # normalement impossible, TypeMessage() a déjà levé
    raise AssertionError("inatteignable")


# en dict pour l'affichage et le JSON
def vers_dict(msg: Message) -> dict[str, Any]:
    resultat: dict[str, Any] = {}
    for nom in msg.__slots__:  # type: ignore[union-attr]
        valeur = getattr(msg, nom)
        resultat[nom] = valeur.name if isinstance(valeur, IntEnum) else valeur
    return resultat
