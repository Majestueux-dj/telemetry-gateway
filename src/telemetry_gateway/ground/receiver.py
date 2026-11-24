# Station sol, à lancer sur le PC : telemetry-ground --port 5005

from __future__ import annotations

# lib standard
import argparse
import json  # pour l'option --json
import socket  # réception UDP
import sys
import time
from dataclasses import dataclass

# même décodage que la passerelle
from ..protocol import ErreurTrame, TypeMessage, decoder_charge, decoder_trame
from ..protocol.messages import vers_dict


# stats de liaison par passerelle
# en UDP rien ne prévient quand une trame se perd, on le voit avec les n° de séquence
@dataclass
class StatsLiaison:
    recues: int = 0
    perdues: int = 0
    dernier_seq: int | None = None

    # si on reçoit 10 puis 13 on a raté 11 et 12, donc 2 perdues
    def maj_seq(self, seq: int) -> int:
        ecart = 0
        if self.dernier_seq is not None:
            # seq sur 32 bits, le & gère le passage de 0xFFFFFFFF à 0
            ecart = (seq - self.dernier_seq - 1) & 0xFFFFFFFF

            # seq qui recule (trame en retard ou passerelle redémarrée) : avec le modulo ça
            # ferait ~4 milliards de pertes, donc au-delà de la moitié on compte 0
            if ecart > 0x7FFFFFFF:
                ecart = 0

        self.dernier_seq = seq
        self.recues += 1
        self.perdues += ecart
        return ecart

    # perdues / (reçues + perdues)
    @property
    def taux_perte(self) -> float:
        total = self.recues + self.perdues
        return self.perdues / total if total else 0.0


class StationSol:
    # rangé par id_noeud, sinon deux passerelles sur le même port mélangeraient leurs seq
    def __init__(self) -> None:
        self.liaisons: dict[int, StatsLiaison] = {}
        self.invalides = 0

    # décode un datagramme en dict, une trame fausse est jetée (None)
    def traiter(self, datagramme: bytes) -> dict | None:
        try:
            trame = decoder_trame(datagramme)
            msg = decoder_charge(trame.type_msg, trame.charge)
        except (ErreurTrame, ValueError) as err:
            self.invalides += 1
            print(f"trame rejetée : {err}", file=sys.stderr)
            return None

        # seq mis à jour que sur les trames valides, sinon un seq corrompu fausse les pertes
        liaison = self.liaisons.setdefault(trame.id_noeud, StatsLiaison())
        perdues = liaison.maj_seq(trame.seq)
        return {
            "noeud": trame.id_noeud,
            "seq": trame.seq,
            "horodatage": trame.horodatage_us / 1e6,
            "type": TypeMessage(trame.type_msg).name,
            "perdues_avant": perdues,
            "donnees": vers_dict(msg),
        }


# affichage terminal. l'heure est celle de la Pi, sans réseau au boot (pas de RTC) elle peut être fausse
def _formater(enr: dict) -> str:
    d = enr["donnees"]
    heure = time.strftime("%H:%M:%S", time.localtime(enr["horodatage"]))
    entete = f"{heure} n{enr['noeud']} #{enr['seq']:<6}"
    if enr["perdues_avant"]:
        entete += f" (+{enr['perdues_avant']} perdues)"

    match enr["type"]:
        case "ENVIRONNEMENT":
            # en hPa c'est plus parlant
            corps = (f"T={d['temperature_c']:6.2f}C  P={d['pression_pa'] / 100:8.2f}hPa  "
                     f"alt={d['altitude_m']:7.1f}m")
        case "INERTIEL":
            corps = (f"a=({d['ax_g']:+.2f},{d['ay_g']:+.2f},{d['az_g']:+.2f})g  "
                     f"w=({d['gx_dps']:+6.1f},{d['gy_dps']:+6.1f},{d['gz_dps']:+6.1f})dps")
        case "SANTE":
            corps = (f"marche={d['duree_marche_s']}s bmp={d['etat_bmp280']} mpu={d['etat_mpu6050']} "
                     f"env={d['trames_envoyees']} err={d['erreurs_envoi']}/{d['erreurs_capteurs']}")
        case _:
            # ALARME : rare, on affiche tout
            corps = " ".join(f"{k}={v}" for k, v in d.items())
    return f"{entete} {enr['type']:<13} {corps}"


# écoute jusqu'au Ctrl+C puis affiche le bilan des pertes
def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(prog="telemetry-ground")
    # 0.0.0.0 = toutes les interfaces
    analyseur.add_argument("--ecoute", default="0.0.0.0", help="adresse d'écoute")
    analyseur.add_argument("--port", type=int, default=5005)
    # --json pour rediriger dans un fichier et tracer les courbes après
    analyseur.add_argument("--json", action="store_true")
    # l'IMU envoie 20 trames/s, ça noie le reste
    analyseur.add_argument("--sans-imu", action="store_true", help="masquer les trames INERTIEL")
    options = analyseur.parse_args(argv)

    station = StationSol()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((options.ecoute, options.port))
    print(f"en écoute sur le port {options.port}...", file=sys.stderr)

    try:
        while True:
            # nos trames font 50 octets max, 2048 couvre large le max du protocole (1046)
            donnees, _ = sock.recvfrom(2048)
            enr = station.traiter(donnees)
            if enr is None or (options.sans_imu and enr["type"] == "INERTIEL"):
                continue
            # flush sinon avec une redirection rien ne sort tout de suite
            print(json.dumps(enr) if options.json else _formater(enr), flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        # bilan sur stderr pour pas polluer le JSON
        sock.close()
        for noeud, s in station.liaisons.items():
            print(f"noeud {noeud} : {s.recues} reçues, {s.perdues} perdues "
                  f"({s.taux_perte:.2%}), {station.invalides} invalides", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
