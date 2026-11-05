# B. Stockage et capacité · E. Dimensionnement et montée en charge

> **À lire d'abord.** L'énoncé donne « 120 Go compressés » ; je n'ai pas le détail du scénario (volume moyen, pointe) du wiki. Les hypothèses ci-dessous sont **posées explicitement** (H1 à H6) et **à remplacer** par les chiffres du wiki si elles diffèrent. Tout ce qui est « mesuré » vient du cluster de démonstration (1 NodeManager, images amd64 émulées sur arm64) : ce ne sont **pas** des performances de production.

## Hypothèses

| # | Hypothèse | Valeur | Justification |
|---|---|---|---|
| H1 | Les 120 Go sont le volume **compressé d'une journée** de données (3 flux). | 120 Go/jour | Lecture de l'énoncé ; *à confirmer*. |
| H2 | **Taux de décompression** des CSV gzip. | **×8** (sensibilité ×5 à ×10) | Mesuré sur le jeu fourni : `gzip -6` donne ×6,3 (commandes), ×5,1 (annulations), ×10,3 (consultations), **×9,4 au total**. Le jeu est petit et répétitif ; on retient ×8, un peu en dessous du mesuré, et on montre la sensibilité. |
| H3 | Volume de **pointe** = 2 × volume moyen. | ×2 | Jour de promotion ; hypothèse de travail. |
| H4 | **Durée de conservation des données de travail** : 3 jours (J, J−1 pour le recalcul du lendemain, J−2 de marge). Le brut à 90 jours et le stockage à 2 ans sont hors de ce calcul (section D du sujet). | 3 jours | Les corrections arrivent le lendemain. |
| H5 | **Réplication HDFS** | ×3 | Valeur par défaut, celle du cluster fourni. |
| H6 | **Marge de capacité** : disque utilisé ≤ 70 % | 30 % | HDFS se dégrade quand les disques se remplissent, et il faut de la place pour re-répliquer après une panne. |

## B. Capacité de l'espace de travail HDFS

### Mesures sur le cluster (jeu gonflé ×100, identifiants uniques)

| Zone | Taille | Rapport au brut |
|---|---|---|
| Brut (`/brut`) | 456,7 Mo | 1 |
| Propre (`/propre`, lignes versionnées) | 72,7 Mo | 0,16 |
| Publié (`/publie`) | 73,1 Mo | 0,16 |
| **Total conservé** | 602,5 Mo | **×1,32** |
| Transitoire (`/tmp` pendant le calcul, supprimé après) | ≈ 156 Mo | ≈ 0,34 |

(Le « propre » est petit parce que les consultations — 90 % des octets — n'y passent pas.)

### Calcul

Volume décompressé par jour : `120 Go × 8 = 960 Go` (moyen), `× 2 = 1 920 Go` (pointe).

```
Travail (moyen) = 960 × 1,32 × 3 jours + 960 × 0,34 (transitoire)             ≈ 4,12 To
Travail (pointe) = 2 jours moyens (960 × 1,32 × 2) + 1 jour de pointe
                   (1 920 × 1,32) + transitoire de pointe (1 920 × 0,34)      ≈ 5,70 To
Disque brut = travail × réplication 3 ÷ (1 − 30 % de marge)
   moyen : 4,12 × 3 / 0,70  ≈ 17,7 To
   pointe: 5,70 × 3 / 0,70  ≈ 24,4 To
```

| Taux de décompression | Travail moyen | Travail pointe | **Disque à prévoir (pointe)** |
|---|---|---|---|
| ×5 | 2,6 To | 3,6 To | 15,3 To |
| **×8 (retenu)** | 4,1 To | 5,7 To | **24,4 To** |
| ×10 | 5,2 To | 7,1 To | 30,5 To |

**Lecture** : il faut de l'ordre de **25 To de disque brut** répartis sur les DataNodes pour tenir la pointe avec 3 jours de travail, la réplication et la marge. La réplication multiplie par 3 et la marge par ≈ 1,4 : ce sont les deux facteurs qui pèsent le plus.

**Pourquoi la réplication HDFS ne suffit pas à assurer la persistance après la destruction du cluster** : les 3 réplicas sont dans le même cluster, donc dans les mêmes volumes Docker. `docker compose down -v` détruit d'un coup les volumes du NameNode (qui sait où sont les blocs) et ceux des DataNodes. La réplication protège contre la perte d'*un* DataNode ; elle ne protège ni contre la destruction du cluster, ni contre une fausse manipulation (`hdfs dfs -rm`, qui se réplique aussi), ni contre une corruption logique. Démonstration faite : après `down -v`, HDFS est vide, et seul `persistant/` (hors cluster) permet de tout restaurer (voir `tests_echec.md`, test 6).

**Capacité réelle de la démo** : 82 Go configurés dont 12,7 Go libres au moment des essais (disque de la VM Docker), soit ≈ 4 Go utiles après réplication ×3. Le jeu ×100 (1,4 Go répliqué) était proche de ce que la démo peut accueillir.

## E. Dimensionnement

### Mesures de durée (jeu ×1, ×10, ×100 ; mêmes jobs, mêmes réglages)

| Jeu | Entrée (brut) | Job 1 nettoyage+jointure | Job 2 agrégats | Job 3a consultations | Job 3b top 5 | Somme des jobs | Durée totale du script |
|---|---|---|---|---|---|---|---|
| ×1 | 4,5 Mo | 24 s | 24 s | 27 s | 25 s | 100 s | 180 s |
| ×10 | 45 Mo | 31 s | 25 s | 29 s | 26 s | 111 s | 199 s |
| ×100 | 457 Mo | 30 s | 26 s | 53 s | 26 s | 135 s | 237 s |

Contrôle de justesse : le ×100 donne un net de **38 348 332 €**, soit exactement 100 × 383 483,32 € (identifiants rendus uniques par copie : sans cela, la déduplication aurait supprimé 99 copies sur 100).

**Ce que ça montre** : multiplier le volume par 100 ne multiplie la durée des jobs que par 1,35. Le temps est dominé par un **coût fixe d'environ 25 s par job** (démarrage de l'ApplicationMaster et des conteneurs). Seul le job 3a (le plus gros volume, 407 Mo) sort de ce palier. Le débit « marginal » (octets en plus ÷ secondes en plus) est de l'ordre de **10 à 15 Mo/s** sur ce cluster ; on retient 13 Mo/s. Il est très imprécis : le palier fixe écrase le signal sauf pour le job 3a. Les 100 s restantes de la durée totale ne sont pas du calcul Hadoop : c'est notre script, qui **relit tout le brut sur la machine hôte** pour les contrôles. C'est un goulot qui ne passerait pas à l'échelle (voir limites).

