#!/usr/bin/env python3
"""Job 2 - reducer : CA brut, annulations, CA net et nb de commandes distinctes par catégorie."""
import sys
from decimal import Decimal


def sortie(cat, brut, annule, commandes):
    d = lambda x: x.quantize(Decimal("0.01"))
    print("%s\t%s\t%s\t%s\t%d" % (cat, d(brut), d(annule), d(brut - annule), len(commandes)))


cat, brut, annule, commandes = None, Decimal(0), Decimal(0), set()
for ligne in sys.stdin:
    c, cid, b, a = ligne.rstrip("\n").split("\t")
    if c != cat:
        if cat is not None:
            sortie(cat, brut, annule, commandes)
        cat, brut, annule, commandes = c, Decimal(0), Decimal(0), set()
    brut += Decimal(b)
    annule += Decimal(a)
    commandes.add(cid)
if cat is not None:
    sortie(cat, brut, annule, commandes)
