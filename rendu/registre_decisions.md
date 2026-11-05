# Registre des décisions

Chaque décision est numérotée, avec ce qui a été retenu, ce qu'on a écarté et pourquoi. Les décisions « métier » ont été validées par l'équipe ; les décisions « technique » ont été prises pendant l'implémentation et sont marquées *(à valider)* quand elles méritent un avis.

## A. Règles métier

| # | Décision | Alternative écartée | Raison |
|---|---|---|---|
| M1 | **Montant d'une ligne = `quantite × prix_unitaire`**. CA brut = somme sur les lignes valides. | — | Seule définition possible avec les colonnes fournies. |
| M2 | **CA net = CA brut − annulations/retours rattachés** (somme de `montant_rembourse`). | — | Définition du besoin métier. |
| M3 | **Clé de jointure = `(commande_id, ligne_id)`**. Une annulation est orpheline si cette clé n'existe pas, même si la commande existe (ex. CMD1074687 ligne 5 pour une commande de 4 lignes). | Joindre sur `commande_id` seul | Un `commande_id` seul rattacherait un remboursement à la mauvaise catégorie (une commande peut avoir plusieurs catégories). |
| M4 | **Lignes au statut `ANNULEE` : option 1.** La ligne reste dans le CA brut et son annulation est déduite normalement. On ne filtre pas sur le statut. | Option 2 : exclure la ligne du brut et ignorer l'annulation | Fidélité à la donnée brute, traçabilité. Le **net est identique** dans les deux options (vérifié sur l'extrait : mode = 56,58). |
| M5 | **Nombre de commandes par catégorie = `commande_id` distincts.** Une commande multi-catégories compte dans chacune ; la somme par catégorie peut donc dépasser le nombre de commandes uniques. | Compter les lignes | Le besoin demande un nombre de *commandes*. |
| M6 | **Plusieurs annulations sur la même ligne** (ids distincts) : elles s'additionnent, dans l'ordre de `annulation_id`, tant que le cumul reste ≤ au montant de la ligne. | — | Ex. CMD1075106 ligne 1 : deux retours d'une unité = 259,80. |
| M7 | **Remboursement supérieur au montant de la ligne** : l'annulation fautive est **rejetée** (non déduite) et signalée dans les anomalies. | La déduire quand même (net négatif possible) | Décision d'équipe. 13 cas sur le jeu fourni. |
| M8 | **Quantité annulée supérieure à la quantité commandée** : anomalie **bloquante**, aucune publication. | Simple avertissement | Décision d'équipe : cette incohérence remet en cause la fiabilité du lot. Sur le jeu fourni, elle ne se déclenche pas (les cas apparents sont déjà rejetés par M7) ; le blocage a été vérifié sur un jeu de test. |
| M9 | **Devise ≠ EUR (CHF, 42 lignes) : ligne rejetée** et signalée. | Convertir avec un taux | Aucun taux de change fourni ; en inventer un fausserait le CA. |
| M10 | **Date invalide (`hier`…) : ligne rejetée** et signalée. Formats acceptés : `YYYY-MM-DDTHH:MM:SS`, `YYYY-MM-DD HH:MM:SS`, `DD/MM/YYYY HH:MM` (heures sans zéro initial acceptées). | Garder la ligne : la date n'entre pas dans le calcul | Décision d'équipe : donnée non fiable → à examiner. **Coût connu** : du CA réel est écarté (13 lignes de commandes). |
| M11 | **Montant de remboursement invalide** (`abc`, `N/A`, négatif) : annulation rejetée. | Déduire le prix de la ligne | Ne pas deviner un montant. |
| M12 | **Quantité ou prix non numérique, nul ou négatif : ligne rejetée.** Catégorie vide : rejet. Statut inconnu : rejet. | — | Valeurs inexploitables. |
| M13 | **Catégories normalisées en minuscules** (`Electromenager` → `electromenager`). | Rejeter | Simple casse, le sens est évident. |
| M14 | **Virgule décimale réparée** : `35,99` éclate en deux champs ; on les recolle si les deux sont numériques et si cela redonne le bon nombre de colonnes. | Rejeter ces lignes | *(Hypothèse : non confirmée par la source.)* 5 commandes et 3 annulations concernées. Si l'hypothèse est fausse, le CA est faussé de quelques lignes seulement. |
| M15 | **Doublons exacts : un seul exemplaire conservé**, les autres comptés en anomalie `DOUBLON`. Deux annulations de même `annulation_id` qui ne diffèrent que par le format (`15.90` / `15.900`, casse du motif) sont considérées identiques **après normalisation**. | Garder tous les exemplaires | Un remboursement ne se compte pas deux fois. |
| M16 | **Même `(commande_id, ligne_id)` avec des contenus différents : toutes les versions sont rejetées** et signalées ; les annulations de cette clé deviennent orphelines. | Garder la première / la dernière | Décision d'équipe : on ne sait pas laquelle est juste. 10 cas (20 lignes rejetées) sur le jeu fourni. |
| M17 | **Corrections** : l'original n'est jamais modifié. Il est la version 1 ; chaque correction appliquée (triée par `horodatage_correction` puis `correction_id`) crée une version suivante. Les agrégats lisent la **dernière version**. `AJOUT` crée la ligne ; `MODIFICATION` la remplace ; `SUPPRESSION` la retire. | Écraser la ligne | Reprise/recalcul sans perte, audit possible (`versions_et_lignes.tsv`). |
| M18 | **Correction sans ligne à corriger** (`MODIFICATION`/`SUPPRESSION` sur une clé inexistante) : signalée `CORRORPH`, non appliquée (9 cas). **`AJOUT` sur une ligne qui existe déjà** : appliqué comme remplacement, avec une `ALERTE`. | Rejeter | Une correction n'est jamais perdue en silence. |
| M19 | **Orphelines : règle des 3 flux = 3 lots.** Le compteur d'une orpheline est le nombre de **lots distincts** où elle reste orpheline : rejouer un même lot ne l'incrémente pas (idempotent). À 3 : rejet (`ORPHELINE_EXPIREE` dans les anomalies). | Compter les exécutions | Une relance technique ne doit pas « user » les orphelines. |
| M20 | **Consultations** : une consultation identique (même session, même produit, même horodatage) n'est comptée qu'une fois (200 doublons). `client_id` vide toléré (inutile pour le top 5). Catégorie en minuscules, vide → rejet. Top 5 : égalité départagée par `produit_id` croissant. | — | Un rechargement de page n'est pas une nouvelle consultation. |
| M21 | **Un produit peut apparaître dans deux catégories** du top 5 : la catégorie retenue est celle de la ligne de consultation. 7 produits concernés (ex. P00223 : sport 1 096 vues, beaute 25). | Rattacher chaque produit à sa catégorie majoritaire | Choix le plus simple ; les lignes minoritaires sont du bruit (≈ 25 vues) qui n'atteint pas le top 5 dans le jeu fourni. *(À reconsidérer sur un jeu plus bruité.)* |

