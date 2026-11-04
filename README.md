# Projet Hadoop MarchéPlus : fichiers fournis

Ce dépôt contient les fichiers de départ du projet. **Le sujet est sur le wiki :**
<https://slamwiki2.kobject.net/eadl/bloc5/fm3/td3>

## Contenu

| Dossier | Contenu |
|---|---|
| `donnees/` | Le jeu de données réduit de la journée du 15 novembre 2026 : commandes, consultations, annulations et lot correctif |
| `environnement/` | Le cluster Hadoop sur Docker Compose : HDFS, YARN, Hive et Python 3. Son fonctionnement est décrit dans [`environnement/README.md`](environnement/README.md) |

Ne modifiez pas les fichiers de `donnees/` : vos résultats doivent être calculés sur le jeu
fourni. Pour vos tests, travaillez sur des copies.

## Prérequis

- Docker avec Docker Compose v2 (`docker compose version`)
- Git
- De la mémoire pour Docker : le cluster réserve jusqu'à 6 Go aux tâches YARN, en plus de
  ses services. Sous Windows et macOS, allouez à Docker au moins 10 Go si possible.

## Démarrage rapide

```bash
git clone https://github.com/supavenir/hadoop-td3
cd hadoop-td3/environnement
docker compose up -d --build
```

Le premier lancement télécharge les images et Python : faites-le avant la séance si possible.

Vérifiez que HDFS est prêt (la commande doit afficher `Live datanodes (3)`) :

```bash
docker exec namenode hdfs dfsadmin -report
```

La suite (interfaces web, chargement des données dans HDFS, Streaming, Hive, dossier
`persistant/`, arrêt du cluster) est dans [`environnement/README.md`](environnement/README.md).

## Si un autre cluster tourne déjà

Les noms de conteneurs et les ports sont les mêmes que ceux du TD1. Arrêtez l'ancien cluster
depuis son propre dossier avec `docker compose down` avant de lancer celui-ci.
