# Passerelle de télémesure sur Raspberry Pi

La Pi lit deux capteurs en I2C, un BMP280 (température, pression) et un MPU-6050 (accéléro, gyro), et envoie les mesures en UDP à un PC qui sert de station sol. Chaque trame a un numéro de séquence et un CRC16, comme ça le PC jette les trames abîmées et sait combien il en a perdu.

Ça tourne dans un conteneur Docker sur la Pi, qui est relancé tout seul si le programme plante ou se bloque.

Matériel :

- une Raspberry Pi avec Docker, sur le même réseau que le PC
- un BMP280 et un MPU-6050
- un PC pour la station sol


## Branchements

Les deux capteurs sont sur le même bus I2C (i2c-1), en 3,3 V.

| Capteur  | VCC  | GND | SDA           | SCL           | Adresse               |
|----------|------|-----|---------------|---------------|-----------------------|
| BMP280   | 3,3V | GND | GPIO2 (pin 3) | GPIO3 (pin 5) | 0x76 (SDO à la masse) |
| MPU-6050 | 3,3V | GND | GPIO2 (pin 3) | GPIO3 (pin 5) | 0x68 (AD0 à la masse) |

Si SDO ou AD0 est au 3,3 V, l'adresse passe à 0x77 ou 0x69, il faut alors changer `adresse` dans `config/gateway.toml`.

Activer l'I2C (`sudo raspi-config`, Interface Options, I2C) puis vérifier que les capteurs répondent :

```bash
sudo apt install i2c-tools
i2cdetect -y 1        # on doit voir 68 et 76
```


## Lancement

### Sur la Pi

Mettre l'IP du PC dans `transport.hote` (`config/gateway.toml`), puis :

```bash
make docker-build
make docker-up
make docker-logs      # pour suivre les logs
```

`make docker-up` récupère le gid du groupe `i2c` de la Pi et le passe au conteneur, sinon il n'a pas le droit d'ouvrir `/dev/i2c-1`.

Après une modif de la config, pas besoin de rebuild : le fichier est monté dans le conteneur, un `docker compose restart gateway` suffit.

Pour débugger sans Docker : `make run` directement sur la Pi (installer smbus2 avant avec `pip install -e ".[rpi]"`).

### Sur le PC (station sol)

```bash
make ground
```

On a une ligne par trame reçue :

```
21:55:43 n1 #0      ENVIRONNEMENT T= 25.13C  P= 1006.51hPa  alt=   56.2m
21:55:43 n1 #2      SANTE         marche=0s bmp=OK mpu=OK env=2 err=0/0
...
noeud 1 : 132 reçues, 0 perdues (0.00%), 0 invalides
```

Le bilan (dernière ligne) s'affiche au Ctrl+C.

Les trames INERTIEL arrivent 20 fois par seconde et noient un peu le reste, on peut les cacher :

```bash
PYTHONPATH=src python3 -m telemetry_gateway.ground.receiver --sans-imu
```

Si rien n'arrive : vérifier `transport.hote` dans la config de la Pi, et que le pare-feu du PC laisse passer l'UDP sur le port 5005.

### Pour tester

- taper un coup sec sur le MPU-6050 : au-delà de 3 g on reçoit une alarme `CHOC`
- poser le doigt sur le BMP280 : la température monte doucement
- débrancher le SDA d'un capteur pendant que ça tourne : après 3 lectures ratées il passe `EN_PANNE` (alarme `CAPTEUR_EN_PANNE`), et quand on rebranche il est ré-initialisé tout seul (alarme `CAPTEUR_RETABLI`)
- couper la station sol et la relancer : la passerelle continue d'envoyer et la réception reprend


## Redémarrage automatique

Deux cas :

- le programme plante : `restart: unless-stopped` dans `docker-compose.yml` le relance (et il redémarre aussi au boot de la Pi)
- le programme se bloque sans planter (une lecture I2C qui ne rend jamais la main par exemple) : le fichier de signal de vie n'est plus mis à jour, le HEALTHCHECK passe le conteneur `unhealthy` au bout d'une quarantaine de secondes et `autoheal` le redémarre. Docker tout seul ne relance pas un conteneur unhealthy, d'où autoheal.

Le schéma et le rôle de chaque fichier sont dans `docs/architecture.pdf`, le format des trames dans `docs/PROTOCOLE.md`.


## Nos choix

- UDP plutôt que TCP : une mesure perdue est remplacée 50 ms après, donc en perdre une n'est pas grave. En TCP la passerelle pourrait se bloquer si la station sol ne répond plus. Et on voit quand même les pertes avec le numéro de séquence.
- Un CRC16 dans la trame, parce que le checksum UDP est optionnel en IPv4 et assez faible. En plus il ne dépend pas du transport, il marcherait pareil sur une liaison série.
- Un seul thread : les deux capteurs sont sur le même bus, avec plusieurs threads il faudrait un verrou. À 20 Hz une boucle suffit largement.
- Drivers écrits à la main à partir des datasheets, sans lib de capteur. Les formules de compensation du BMP280 sont celles de Bosch.


## Dépendances

Que la lib standard Python, sauf [smbus2](https://pypi.org/project/smbus2/) pour le bus I2C sur la Pi (installé dans l'image Docker).

En dev : ruff pour le style.

Côté Docker : l'image `python:3.11-slim` et [willfarrell/autoheal](https://github.com/willfarrell/docker-autoheal).


## Limites

- Une alarme n'est envoyée qu'une fois, au dépassement du seuil. Si cette trame se perd la station sol ne la verra jamais, il faudrait un accusé de réception.
- L'heure des trames est celle de la Pi, qui n'a pas de RTC : si elle n'a pas le réseau au démarrage, l'heure affichée peut être fausse.
- Le MPU-6050 est lu en polling à 20 Hz. Pour aller plus vite sans rater d'échantillons il faudrait passer par sa FIFO ou sa broche d'interruption.


## Docs utilisées

- Datasheet Bosch BMP280 (BST-BMP280-DS001)
- InvenSense, MPU-6000 and MPU-6050 Register Map and Descriptions (RM-MPU-6000A-00)
- Le catalogue CRC de Greg Cook (reveng), pour les paramètres du CRC-16/CCITT-FALSE
