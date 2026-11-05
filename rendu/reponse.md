### 1 - Sans IA : lire le cas, explorer les données, relever les ambiguïtés et formuler les hypothèses.

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

