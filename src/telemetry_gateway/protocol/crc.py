# CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF)
# test : "123456789" doit donner 0x29B1

from __future__ import annotations

POLYNOME = 0x1021
# avec init à 0 les zéros en début de trame ne changeraient pas le CRC
VALEUR_INIT = 0xFFFF


# table des 256 octets, calculée une fois au démarrage
def _construire_table(polynome: int) -> tuple[int, ...]:
    table = []
    for octet in range(256):
        crc = octet << 8
        for _ in range(8):
            crc = ((crc << 1) ^ polynome) if crc & 0x8000 else (crc << 1)
        table.append(crc & 0xFFFF)
    return tuple(table)


_TABLE = _construire_table(POLYNOME)


# avec la table : un accès par octet au lieu de 8 décalages
# crc en paramètre si un jour on veut calculer en plusieurs morceaux
def crc16_ccitt(donnees: bytes | bytearray | memoryview, crc: int = VALEUR_INIT) -> int:
    for o in donnees:
        crc = ((crc << 8) & 0xFFFF) ^ _TABLE[((crc >> 8) ^ o) & 0xFF]
    return crc
