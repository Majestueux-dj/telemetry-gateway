# Driver BMP280 (pression + température), Bosch
# registres et formules de compensation : dans la datasheet (BST-BMP280-DS001)

from __future__ import annotations

# lib standard
import struct  # pour décoder les octets de calibration
import time  # pause après le reset
from dataclasses import dataclass

# nos modules
from ..hal import BusI2C, ErreurI2C
from ..models import IdCapteur, MesureEnvironnement
from .base import Capteur, ErreurCapteur

# Registres
REG_CALIB_START = 0x88   # 24 octets de calibration (0x88 à 0x9F)
REG_CHIP_ID = 0xD0
REG_RESET = 0xE0
REG_STATUS = 0xF3
REG_CTRL_MEAS = 0xF4
REG_CONFIG = 0xF5
REG_PRESS_MSB = 0xF7     # 0xF7 à 0xFC : pression (3 octets) puis température (3 octets)

CHIP_ID = 0x58
RESET_CMD = 0xB6

# pour ctrl_meas
OSRS_X1, OSRS_X2, OSRS_X4, OSRS_X8, OSRS_X16 = 1, 2, 3, 4, 5
MODE_NORMAL = 0b11
# pour config
STANDBY_62_5_MS = 0b001
FILTER_X4 = 0b010


# coefficients gravés en usine, lus une fois à l'init
@dataclass(frozen=True, slots=True)
class Calibration:
    T1: int
    T2: int
    T3: int
    P1: int
    P2: int
    P3: int
    P4: int
    P5: int
    P6: int
    P7: int
    P8: int
    P9: int

    @classmethod
    def depuis_octets(cls, brut: bytes) -> Calibration:
        if len(brut) != 24:
            raise ErreurCapteur(f"le bloc de calibration doit faire 24 octets, reçu {len(brut)}")
        # T1 et P1 non signés, le reste signé, tout en 16 bits little-endian
        return cls(*struct.unpack("<HhhHhhhhhhhh", brut))


# formules de la datasheet (version flottante), t_fine resert pour la pression
def compenser_temperature(adc_t: int, cal: Calibration) -> tuple[float, float]:
    var1 = (adc_t / 16384.0 - cal.T1 / 1024.0) * cal.T2
    var2 = ((adc_t / 131072.0 - cal.T1 / 8192.0) ** 2) * cal.T3
    t_fine = var1 + var2
    return t_fine / 5120.0, t_fine


# pareil pour la pression, en Pa
def compenser_pression(adc_p: int, t_fine: float, cal: Calibration) -> float:
    var1 = t_fine / 2.0 - 64000.0
    var2 = var1 * var1 * cal.P6 / 32768.0
    var2 = var2 + var1 * cal.P5 * 2.0
    var2 = var2 / 4.0 + cal.P4 * 65536.0
    var1 = (cal.P3 * var1 * var1 / 524288.0 + cal.P2 * var1) / 524288.0
    var1 = (1.0 + var1 / 32768.0) * cal.P1
    if var1 == 0:
        raise ErreurCapteur("compensation pression : division par zéro (calibration invalide)")
    p = 1048576.0 - adc_p
    p = (p - var2 / 4096.0) * 6250.0 / var1
    var1 = cal.P9 * p * p / 2147483648.0
    var2 = p * cal.P8 / 32768.0
    return p + (var1 + var2 + cal.P7) / 16.0


# Altitude à partir de la pression
def pression_vers_altitude(pression_pa: float, pression_mer_pa: float = 101325.0) -> float:
    return 44330.0 * (1.0 - (pression_pa / pression_mer_pa) ** (1.0 / 5.255))


class BMP280(Capteur[MesureEnvironnement]):
    id_capteur = IdCapteur.BMP280

    # valeur qu'on lit tant que le capteur n'a fait aucune mesure
    _ADC_SANS_MESURE = 0x80000

    def __init__(
        self,
        bus: BusI2C,
        adresse: int = 0x76,
        pression_mer_pa: float = 101325.0,
        surechantillonnage_t: int = OSRS_X2,
        surechantillonnage_p: int = OSRS_X16,
    ) -> None:
        super().__init__(bus, adresse)
        self.pression_mer_pa = pression_mer_pa
        self._osrs_t = surechantillonnage_t
        self._osrs_p = surechantillonnage_p
        self._cal: Calibration | None = None

    # chip id, reset, calibration puis config
    def initialiser(self) -> None:
        try:
            id_puce = self.bus.lire_octet(self.adresse, REG_CHIP_ID)
            if id_puce != CHIP_ID:
                raise ErreurCapteur(f"{self.nom} : chip id inattendu 0x{id_puce:02X}")

            self.bus.ecrire_octet(self.adresse, REG_RESET, RESET_CMD)
            time.sleep(0.005)  # 2 ms d'après la datasheet, on prend un peu de marge

            self._cal = Calibration.depuis_octets(
                self.bus.lire_bloc(self.adresse, REG_CALIB_START, 24)
            )

            # config avant ctrl_meas, tant que le capteur est encore en sleep
            self.bus.ecrire_octet(
                self.adresse, REG_CONFIG, (STANDBY_62_5_MS << 5) | (FILTER_X4 << 2)
            )
            self.bus.ecrire_octet(
                self.adresse,
                REG_CTRL_MEAS,
                (self._osrs_t << 5) | (self._osrs_p << 2) | MODE_NORMAL,
            )
        except ErreurI2C as err:
            raise ErreurCapteur(f"{self.nom} : échec init : {err}") from err

    # les 6 octets d'un coup pour avoir pression et température de la même mesure
    def lire_brut(self) -> tuple[int, int]:
        try:
            o = self.bus.lire_bloc(self.adresse, REG_PRESS_MSB, 6)
        except ErreurI2C as err:
            raise ErreurCapteur(f"{self.nom} : échec lecture : {err}") from err
        adc_p = (o[0] << 12) | (o[1] << 4) | (o[2] >> 4)
        adc_t = (o[3] << 12) | (o[4] << 4) | (o[5] >> 4)
        return adc_p, adc_t

    # lecture + compensation
    def lire(self) -> MesureEnvironnement:
        if self._cal is None:
            raise ErreurCapteur(f"{self.nom} : lire() appelé avant initialiser()")

        adc_p, adc_t = self.lire_brut()
        if adc_t == self._ADC_SANS_MESURE or adc_p == self._ADC_SANS_MESURE:
            raise ErreurCapteur(f"{self.nom} : pas encore de mesure dispo")

        temperature, t_fine = compenser_temperature(adc_t, self._cal)
        pression = compenser_pression(adc_p, t_fine, self._cal)

        # si on sort de la plage du capteur (-40..85 °C, 300..1100 hPa) c'est que la lecture est fausse
        if not (-40.0 <= temperature <= 85.0 and 30000.0 <= pression <= 110000.0):
            raise ErreurCapteur(f"{self.nom} : valeurs hors plage T={temperature} P={pression}")

        return MesureEnvironnement(
            temperature_c=temperature,
            pression_pa=pression,
            altitude_m=pression_vers_altitude(pression, self.pression_mer_pa),
        )
