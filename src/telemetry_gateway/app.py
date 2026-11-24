# Service principal, c'est ici que tout est branché

# pour écrire int | None dans les annotations
from __future__ import annotations

# lib standard
import logging
import signal  # pour attraper le SIGTERM de docker stop
import threading  # juste pour Event
import time

# nos modules
from .config import Config
from .core.alarms import SurveillanceAlarmes
from .core.health import SanteCapteur
from .core.scheduler import Ordonnanceur
from .core.watchdog import SignalVie
from .drivers import BMP280, MPU6050, Capteur, ErreurCapteur
from .hal import ouvrir_bus
from .models import Alarme, CodeAlarme, EtatCapteur, IdCapteur, RapportSante
from .protocol import Trame, encoder_charge, encoder_trame
from .protocol.messages import Message
from .transport import EmetteurUdp

log = logging.getLogger(__name__)


class Passerelle:

    def __init__(self, conf: Config):
        self.conf = conf
        self.bus = ouvrir_bus(conf.bus_i2c)
        self.emetteur = EmetteurUdp(conf.hote, conf.port)

        self.alarmes = SurveillanceAlarmes(conf.seuils)
        self.signal_vie = SignalVie(conf.fichier_signal_vie)
        self.ordonnanceur = Ordonnanceur()
        self.sante: dict[IdCapteur, SanteCapteur] = {}

        self._seq = 0
        self._demarrage = time.monotonic()
        self._arret = threading.Event()

        if conf.bmp280.actif:
            bmp = BMP280(self.bus, conf.bmp280.adresse, pression_mer_pa=conf.bmp280.pression_mer_pa)
            self._ajouter_capteur(bmp, conf.bmp280.periode_s)

        if conf.mpu6050.actif:
            mpu = MPU6050(
                self.bus,
                conf.mpu6050.adresse,
                gamme_accel_g=conf.mpu6050.gamme_accel_g,
                gamme_gyro_dps=conf.mpu6050.gamme_gyro_dps,
            )
            self._ajouter_capteur(mpu, conf.mpu6050.periode_s)

        self.ordonnanceur.ajouter("sante", conf.periode_sante_s, self._envoyer_sante)

    # pas d'initialiser() ici, _lire_capteur() le fait au 1er passage
    # comme ça un capteur absent au démarrage ne bloque pas tout
    def _ajouter_capteur(self, capteur: Capteur, periode_s: float) -> None:
        sc = SanteCapteur(capteur, self.conf.sante)
        self.sante[capteur.id_capteur] = sc
        self.ordonnanceur.ajouter(capteur.nom, periode_s, lambda t: self._lire_capteur(sc, t))

    # appelé par l'ordonnanceur à la période du capteur
    def _lire_capteur(self, sc: SanteCapteur, maintenant: float) -> None:
        if not sc.utilisable:
            ok = sc.tenter_init(maintenant)
            if ok and sc.erreurs_totales:
                self.publier(Alarme(sc.capteur.id_capteur, CodeAlarme.CAPTEUR_RETABLI, 0.0))
            if not sc.utilisable:
                return

        try:
            mesure = sc.capteur.lire()
        except ErreurCapteur as err:
            if sc.noter_erreur(maintenant, err):
                nb_err = float(sc.erreurs_consecutives)
                self.publier(Alarme(sc.capteur.id_capteur, CodeAlarme.CAPTEUR_EN_PANNE, nb_err))
            return

        sc.noter_succes()
        # la mesure part avant l'alarme
        self.publier(mesure)
        for alarme in self.alarmes.verifier(mesure):
            log.warning("ALARME %s %s valeur=%.2f", alarme.capteur.name, alarme.code.name, alarme.valeur)
            self.publier(alarme)

    def _etat(self, id_capteur: IdCapteur) -> EtatCapteur:
        sc = self.sante.get(id_capteur)
        if sc is None:
            return EtatCapteur.NON_INITIALISE
        return sc.etat

    def _envoyer_sante(self, maintenant: float) -> None:
        total_err_capteurs = sum(s.erreurs_totales for s in self.sante.values())
        rapport = RapportSante(
            duree_marche_s=int(maintenant - self._demarrage),
            etat_bmp280=self._etat(IdCapteur.BMP280),
            etat_mpu6050=self._etat(IdCapteur.MPU6050),
            trames_envoyees=self.emetteur.envoyees,
            erreurs_envoi=self.emetteur.erreurs,
            erreurs_capteurs=total_err_capteurs,
        )
        self.publier(rapport)

    # tout ce qui part vers la station sol passe par là
    def publier(self, msg: Message) -> None:
        type_msg, charge = encoder_charge(msg)
        trame = Trame(
            type_msg=type_msg,
            id_noeud=self.conf.id_noeud,
            seq=self._seq,
            horodatage_us=time.time_ns() // 1000,
            charge=charge,
        )
        self._seq = (self._seq + 1) & 0xFFFFFFFF
        self.emetteur.envoyer(encoder_trame(trame))

    # signal.signal passe (signum, frame), on s'en sert pas
    def arreter(self, *_: object) -> None:
        self._arret.set()

    def executer(self) -> None:
        # docker stop ou Ctrl+C : on sort de la boucle proprement
        signal.signal(signal.SIGTERM, self.arreter)
        signal.signal(signal.SIGINT, self.arreter)

        log.info("passerelle noeud=%d -> udp://%s:%d (/dev/i2c-%d)",
                 self.conf.id_noeud, self.conf.hote, self.conf.port, self.conf.bus_i2c)

        try:
            while not self._arret.is_set():
                delai = self.ordonnanceur.executer_en_attente()
                # si une lecture I2C bloque, le heartbeat n'est plus touché et docker relance
                self.signal_vie.signaler(time.monotonic())
                # wait() plutôt que sleep() pour sortir direct si on arrête
                self._arret.wait(delai)
        finally:
            log.info("arrêt (%d trames envoyées, %d erreurs d'envoi)",
                     self.emetteur.envoyees, self.emetteur.erreurs)
            self.emetteur.fermer()
            self.bus.fermer()
