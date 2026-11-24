# Driver MPU-6050 (accéléromètre et gyroscope), InvenSense
# doc : MPU-6000/MPU-6050 Register Map

from __future__ import annotations

# lib standard
import struct  # pour décoder les 14 octets de mesure
import time  # pause après le reset

# nos modules
from ..hal import BusI2C, ErreurI2C
from ..models import IdCapteur, MesureInertielle
from .base import Capteur, ErreurCapteur

# Registres
REG_SMPLRT_DIV = 0x19
REG_CONFIG = 0x1A
REG_GYRO_CONFIG = 0x1B
REG_ACCEL_CONFIG = 0x1C
REG_ACCEL_XOUT_H = 0x3B  # 0x3B à 0x48 : accel (6 octets), temp (2), gyro (6), en big-endian
REG_PWR_MGMT_1 = 0x6B
REG_WHO_AM_I = 0x75

WHO_AM_I_VALUE = 0x68
PWR_RESET = 0x80
CLKSEL_PLL_GYRO_X = 0x01  # horloge du gyro X, plus stable que l'oscillateur interne
DLPF_44HZ = 0x03

# gamme : (valeur du registre, LSB par g ou par °/s)
GAMMES_ACCEL = {2: (0, 16384.0), 4: (1, 8192.0), 8: (2, 4096.0), 16: (3, 2048.0)}
GAMMES_GYRO = {250: (0, 131.0), 500: (1, 65.5), 1000: (2, 32.8), 2000: (3, 16.4)}


class MPU6050(Capteur[MesureInertielle]):
    id_capteur = IdCapteur.MPU6050

    # on vérifie les gammes dès la création
    def __init__(
        self,
        bus: BusI2C,
        adresse: int = 0x68,
        gamme_accel_g: int = 2,
        gamme_gyro_dps: int = 250,
    ) -> None:
        super().__init__(bus, adresse)
        if gamme_accel_g not in GAMMES_ACCEL:
            raise ValueError(f"gamme_accel_g doit valoir {sorted(GAMMES_ACCEL)}")
        if gamme_gyro_dps not in GAMMES_GYRO:
            raise ValueError(f"gamme_gyro_dps doit valoir {sorted(GAMMES_GYRO)}")
        self._afs_sel, self._lsb_accel = GAMMES_ACCEL[gamme_accel_g]
        self._fs_sel, self._lsb_gyro = GAMMES_GYRO[gamme_gyro_dps]
        self._initialise = False

    # WHO_AM_I, reset, réveil puis filtre, fréquence et gammes
    def initialiser(self) -> None:
        self._initialise = False
        try:
            id_lu = self.bus.lire_octet(self.adresse, REG_WHO_AM_I)
            if id_lu != WHO_AM_I_VALUE:
                raise ErreurCapteur(f"{self.nom} : WHO_AM_I inattendu 0x{id_lu:02X}")

            self.bus.ecrire_octet(self.adresse, REG_PWR_MGMT_1, PWR_RESET)
            time.sleep(0.1)  # le temps que le reset se fasse

            # il démarre en veille
            self.bus.ecrire_octet(self.adresse, REG_PWR_MGMT_1, CLKSEL_PLL_GYRO_X)
            self.bus.ecrire_octet(self.adresse, REG_CONFIG, DLPF_44HZ)
            # 1 kHz / (1 + 9) = 100 Hz
            self.bus.ecrire_octet(self.adresse, REG_SMPLRT_DIV, 9)
            self.bus.ecrire_octet(self.adresse, REG_GYRO_CONFIG, self._fs_sel << 3)
            self.bus.ecrire_octet(self.adresse, REG_ACCEL_CONFIG, self._afs_sel << 3)
        except ErreurI2C as err:
            raise ErreurCapteur(f"{self.nom} : échec init : {err}") from err
        self._initialise = True

    # les 14 octets d'un coup : ax, ay, az, temp, gx, gy, gz
    def lire_brut(self) -> tuple[int, ...]:
        try:
            octets = self.bus.lire_bloc(self.adresse, REG_ACCEL_XOUT_H, 14)
        except ErreurI2C as err:
            raise ErreurCapteur(f"{self.nom} : échec lecture : {err}") from err
        return struct.unpack(">7h", octets)

    # brut vers g et °/s selon la gamme
    def lire(self) -> MesureInertielle:
        if not self._initialise:
            raise ErreurCapteur(f"{self.nom} : lire() appelé avant initialiser()")
        ax, ay, az, temp, gx, gy, gz = self.lire_brut()
        return MesureInertielle(
            ax_g=ax / self._lsb_accel,
            ay_g=ay / self._lsb_accel,
            az_g=az / self._lsb_accel,
            gx_dps=gx / self._lsb_gyro,
            gy_dps=gy / self._lsb_gyro,
            gz_dps=gz / self._lsb_gyro,
            temperature_c=temp / 340.0 + 36.53,
        )
