# D. Tests d'échec et de reprise (observations réelles)

Tous les tests ci-dessous ont été exécutés sur le cluster Docker du projet avec `src/pipeline.sh`. Les jours `2026119x` sont des jours fictifs de test, supprimés ensuite ; le vrai jour est `20261115`.

Codes de sortie de `pipeline.sh` : **0** publié · **2** publication bloquée par les contrôles · **3** flux manquant/vide · **4** brut déjà présent mais différent · **1** échec technique (rien de publié).

## 1. Flux manquant ou vide — code 3

```
$ ./pipeline.sh 20261199 1 commandes.csv annulations.csv          # pas de consultations
FLUX MANQUANT : consultations_* (obligatoire pour le lot 1) -> aucune publication     (exit 3)

$ ./pipeline.sh 20261199 1 commandes.csv annulations.csv consultations_vide.csv
FLUX MANQUANT OU VIDE : …/consultations_vide.csv -> aucune publication                 (exit 3)
```
Le contrôle a lieu **avant tout dépôt** : rien n'est écrit dans HDFS.

## 2. Brut déjà déposé mais différent — code 4

On rejoue le lot 1 du `20261115` avec un fichier de commandes tronqué à 100 lignes :
```
BRUT IMMUABLE : commandes_20261115.csv existe déjà dans /marcheplus/brut/jour=20261115/lot=1
avec un contenu différent -> refus                                                      (exit 4)
```
Le brut déjà en place n'est pas modifié.

## 3. Fichier d'entrée corrompu — code 2

Une ligne sur cinq du fichier de commandes est abîmée (colonnes tronquées, valeur illisible). Le pipeline va jusqu'au bout des jobs, puis les contrôles bloquent :
```
OK      commerce_entree_egale_sorties : entrée=8607 ; VERSION=6314 + … + REJ=1745 = 8607
ECHEC   taux_rejets_commerce : 20.27 % (seuil 5 %)
=> PUBLICATION BLOQUEE                                                                  (exit 2)
```
- `/marcheplus/publie` ne contient toujours que `jour=20261115` : **rien n'a été publié** pour le jour corrompu.
- Les sorties sont rangées dans `/marcheplus/echecs/jour=20261198/run=…` (CA calculé, anomalies, rapport JSON) pour examen.
- Le net était pourtant calculable et cohérent (306 733,93 €) : la cohérence arithmétique seule ne suffit pas, d'où le contrôle du taux de rejets.

## 4. Job tué en cours de route (`yarn application -kill`) — code 1

On lance le pipeline sur le jeu complet, on attend que le job 1 tourne (35 %), puis :
```
$ yarn application -kill application_1793885121558_0017
Killed application application_1793885121558_0017
…
Job … failed with state KILLED due to: Application … was killed by user root
JOB job1_nettoyage_jointure EN ECHEC (pas de _SUCCESS dans …/job1)                      (exit 1)
```
- État YARN final : `State : KILLED`, `Final-State : KILLED`.
- **Rien n'est publié.** Le dossier `/marcheplus/tmp/jour=20261197/run=…/job1/_temporary` reste (sortie partielle), séparé de la zone officielle.
- Relancer ensuite le même lot fonctionne : le brut déjà déposé est reconnu identique, une nouvelle exécution `run=…` repart de zéro.

## 5. Arrêt d'un DataNode (`docker compose stop datanode1`)

C'est le test qui a révélé le plus de choses, dont **un défaut de notre propre script**.

**5a. Arrêt pendant un job — le job réussit, mais notre script l'a cru en échec.**
Le job 1 s'est terminé en `FinalApplicationStatus=SUCCEEDED` alors que `datanode1` était arrêté (la réplication ×3 l'a absorbé). Pourtant le pipeline a signalé un échec : le client Streaming est resté bloqué environ une minute, puis a tenté de lire le statut final auprès d'un JobHistory Server MapReduce (`0.0.0.0:10020`) qui **n'existe pas** dans ce compose :
```
ERROR streaming.StreamJob: Error Launching job : java.net.ConnectException: Your endpoint configuration is wrong
```
Correction (décision T12) : un job est considéré réussi si son dossier de sortie contient `_SUCCESS`, que HDFS n'écrit qu'en cas de réussite. Un job tué n'en a pas (test 4).

