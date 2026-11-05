#!/usr/bin/env python3
"""Job 2 - mapper : ne garde que les lignes LIGNE du job 1, clé = catégorie."""
import sys

for ligne in sys.stdin:
    c = ligne.rstrip("\n").split("\t")
    if c[0] == "LIGNE":                      # LIGNE cat cid lid brut annule
        print("%s\t%s\t%s\t%s" % (c[1], c[2], c[4], c[5]))
