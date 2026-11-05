#!/usr/bin/env python3
"""Gestion de la file d'attente des annulations orphelines (règle des 3 flux).

Le compteur d'une orpheline = nombre de LOTS distincts dans lesquels elle est restée orpheline
(rejouer un même lot n'incrémente donc pas : traitement idempotent).
  compteur < max : reste EN ATTENTE ; compteur >= max : REJETEE (expirée).
Usage : orphelines.py --job1 F --lot N [--etat-prec F] [--max 3] --etat-sortie F --expirees F
Fichier d'état : annulation_id \t commande_id \t ligne_id \t montant \t lots (liste séparée par des virgules)
"""
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job1", required=True)
    ap.add_argument("--lot", required=True)
    ap.add_argument("--etat-prec")
    ap.add_argument("--max", type=int, default=3)
    ap.add_argument("--etat-sortie", required=True)
    ap.add_argument("--expirees", required=True)
    a = ap.parse_args()

    prec = {}
    if a.etat_prec:
        try:
            for l in open(a.etat_prec, encoding="utf-8"):
                c = l.rstrip("\n").split("\t")
                if len(c) == 5:
                    prec[c[0]] = set(c[4].split(","))
        except FileNotFoundError:
            pass

    attente, expirees = [], []
    for l in open(a.job1, encoding="utf-8"):
        c = l.rstrip("\n").split("\t")
        if c[0] != "ORPH":
            continue
        aid, cid, lid, montant = c[1:5]
        lots = prec.get(aid, set()) | {a.lot}
        ligne = "\t".join([aid, cid, lid, montant, ",".join(sorted(lots, key=int))])
        (expirees if len(lots) >= a.max else attente).append((ligne, len(lots)))

    with open(a.etat_sortie, "w", encoding="utf-8") as f:
        for ligne, _ in sorted(attente):
            f.write(ligne + "\n")
    with open(a.expirees, "w", encoding="utf-8") as f:
        for ligne, n in sorted(expirees):
            f.write("ORPHELINE_EXPIREE\t%s\tflux=%d\n" % (ligne, n))
    print("orphelines : %d en attente, %d expirées (rejetées)" % (len(attente), len(expirees)))


if __name__ == "__main__":
    main()
