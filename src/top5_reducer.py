#!/usr/bin/env python3
"""Job 3b - reducer : 5 produits les plus consultés par catégorie (égalité : produit_id croissant)."""
import sys


def sortie(cat, produits):
    for rang, (prod, nb) in enumerate(sorted(produits, key=lambda x: (-x[1], x[0]))[:5], 1):
        print("TOP5\t%s\t%d\t%s\t%d" % (cat, rang, prod, nb))


cat, produits = None, []
for ligne in sys.stdin:
    c, prod, nb = ligne.rstrip("\n").split("\t")
    if c != cat:
        if cat is not None:
            sortie(cat, produits)
        cat, produits = c, []
    produits.append((prod, int(nb)))
if cat is not None:
    sortie(cat, produits)
