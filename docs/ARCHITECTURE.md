# Architecture

## En gros

Le code est découpé en couches, le schéma et le trajet d'une mesure sont dans `docs/architecture.pdf`.

Chaque couche ne dépend que de celle d'en dessous :

- les drivers parlent à un `BusI2C` (`lire_octet`, `lire_bloc`, `ecrire_octet`) sans savoir comment le bus est géré derrière
- `protocol/` transforme les objets de `models.py` en octets, il ne connaît ni les capteurs ni le réseau
- `transport/` envoie juste des octets. Pour passer en liaison série au lieu d'UDP il n'y aurait que ce module à changer

## La boucle principale

Tout tourne dans un seul thread. `Passerelle.executer()` fait à peu près :

```
tant qu'on n'a pas demandé l'arrêt :
    delai = ordonnanceur.executer_en_attente()  # lance les tâches dues
    signal_vie.signaler()                       # pour le healthcheck
    arret.wait(delai)                           # attend la prochaine tâche
```

Les tâches :

- lecture BMP280 toutes les 0,5 s
- lecture MPU-6050 toutes les 50 ms
- trame SANTE toutes les 5 s

(les périodes se règlent dans `config/gateway.toml`)

Pas de thread par capteur : ils sont sur le même bus I2C, il aurait fallu un verrou et ça complique pour rien. Une lecture I2C prend quelques ms, une seule boucle tient largement 20 Hz + 2 Hz.

`arret.wait()` plutôt que `time.sleep()` : quand `docker stop` envoie SIGTERM la boucle se réveille tout de suite, et on ferme proprement la socket et le bus.

## Les pannes

Chaque capteur a un état : OK, DEGRADE ou EN_PANNE (voir `core/health.py`).

- **Une erreur I2C** : le capteur passe DEGRADE et on saute la mesure. Si la lecture suivante marche il repasse OK.
- **Plusieurs erreurs d'affilée** (3 par défaut, en général un capteur débranché) : il passe EN_PANNE et on envoie `CAPTEUR_EN_PANNE`. Ensuite on retente l'init, d'abord après 2 s puis en doublant à chaque échec jusqu'à 30 s, pour pas saturer le bus.
- **Capteur rebranché** : l'init passe, alarme `CAPTEUR_RETABLI`, et ça repart.
- **Valeur aberrante** (hors des plages de la datasheet) : comptée comme une erreur de lecture.
- **Réseau coupé** : la socket UDP est non bloquante, l'envoi échoue, on compte l'erreur et l'acquisition continue.
- **Station sol éteinte** : la plupart du temps la Pi ne voit même pas d'erreur, les trames se perdent et rien ne bloque.
- **Crash** : Docker relance (`restart: unless-stopped`).
- **Programme bloqué sans crash** : le fichier de signal de vie n'est plus touché, le HEALTHCHECK passe le conteneur `unhealthy` et autoheal le redémarre.

## Pourquoi ces choix

### UDP et pas TCP

Les mesures arrivent en continu, une mesure perdue est remplacée 50 ms après. En TCP on retransmettrait des valeurs déjà périmées, et si la station sol ne répond plus l'envoi peut bloquer, donc l'acquisition avec. En UDP on perd des trames mais on le voit avec le numéro de séquence.

### Un CRC16 en plus du checksum UDP

Le checksum UDP est optionnel en IPv4 et c'est une simple somme, il laisse passer certaines erreurs. Le CRC-16/CCITT détecte toutes les erreurs d'un bit et toutes les rafales de 16 bits ou moins. Et comme il est dans notre trame, il reste valable si on change de transport.

### Formules du BMP280 en flottant

La datasheet donne la compensation en entiers (pour les micros sans FPU) et en double. La Pi a une FPU, on a pris la version flottante, plus lisible.

### Registres lus d'un coup

Les 6 octets de mesure du BMP280 (à partir de 0xF7) et les 14 du MPU-6050 (à partir de 0x3B) sont lus en une seule transaction I2C. Tous les octets viennent du même échantillon, et c'est plus rapide que registre par registre.