### Calcul de débit

```
Fenêtre : 03h → 06h = 10 800 s ; moins 30 min de marge = 9 000 s utiles
Débit requis (pointe)  = 1 920 Go ÷ 9 000 s ≈ 213 Mo/s
Débit requis (moyen)   =   960 Go ÷ 9 000 s ≈ 107 Mo/s
```

| | Valeur |
|---|---|
| Débit mesuré d'un NodeManager de démo | ≈ 13 Mo/s |
| Volume que la démo traiterait dans la fenêtre | 13 Mo/s × 9 000 s ≈ **117 Go**, soit **≈ 6 %** de la pointe |
| Équivalents « nœud de démo » nécessaires | 213 ÷ 13 ≈ **16** |

Le cluster de démonstration ne tiendrait donc **pas** la pointe de 1,9 To : il en traiterait environ un seizième dans le temps imparti.

### Configuration cible (hypothèse)

| Rôle | Quantité | Dimension | Pourquoi |
|---|---|---|---|
| NameNode (+ standby) | 2 | 16 Go RAM | Métadonnées : ≈ 15 000 blocs de 128 Mo par jour de pointe, soit quelques dizaines de milliers pour 3 jours : négligeable en mémoire. |
| **DataNodes (stockage)** | **6** | 6 To de disque utile chacun (≈ 36 To bruts, pour 24,4 To à prévoir) | Capacité (calcul ci-dessus), avec de la place pour tolérer la perte d'un nœud et re-répliquer. |
| **NodeManagers (calcul)** | **4 à 5** | 16 vCPU / 64 Go chacun | ≈ 16 équivalents-démo (4 vCPU) ⇒ ≈ 64 vCPU ; on arrondit à 4–5 nœuds en tenant compte de la marge ; **estimation très approximative**. |
| ResourceManager | 1 (+ HA) | 8 Go | Ordonnancement. |
| Réseau | 10 Gb/s | | Le shuffle des jobs 1 et 3a traverse tout le jeu ; 213 Mo/s ≈ 1,7 Gb/s en lecture seule, avant shuffle et écritures répliquées. |

