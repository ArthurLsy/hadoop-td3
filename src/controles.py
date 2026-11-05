#!/usr/bin/env python3
"""Contrôles de cohérence avant publication.

Usage : controles.py --job1 F --agg F --cons F --commerce F... --consultations F... [--seuil 0.05] [--sortie rapport.json]
Code de sortie : 0 = publiable ; 2 = publication BLOQUEE (le rapport dit pourquoi).
"""
import argparse
import json
import sys
from collections import Counter
from decimal import Decimal


def lire(chemin):
    with open(chemin, encoding="utf-8") as f:
        return [l.rstrip("\n").split("\t") for l in f if l.strip()]


def nb_lignes(fichiers):
    n = 0
    for chemin in fichiers:
        with open(chemin, encoding="utf-8") as f:
            for l in f:
                if l.strip() and not l.startswith(("commande_id,", "annulation_id,", "session_id,")):
                    n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job1", required=True)
    ap.add_argument("--agg", required=True)
    ap.add_argument("--cons", required=True)
    ap.add_argument("--commerce", nargs="+", required=True)
    ap.add_argument("--consultations", nargs="+", required=True)
    ap.add_argument("--seuil", type=float, default=0.05)
    ap.add_argument("--sortie")
    a = ap.parse_args()

    j1 = Counter(l[0] for l in lire(a.job1))
    j1_lignes = lire(a.job1)
    c3 = Counter(l[0] for l in lire(a.cons))
    agg = lire(a.agg)
    n_commerce, n_cons = nb_lignes(a.commerce), nb_lignes(a.consultations)
    controles = []

    def ctrl(nom, ok, detail, bloquant=True):
        controles.append({"controle": nom, "ok": bool(ok), "detail": detail, "bloquant": bloquant})

    # 0. flux présents et non vides
    ctrl("flux_commerce_non_vide", n_commerce > 0, "%d lignes" % n_commerce)
    ctrl("flux_consultations_non_vide", n_cons > 0, "%d lignes" % n_cons)

    # 1. entrée = valides + rejetées (commandes / annulations / corrections)
    sortis = j1["VERSION"] + j1["CORRORPH"] + j1["ANNOK"] + j1["ORPH"] + j1["DOUBLON"] + j1["REJ"]
    ctrl("commerce_entree_egale_sorties", n_commerce == sortis,
         "entrée=%d ; VERSION=%d + CORRORPH=%d + ANNOK=%d + ORPH=%d + DOUBLON=%d + REJ=%d = %d"
         % (n_commerce, j1["VERSION"], j1["CORRORPH"], j1["ANNOK"], j1["ORPH"], j1["DOUBLON"], j1["REJ"], sortis))

    # 2. consultations : entrée = consultations distinctes + doublons + rejets
    nb_p = sum(int(l[3]) for l in lire(a.cons) if l[0] == "P")
    sortis_c = nb_p + c3["DOUBLON"] + c3["REJ"]
    ctrl("consultations_entree_egale_sorties", n_cons == sortis_c,
         "entrée=%d ; distinctes=%d + doublons=%d + rejets=%d = %d" % (n_cons, nb_p, c3["DOUBLON"], c3["REJ"], sortis_c))

    # 3. brut - annulations = net (recalculé indépendamment depuis le job 1)
    brut = sum(Decimal(l[4]) for l in j1_lignes if l[0] == "LIGNE")
    annule = sum(Decimal(l[4]) for l in j1_lignes if l[0] == "ANNOK")
    net_agg = sum(Decimal(l[3]) for l in agg)
    brut_agg = sum(Decimal(l[1]) for l in agg)
    ctrl("net_egal_brut_moins_annulations", brut - annule == net_agg and brut == brut_agg,
         "brut=%s - annulations=%s = %s ; net agrégé=%s ; brut agrégé=%s" % (brut, annule, brut - annule, net_agg, brut_agg))

    # 4. taux de rejets sous le seuil
    tx_c = j1["REJ"] / n_commerce if n_commerce else 1
    tx_k = c3["REJ"] / n_cons if n_cons else 1
    ctrl("taux_rejets_commerce", tx_c <= a.seuil, "%.2f %% (seuil %.0f %%)" % (100 * tx_c, 100 * a.seuil))
    ctrl("taux_rejets_consultations", tx_k <= a.seuil, "%.2f %% (seuil %.0f %%)" % (100 * tx_k, 100 * a.seuil))

    # 5. aucune anomalie bloquante
    ctrl("aucune_anomalie_bloquante", j1["BLOQUANT"] == 0, "%d anomalie(s) bloquante(s)" % j1["BLOQUANT"])

    ok = all(c["ok"] for c in controles if c["bloquant"])
    rapport = {"publiable": ok, "controles": controles,
               "compteurs": {"commerce": dict(j1), "consultations": dict(c3)}}
    texte = json.dumps(rapport, indent=2, ensure_ascii=False)
    if a.sortie:
        with open(a.sortie, "w", encoding="utf-8") as f:
            f.write(texte + "\n")
    for c in controles:
        print("%s  %s : %s" % ("OK    " if c["ok"] else "ECHEC ", c["controle"], c["detail"]))
    print("=> %s" % ("PUBLIABLE" if ok else "PUBLICATION BLOQUEE"))
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
