#!/usr/bin/env python3
"""Job 3a - reducer : nombre de consultations distinctes par (categorie, produit).
Une consultation identique (même session, même produit, même horodatage) est un doublon : comptée une fois.
Sorties : "P cat produit nb"  |  "DOUBLON CONSULTATION_IDENTIQUE cle"  |  "REJ ..." (transmis)."""
import sys


def sortie(cle, vues, total):
    cat, produit = cle.split("|")
    print("P\t%s\t%s\t%d" % (cat, produit, len(vues)))
    for _ in range(total - len(vues)):
        print("DOUBLON\tCONSULTATION_IDENTIQUE\t%s" % cle)


cle_courante, vues, total = None, set(), 0
for ligne in sys.stdin:
    cle, _, valeur = ligne.rstrip("\n").partition("\t")
    if cle.startswith("REJ|"):
        print(valeur)
        continue
    if cle != cle_courante:
        if cle_courante is not None:
            sortie(cle_courante, vues, total)
        cle_courante, vues, total = cle, set(), 0
    vues.add(valeur)
    total += 1
if cle_courante is not None:
    sortie(cle_courante, vues, total)
