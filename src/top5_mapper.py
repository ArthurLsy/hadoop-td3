#!/usr/bin/env python3
"""Job 3b - mapper : garde les lignes P de la sortie du job 3a, clé = catégorie."""
import sys

for ligne in sys.stdin:
    c = ligne.rstrip("\n").split("\t")
    if c[0] == "P":                       # P cat produit nb
        print("%s\t%s\t%s" % (c[1], c[2], c[3]))
