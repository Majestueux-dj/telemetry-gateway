# Le protocole de télémesure

Tout est en big-endian, les flottants en IEEE-754 simple précision.

## Trame

| Offset | Taille | Champ          | Description                                       |
|-------:|-------:|----------------|---------------------------------------------------|
| 0      | 2      | `SYNC`         | `0xA55A`                                          |
| 2      | 1      | `VERSION`      | `1`                                               |
| 3      | 1      | `TYPE`         | type de message (voir plus bas)                   |
| 4      | 2      | `ID_NOEUD`     | identifiant de la passerelle                      |
| 6      | 4      | `SEQ`          | compteur incrémenté à chaque trame, reboucle à 2³²|
| 10     | 8      | `HORODATAGE_US`| heure Unix en microsecondes                       |
| 18     | 2      | `LONG`         | taille de la charge utile N (≤ 1024)              |
| 20     | N      | `CHARGE`       |                                                   |
| 20+N   | 2      | `CRC`          | CRC-16/CCITT-FALSE des octets 0 à 20+N-1          |

**CRC-16/CCITT-FALSE** : polynôme `0x1021`, valeur initiale `0xFFFF`, pas de réflexion, pas de XOR final. Test : `CRC("123456789") = 0x29B1`.

Une trame est jetée si elle fait moins de 22 octets, si SYNC ou la version ne collent pas, si `LONG` ne correspond pas à la taille du datagramme, ou si le CRC est faux.

## Messages

### `0x01` ENVIRONNEMENT (BMP280), 12 octets

| Champ          | Type | Unité |
|----------------|------|-------|
| temperature_c  | f32  | °C    |
| pression_pa    | f32  | Pa    |
| altitude_m     | f32  | m     |

### `0x02` INERTIEL (MPU-6050), 28 octets

| Champ          | Type | Unité |
|----------------|------|-------|
| ax_g, ay_g, az_g | 3×f32 | g   |
| gx_dps, gy_dps, gz_dps | 3×f32 | °/s |
| temperature_c  | f32  | °C    |

### `0x10` SANTE, 18 octets

| Champ          | Type | Description                                  |
|----------------|------|----------------------------------------------|
| duree_marche_s | u32  | temps depuis le démarrage du service         |
| etat_bmp280    | u8   | 0 NON_INITIALISE, 1 OK, 2 DEGRADE, 3 EN_PANNE|
| etat_mpu6050   | u8   | idem                                         |
| trames_envoyees| u32  |                                              |
| erreurs_envoi  | u32  | erreurs d'envoi UDP                          |
| erreurs_capteurs| u32 | erreurs capteurs cumulées                    |

### `0x20` ALARME, 6 octets

| Champ   | Type | Description |
|---------|------|-------------|
| capteur | u8   | 1 BMP280, 2 MPU6050 |
| code    | u8   | 1 TEMPERATURE_HAUTE, 2 TEMPERATURE_BASSE, 3 PRESSION_BASSE, 4 CHOC, 5 GYRO_EXCESSIF, 6 CAPTEUR_EN_PANNE, 7 CAPTEUR_RETABLI |
| valeur  | f32  | valeur qui a déclenché l'alarme |

## Détection des pertes

À la réception, pour chaque `ID_NOEUD` : `perdues = (SEQ - SEQ_précédent - 1) mod 2³²`. Un écart de plus de 2³¹ veut dire une trame en retard ou dupliquée, ou une passerelle qui a redémarré : on ne le compte pas comme une perte.

## Exemple

Trame ENVIRONNEMENT, noeud 1, séquence 0 :

```
A5 5A 01 01 00 01 00 00 00 00  00 06 2A ...  00 0C  41 C7 99 9A ...  XX XX
SYNC  V  T  NOEUD SEQ          HORODATAGE_US  LONG   T=24.95 ...       CRC
```
