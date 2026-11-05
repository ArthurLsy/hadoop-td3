## 1 - Sans IA : lire le cas, explorer les données, relever les ambiguïtés et formuler les hypothèses.

Doublons repéré avec : sort annulations_20261115.csv | uniq -d

    Annulations : ANN0195835, ANN0195943, ANN0196521, ANN0196916, ANN0197545, ANN0197593, ANN0197646, ANN0197781
    Commandes

Anomalies : 
    Montant_rembourse = abc, N/A ou des int alors que la pluart sont des float
    ANN0197449	CMD1074085	1	ANNULATION	paiement_modifie	1	abc	2026-11-15 14:20:55	
    ANN0195939	CMD1075187	1	RETOUR	taille_inadaptee	1	N/A	2026-11-15 18:54:40	

    Décalage des colonnes dès qu'il y a un int  dans montant_rembourse
    ANN0196219	CMD1075047	2	RETOUR	colis_endommage	1	11	95	2026-11-15 18:18:43

    Décalage des colonnes
    CMD1073139	2	CL004184	P00106	electromenager	2	35	99	EUR	PAYEE	2026-11-15 3:26:05

    'hier' au lieu d'un dateTime
    CMD1073081	4	CL004265	P00178	jardin	1	22.99	EUR	PAYEE	hier

    colonnes vident ici "client_id"
    S00153786		P00111	electromenager	https://www.marcheplus.example/produit/P00111	2026-11-15 7:23:22

    o à la palce d'un O

#### Ambiguités du sujet

    Les fichiers de correction doivent modifier les donées déja agrégé ? 
        Ne touche pas a la version original. Jointure des corrections aux commandes

    Que faire des annulations qui ne correspondnent a aucune commande ?
    Commande annulé après la cloture de la journée ?
        on garde les anulations orphlines de coté et a chaque "jet" on les reparcours

    Remboursement d'annulation supérieur au montant de la commande


    Lignes de commande statut annulé : 
    Des ligne de commandes sont au statut annulé quand elles arrivent mais une annulation est aussi lié a cette ligne donc pour calculele CA etc soit 
    on retire la ligne de la commande, soit on applique la modifications via l'annulations. --> Option 2


    
## Archi Hadoop
    Ce que fournit le compose
        - HDFS: 1 NameNode (namenode) et 3 DataNodes. Facteur de réplication 3 (le défaut), blocs de 128 Mo. Les permissions HDFS sont désactivées (dfs.permissions.enabled=false).
        - YARN: 1 ResourceManager, 1 seul NodeManager (service nodemanager1, conteneur nodemanager) et le History Server. Le NodeManager dispose de 6 Go et 4 vCPU. Chaque tâche map ou reduce et  l'ApplicationMaster prennent 1 Go, et le maximum par conteneur est 4 Go.
        - Hive: hive-server sur le port 10000, hive-metastore et un PostgreSQL pour les métadonnées.
        - Volumes: un volume Docker par composant (NameNode, 3 DataNodes, History Server, metastore). ./persistant est monté sur /persistant, uniquement dans namenode.
        - Python 3.11: le Dockerfile l'ajoute au NameNode et au NodeManager, pas aux DataNodes. Nos mappers et reducers s'exécutent sur le NodeManager, donc c'est suffisant. Ils n'utilisent que la bibliothèque standard.

## Schéma

    - Stockage et calcul sont séparés: le NodeManager n'héberge aucun DataNode. Les jobs lisent HDFS par le réseau.
    - Cycle d'un lot: sources → /brut → Job 1 (nettoyage et jointure) → /propre → Job 2 (agrégats) → /tmp → contrôles → /publie + marqueur → copie dans persistant/.
    - Publiable: seul un résultat qui a passé les contrôles est renommé vers /publie. Sinon il reste en /tmp et une anomalie est remontée.
    - Persistance: persistant/ est le seul élément hors cluster. Après docker compose down -v, on recharge /publie depuis lui.
    - Hive est optionnel: il sert à interroger /publie avec des tables externes.
