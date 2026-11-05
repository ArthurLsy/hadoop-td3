#!/usr/bin/env python3
"""Fabrique un jeu volumineux en dupliquant les CSV fournis (palier 3 : mesures de durée/débit uniquement).

Chaque copie k reçoit des identifiants UNIQUES (id + k * 10 000 000) pour CMD..., ANN..., S..., COR... :
sans cela, chaque copie serait un doublon exact de la précédente et la déduplication les supprimerait.
Les anomalies (virgules décimales, 'abc', dates invalides...) sont dupliquées telles quelles.
Les produits et catégories ne changent pas : le déséquilibre de clés (ex. P00108) est multiplié par N.
Usage : gonfler.py FACTEUR DOSSIER_ENTREE DOSSIER_SORTIE
"""
import os
import re
import sys

PAS = 10_000_000
RE = {p: re.compile(r"^(%s)(\d+)$" % p) for p in ("CMD", "ANN", "S", "COR")}
# colonnes à décaler selon le fichier : (index, préfixe)
COLONNES = {
    "commandes": [(0, "CMD")],
    "annulations": [(0, "ANN"), (1, "CMD")],
    "consultations": [(0, "S")],
    "corrections": [(0, "CMD"), (11, "COR")],
}


def decaler(champs, regles, k):
    for idx, pref in regles:
        if idx < len(champs):
            m = RE[pref].match(champs[idx])
            if m:
                champs[idx] = "%s%d" % (m.group(1), int(m.group(2)) + k * PAS)
    return champs


def main():
    facteur, entree, sortie = int(sys.argv[1]), sys.argv[2], sys.argv[3]
    os.makedirs(sortie, exist_ok=True)
    for nom in sorted(os.listdir(entree)):
        if not nom.endswith(".csv"):
            continue
        flux = nom.split("_")[0]
        regles = COLONNES[flux]
        with open(os.path.join(entree, nom), encoding="utf-8") as f:
            lignes = [l.rstrip("\r\n") for l in f if l.strip()]
        entete, corps = lignes[0], lignes[1:]
        with open(os.path.join(sortie, nom), "w", encoding="utf-8") as out:
            out.write(entete + "\n")
            for k in range(facteur):
                for l in corps:
                    out.write(",".join(decaler(l.split(","), regles, k)) + "\n")
        print("%s : %d lignes x %d = %d" % (nom, len(corps), facteur, len(corps) * facteur))


if __name__ == "__main__":
    main()