**5b. DataNode arrêté mais encore « vivant » pour le NameNode — lectures et écritures intermittentes en échec.**
`hdfs dfs -cat` d'un même fichier, 4 essais de suite, `datanode1` arrêté :
```
essai 1 : rc=0    md5 correct
essai 2 : rc=0    md5 correct
essai 3 : rc=255  -cat: Null exception message — java.nio.channels.UnresolvedAddressException
essai 4 : rc=255  (idem)
```
Le NameNode continue de proposer `datanode1` comme source (il ne le déclare mort qu'après plusieurs minutes sans battement de cœur), le nom du conteneur arrêté n'est plus résolu, et le client HDFS **ne bascule pas** sur un autre réplica pour ce type d'erreur. Conséquences observées :

- notre vérification de brut a lu un fichier vide et déclaré « contenu différent » (faux) → les lectures sont maintenant réessayées (T13) et une erreur de lecture est signalée comme telle ;
- le lancement d'un job a échoué à l'écriture de ses fichiers de travail (`DataStreamer Exception … UnresolvedAddressException`) → `exit 1`, **rien de publié**.

`hdfs dfsadmin -report` indiquait en même temps `Under replicated blocks: 4` et `Live datanodes (3)` : le NameNode n'avait pas encore constaté la panne.

**5c. Reprise.** `docker compose start datanode1`, puis relance du même lot : les quatre jobs passent, contrôles OK, publication normale.

*Non observé* : l'instant où le NameNode déclare le DataNode mort et ré-réplique ses blocs (délai par défaut de l'ordre de 10 minutes) ; nous n'avons pas attendu.

**Leçon pour la section E** : avec trois DataNodes et une réplication ×3, la panne d'un seul DataNode ne fait pas perdre de données, mais elle peut **interrompre le traitement** pendant la fenêtre où le NameNode ne l'a pas encore détectée. Dans la fenêtre 03h–6h, il faut prévoir une reprise automatique (relancer le lot) plutôt que supposer que la réplication suffit.

## 6. Destruction du cluster (`docker compose down -v`) puis restauration

Avant : `v=1` (empreinte `b51bc0e1…`) et `v=2` (`65a20acb…`) publiés pour `20261115`, copiés dans `persistant/`.
```
$ docker compose down -v       # conteneurs ET volumes (HDFS, Hive, History Server) supprimés
$ docker compose up -d         # cluster neuf, 3 DataNodes
$ hdfs dfs -ls /marcheplus     # ls: `/marcheplus': No such file or directory   <- HDFS vide
$ ./restore.sh
== Restauration depuis /persistant
19 fichiers vérifiés, 0 écart(s)
OK  restauration identique
version courante de jour=20261115 : v=2
```
Les empreintes de `ca_par_categorie.tsv` des deux versions sont identiques avant destruction et après restauration.

*Découverte pendant ce test* : une première version de `restore.sh` annonçait « 1 fichier vérifié » au lieu de 19, parce que `docker exec -i` consommait l'entrée de la boucle. Corrigé (`< /dev/null`), puis re-vérifié.

## 7. Lot correctif du lendemain

Le lot 2 (`corrections_20261115.csv`, 67 lignes) crée des versions de lignes sans toucher aux originaux :

| | v=1 (lot 1) | v=2 (lot 1 + corrections) |
|---|---|---|
| Versions de lignes (originales + corrections appliquées) | 7 879 | 7 935 (+56 corrections appliquées) |
| Corrections sans ligne à corriger (`CORRORPH`) | — | 9 |
| Corrections en double (`DOUBLON`) | — | 2 (56 + 9 + 2 = 67 lignes de corrections) |
| Annulations rattachées / orphelines | 466 / 20 | 470 / 16 (4 lignes créées par `AJOUT`) |
| Net total | 383 483,32 € | 384 263,23 € |

`v=1` reste consultable ; `COURANT` pointe sur `v=2`.

## 8. Rejeu d'un lot — résultat identique

On rejoue le lot 2 du `20261115` (déjà publié en `v=2`) :
```
lot déjà déposé à l'identique : rejeu, le brut n'est pas réécrit
job job1 … job2 … job3a … job3b …            # les quatre jobs sont recalculés
=> PUBLIABLE
RESULTAT IDENTIQUE à v=2 : aucune nouvelle version publiée (rejeu idempotent).      (exit 0)
```
`/marcheplus/publie/jour=20261115` ne contient toujours que `v=1`, `v=2` et `COURANT` : pas de `v=3`.

## Ce qui n'a pas été testé

- Un échec **entre** le renommage vers `/propre` et le renommage vers `/publie`. La publication fait deux renommages HDFS, chacun atomique mais pas l'ensemble. Un arrêt entre les deux laisserait un `/propre/jour=J/v=N` sans version publiée ; le script supprime ce reliquat avant de republier la version `N`, mais **ce chemin n'a pas été exercé**.
- La purge à 90 jours du brut (non automatisée).
- Le moment où le NameNode déclare un DataNode mort (test 5).