## B. Décisions techniques

| # | Décision | Alternative écartée | Raison |
|---|---|---|---|
| T1 | **Nettoyage en MapReduce Streaming (Python)**, obligatoire dans le sujet. | Hive | Exigé ; permet aussi de produire des rejets avec leur raison. |
| T2 | **Jointure côté reducer** : le mapper émet la clé `(commande_id, ligne_id)` avec un tag (`C` commande, `A` annulation, `K` correction) ; le reducer reçoit tout ce qui concerne une ligne. | `JOIN` Hive ; jointure en mémoire côté mapper (map-side) | Même passe que le nettoyage, le versionnement et les contrôles par ligne (doublons, quantités, cumul des remboursements) qui demandent d'avoir toutes les lignes d'une clé ensemble. **Coût** : tout le jeu traverse le shuffle. **Risque d'asymétrie** : faible sur cette clé (≤ quelques lignes par clé), contrairement au top 5 (voir T4). |
| T3 | **Quatre jobs** : (1) nettoyage + jointure + versions, (2) agrégats par catégorie, (3a) consultations par (catégorie, produit), (3b) top 5. | Un seul job | Chaque job a une clé de regroupement différente. |
| T4 | **Top 5 en deux jobs**, sans combiner la clé catégorie dès le départ. | Un job clé = catégorie | Une clé = catégorie concentrerait tout le trafic d'une catégorie dans un seul reducer (P00108 = 4 325 vues contre 377 pour le deuxième produit de sa catégorie). Le job 3a répartit par (catégorie, produit). |
| T5 | **Nombre de reducers : 2** pour les jobs 1 et 3a, **1** pour 2 et 3b. | Plus | Le cluster n'a qu'un NodeManager (6 Go) ; plus de reducers ne ferait que se concurrencer. |
| T6 | **Hive non utilisé** pour le résultat. | Tables Hive sur `/publie` | Les résultats sont de petits fichiers TSV déjà consultables ; Hive n'apporterait rien au besoin. Le service reste disponible dans le cluster. |
| T7 | **Zones HDFS** : `/marcheplus/brut`, `/propre`, `/tmp`, `/publie`, `/echecs`, partitionnées par `jour=` (et `lot=`/`v=`). | — | Une zone = un niveau de confiance. |
| T8 | **Brut immuable** : un lot déjà déposé n'est jamais réécrit ; le redéposer à l'identique est accepté (rejeu), avec un contenu différent il est **refusé** (code 4). | Écraser | Le brut sert de preuve et de base de recalcul. |
| T9 | **Publication atomique** : les résultats sont écrits dans `/tmp/.../run=<horodatage>`, contrôlés, puis le dossier est **renommé** en `/publie/jour=J/v=N`. Le marqueur `_VALIDE` est écrit *avant* le renommage, donc il apparaît avec le dossier. Un fichier `COURANT` désigne la version officielle. | Écrire directement dans `/publie` | Un lecteur ne voit jamais un dossier à moitié écrit. |
| T10 | **Seuil de rejets : 5 %** par flux. Observé : 1,9 % (commerce), 0,13 % (consultations). | — | Seuil arbitraire *(à valider avec le métier)* ; assez large pour le jeu fourni, assez bas pour attraper un fichier corrompu (testé à 20 %). |
| T11 | **Rejeu identique** : si le résultat est identique à la dernière version publiée, **aucune nouvelle version** n'est créée. | Toujours créer une version | Évite d'inventer des versions quand rien n'a changé. |
| T12 | **Un job est réussi si `_SUCCESS` existe** dans son dossier de sortie, même si le client Streaming a échoué. | Se fier au code retour du client | Constaté : sans JobHistory Server MapReduce dans ce cluster, le client peut échouer (« endpoint configuration is wrong ») *après* la fin réussie du job. `_SUCCESS` n'est écrit que si le job a réussi ; un job tué n'en a pas (testé). |
| T13 | **Lectures HDFS avec reprises** (8 essais) et erreur explicite si elles échouent. | Lecture simple | Constaté : avec un DataNode arrêté mais encore « vivant » pour le NameNode, une lecture sur deux échoue (`UnresolvedAddressException`). Une lecture ratée ne doit jamais être prise pour un fichier modifié. |
| T14 | **Persistance** : après publication, la version, le brut du lot, `COURANT` et l'état des orphelines sont copiés dans `persistant/` ; `restore.sh` les remet dans HDFS en vérifiant chaque fichier par md5. | Copier seulement les résultats | Sans le brut, impossible de recalculer. |
| T15 | **Pas de Spark, pas d'AWS** (contraintes du sujet). | — | — |

## C. Limites connues (non traitées)

- **Dates** : on vérifie qu'elles sont lisibles, pas qu'elles appartiennent bien au 15/11/2026.
- **Devise** : seules les lignes en EUR sont prises en compte (M9).
- **Hypothèse M14** (virgule décimale) non confirmée par la source.
- **Doublons de commandes avec contenus différents** (M16) : on perd les deux versions, sans règle pour trancher.
- **Catégorie des produits** consultés/commandés non unique (M21).
- **Aucun contrôle de cohérence entre `url` et `produit_id`** dans les consultations.
- **Cluster de démonstration** : un seul NodeManager, images amd64 émulées sur machine arm64. Les durées mesurées ne sont pas transposables à une infrastructure de production.
