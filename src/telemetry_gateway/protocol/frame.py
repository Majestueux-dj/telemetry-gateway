# Trame : en-tête (20 octets) plus charge utile plus CRC16 (2 octets)
# SYNC(2) VER(1) TYPE(1) NOEUD(2) SEQ(4) HORODATAGE_US(8) LONG(2) | CHARGE(LONG) | CRC(2)
# tout en big-endian

from __future__ import annotations

# lib standard
import struct  # pour packer l'en-tête en octets
from dataclasses import dataclass

# nos modules
from .crc import crc16_ccitt

# 0xA55A = 1010 0101 0101 1010, peu de chances de tomber dessus par hasard
# en UDP ça sert surtout à jeter vite les paquets qui ne sont pas à nous
SYNC = 0xA55A
# pour refuser proprement les vieilles trames si on change le format
VERSION = 1

_ENTETE = struct.Struct(">HBBHIQH")
_CRC = struct.Struct(">H")
TAILLE_ENTETE = _ENTETE.size  # 20
SURCOUT = TAILLE_ENTETE + _CRC.size  # 22

# on reste sous le MTU pour pas fragmenter (nos charges font 28 octets max de toute façon)
TAILLE_CHARGE_MAX = 1024


# trame cassée ou pas à nous, hérite de ValueError pour tout attraper d'un coup
class ErreurTrame(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Trame:
    type_msg: int
    id_noeud: int
    seq: int
    horodatage_us: int
    charge: bytes


# CRC calculé sur en-tête + charge
def encoder_trame(trame: Trame) -> bytes:
    if len(trame.charge) > TAILLE_CHARGE_MAX:
        raise ErreurTrame(f"charge trop grande : {len(trame.charge)} > {TAILLE_CHARGE_MAX}")
    entete = _ENTETE.pack(
        SYNC,
        VERSION,
        trame.type_msg & 0xFF,
        trame.id_noeud & 0xFFFF,
        trame.seq & 0xFFFFFFFF,
        trame.horodatage_us & 0xFFFFFFFFFFFFFFFF,
        len(trame.charge),
    )
    corps = entete + trame.charge
    return corps + _CRC.pack(crc16_ccitt(corps))


# vérifie et décode, sinon ErreurTrame
# taille avant l'en-tête et longueur avant le CRC, pour pas lire hors du buffer
def decoder_trame(donnees: bytes) -> Trame:
    if len(donnees) < SURCOUT:
        raise ErreurTrame(f"trame trop courte : {len(donnees)} octets")

    sync, version, type_msg, id_noeud, seq, horodatage, longueur = _ENTETE.unpack_from(donnees)
    if sync != SYNC:
        raise ErreurTrame(f"mot de synchro invalide 0x{sync:04X}")
    if version != VERSION:
        raise ErreurTrame(f"version de protocole non supportée : {version}")
    if len(donnees) != SURCOUT + longueur:
        raise ErreurTrame(
            f"longueur incohérente : en-tête {longueur}, reçu {len(donnees) - SURCOUT}"
        )

    (crc_recu,) = _CRC.unpack_from(donnees, TAILLE_ENTETE + longueur)
    # memoryview pour pas recopier
    crc_calcule = crc16_ccitt(memoryview(donnees)[: TAILLE_ENTETE + longueur])
    if crc_recu != crc_calcule:
        raise ErreurTrame(f"CRC faux : reçu 0x{crc_recu:04X}, calculé 0x{crc_calcule:04X}")

    charge = bytes(donnees[TAILLE_ENTETE : TAILLE_ENTETE + longueur])
    return Trame(type_msg=type_msg, id_noeud=id_noeud, seq=seq, horodatage_us=horodatage, charge=charge)