Les nœuds de calcul et de stockage sont **séparés**, comme dans le cluster fourni (le NodeManager n'héberge aucun DataNode). Ce choix retire la localité des données : tout passe par le réseau.

### Ajouter des nœuds de calcul ou de stockage : deux décisions différentes

| | Nœud de **calcul** (NodeManager) | Nœud de **stockage** (DataNode) |
|---|---|---|
| **On en ajoute quand…** | Les jobs dépassent la fenêtre : durée de la chaîne > 3 h ; conteneurs en attente dans YARN (mémoire/vCPU saturés) ; tâches `map` nombreuses qui attendent. | Le disque se remplit (> 70 %) ; la durée de conservation ou le volume augmentent ; une re-réplication après panne ne tient plus dans l'espace libre. |
| **Il apporte** | vCPU et mémoire pour exécuter plus de tâches en parallèle. | Capacité disque et débit d'entrées-sorties. |
| **Il ne résout pas** | Un manque d'espace disque. | Un traitement trop lent : plus de disques ne rendent pas les jobs plus rapides si le CPU est saturé. |
| **Effet sur la réplication** | Aucun. | Augmente la capacité utile (÷ 3) et la tolérance aux pannes. |

Les deux n'évoluent pas ensemble : la capacité dépend de la durée de conservation et de la réplication, le calcul dépend du débit à tenir dans la fenêtre. Un volume deux fois plus grand sur la même fenêtre demande **deux fois plus de calcul** *et* **deux fois plus de stockage** ; mais une conservation deux fois plus longue demande **seulement plus de stockage**.

### Indicateurs à surveiller

- **Durée de la chaîne** (somme des jobs + contrôles) comparée à la fenêtre ; alerte à 05h00 (déjà prévue).
- **YARN** : mémoire et vCPU alloués vs disponibles ; applications en attente ; durée de chaque job.
- **Skew** : écart entre durée du reducer le plus lent et la médiane.
- **HDFS** : % de disque utilisé par DataNode, `Under replicated blocks`, `Missing blocks`, nombre de DataNodes vivants.
- **NameNode** : mémoire (nombre d'objets), nombre de petits fichiers.
- **Qualité** : taux de rejets (seuil 5 %), anomalies bloquantes, orphelines en attente.

### Limites qui apparaissent quand le volume augmente

1. **Clé déséquilibrée (job 3a).** Le produit P00108 pèse **10,8 %** des consultations distinctes (4 325 sur 40 066 ; le deuxième produit de sa catégorie en a 377). Une clé ne se découpe pas : un seul reducer reçoit toute cette part, donc l'accélération maximale par ajout de reducers est plafonnée à ≈ **×9,3** (1 ÷ 0,108), quel que soit leur nombre. C'est pourquoi on regroupe par (catégorie, produit) et non par catégorie. Remède possible : un combiner qui pré-agrège côté mapper, ou « saler » la clé.
2. **Jointure (job 1).** Tout le jeu traverse le shuffle. Le déséquilibre est faible sur la clé `(commande_id, ligne_id)` : au plus 3 lignes par clé dans les données fournies. Il serait fort si on joignait sur la catégorie ou sur un client très actif.
3. **NameNode et petits fichiers.** Chaque fichier ou bloc coûte de la mémoire au NameNode. Nous produisons peu de fichiers par jour (2 par job), mais publier un fichier par version et par jour pendant 2 ans en produirait des milliers de petits : à regrouper.
4. **Entrées-sorties disque et réseau.** Chaque octet de brut est lu, shufflé, puis écrit ×3 (réplication) ; les écritures répliquées traversent le réseau. Sur la démo, 1 NodeManager et tout dans un même disque virtuel : la contention est certaine.
5. **Notre script d'orchestration.** L'étape de contrôle rapatrie tout le brut sur la machine qui lance le script (ici via `docker exec`). C'est ce qui fait passer la durée totale de 135 s (jobs) à 237 s au ×100, et ça ne passerait pas à 2 To. À terme, les compteurs d'entrée devraient être calculés dans les jobs (compteurs Hadoop), pas en relisant le brut.
6. **Client Streaming fragile** (observé) : sans JobHistory Server MapReduce, il peut déclarer un échec après un job réussi ; on s'appuie sur `_SUCCESS` (décision T12).
7. **Panne d'un DataNode** (observée) : la réplication préserve les données, mais le traitement peut échouer pendant la fenêtre où le NameNode n'a pas encore constaté la panne (voir `tests_echec.md`, test 5).

### Pourquoi l'extrapolation depuis le jeu réduit reste approximative

- **Palier fixe dominant** : à 4–457 Mo, 25 s de démarrage par job écrasent le temps de calcul ; le débit « marginal » de 13 Mo/s est estimé sur un très petit écart de durée.
- **Cluster non représentatif** : 1 NodeManager, calcul et stockage séparés, tout sur un seul disque virtuel, images amd64 émulées sur arm64 (durées pessimistes, dans une proportion que nous ne connaissons pas).
- **Données dupliquées** : le jeu gonflé répète 100 fois les mêmes distributions. Même répartition des produits, donc même skew, mêmes taux d'anomalies ; la compression, la mémoire des reducers (ensembles de sessions distinctes) et la localité n'ont pas la même allure sur des données réelles.
- **Un seul point mesuré qui dépasse le palier** (job 3a) : une droite tracée sur trois points serait trompeuse.
- **La relation n'est pas linéaire** à grande échelle : shuffle, spill sur disque, mémoire des reducers et réseau introduisent des seuils qu'on n'a pas atteints.

Ce document donne donc un **ordre de grandeur** et une méthode ; il ne remplace pas un essai à l'échelle sur l'infrastructure cible.
