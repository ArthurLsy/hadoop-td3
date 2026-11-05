#!/usr/bin/env python3
"""Reducer de jointure (côté reducer) commandes <-> annulations, avec versionnement.

Reçoit, groupées par clé "commande_id|ligne_id", les lignes tagguées C (commande),
A (annulation) et K (correction) produites par mapper.py.

Versionnement : la commande d'origine est la version 1 ; chaque correction appliquée
(triées par horodatage_correction puis correction_id) crée une version suivante.
Les agrégats utilisent la DERNIÈRE version. L'original n'est jamais écrasé.

Sorties (première colonne = type) :
  VERSION  clé, n°, ORIGINE|AJOUT|MODIFICATION|SUPPRESSION, correction_id, catégorie, quantité, prix
  LIGNE    catégorie, commande_id, ligne_id, brut, annulé, version      (état final, si non supprimée)
  ANNOK    annulation_id, commande_id, ligne_id, montant                (annulation rattachée)
  ORPH     annulation_id, commande_id, ligne_id, montant, raison        (aucune ligne de commande)
  CORRORPH correction_id, clé, type                                     (correction sans ligne à modifier)
  DOUBLON  raison, clé, détail                                          (doublon exact)
  ALERTE   raison, clé, détail                                          (à examiner, non bloquant)
  BLOQUANT raison, clé, détail                                          (interdit la publication)
  REJ      source, raison, détail                                       (rejets du mapper, clés dupliquées
                                                                         différentes, remboursement > ligne)
"""
import sys
from decimal import Decimal


def flush(cle, cmds, anns, cors):
    cid, lid = cle.split("|")

    # --- dédoublonnage des commandes identiques
    vues = []
    for c in cmds:
        if c in vues:
            print("DOUBLON\tCOMMANDE_IDENTIQUE\t%s\t%s" % (cle, "\t".join(c)))
        else:
            vues.append(c)
    # --- dédoublonnage des annulations (même annulation_id)
    uniques = {}
    for a in anns:
        if a[0] in uniques:
            print("DOUBLON\tANNULATION_IDENTIQUE\t%s\t%s" % (cle, "\t".join(a)))
        else:
            uniques[a[0]] = a
    annulations = list(uniques.values())
    # --- dédoublonnage des corrections (même correction_id)
    corrections = {}
    for k in cors:
        if k[0] in corrections:
            print("DOUBLON\tCORRECTION_IDENTIQUE\t%s\t%s" % (cle, "\t".join(k)))
        else:
            corrections[k[0]] = k

    # Même clé avec des contenus différents : on rejette TOUTES les versions.
    if len(vues) > 1:
        for v in vues:
            print("REJ\tCOMMANDE\tCLE_DUPLIQUEE_DIFFERENTE\t%s,%s" % (cle, ",".join(v)))
        vues = []

    # --- versionnement
    etat, version = None, 0
    if vues:
        etat, version = vues[0], 1
        print("VERSION\t%s\t1\tORIGINE\t-\t%s\t%s\t%s" % (cle, *etat))
    for k in sorted(corrections.values(), key=lambda x: (x[2], x[0])):   # (ts_correction, id)
        corr_id, typ, _ts, cat, qte, prix = k
        if typ == "AJOUT":
            if etat is not None:
                print("ALERTE\tAJOUT_SUR_LIGNE_EXISTANTE\t%s\t%s" % (cle, corr_id))
            nouvel = (cat, qte, prix)
        elif typ == "MODIFICATION":
            if etat is None:
                print("CORRORPH\t%s\t%s\t%s" % (corr_id, cle, typ))
                continue
            nouvel = (cat, qte, prix)
        else:  # SUPPRESSION
            if etat is None:
                print("CORRORPH\t%s\t%s\t%s" % (corr_id, cle, typ))
                continue
            nouvel = None
        version += 1
        print("VERSION\t%s\t%d\t%s\t%s\t%s\t%s\t%s" % (cle, version, typ, corr_id, cat, qte, prix))
        etat = nouvel

    if etat is None:
        raison = "LIGNE_SUPPRIMEE" if version else "LIGNE_ABSENTE"
        for a in annulations:
            print("ORPH\t%s\t%s\t%s\t%s\t%s" % (a[0], cid, lid, a[3], raison))
        return

    cat, qte, prix = etat
    brut = Decimal(qte) * Decimal(prix)
    annule = Decimal("0")
    qte_annulee = 0
    # Annulations traitées par identifiant (ordre déterministe). Une annulation qui ferait
    # dépasser le montant de la ligne est rejetée et signalée (non déduite).
    for a in sorted(annulations, key=lambda x: x[0]):
        if annule + Decimal(a[3]) > brut:
            print("REJ\tANNULATION\tMONTANT_SUPERIEUR_AU_BRUT\t%s,%s,%s,%s,%s>%s"
                  % (a[0], cle, a[1], a[2], annule + Decimal(a[3]), brut))
            continue
        annule += Decimal(a[3])
        qte_annulee += int(a[2])
        print("ANNOK\t%s\t%s\t%s\t%s" % (a[0], cid, lid, a[3]))
    print("LIGNE\t%s\t%s\t%s\t%s\t%s\t%d" % (cat, cid, lid, brut, annule, version))
    # Quantité annulée > quantité commandée : anomalie BLOQUANTE (aucune publication).
    if qte_annulee > int(qte):
        print("BLOQUANT\tQUANTITE_ANNULEE_SUPERIEURE\t%s\t%d>%s" % (cle, qte_annulee, qte))


def main():
    cle_courante, cmds, anns, cors = None, [], [], []
    for ligne in sys.stdin:
        ligne = ligne.rstrip("\n")
        cle, _, valeur = ligne.partition("\t")
        if cle.startswith("REJ|"):
            print(valeur)
            continue
        if cle != cle_courante:
            if cle_courante is not None:
                flush(cle_courante, cmds, anns, cors)
            cle_courante, cmds, anns, cors = cle, [], [], []
        champs = valeur.split("\t")
        if champs[0] == "C":
            cmds.append(tuple(champs[1:]))     # (categorie, quantite, prix)
        elif champs[0] == "A":
            anns.append(tuple(champs[1:]))     # (ann_id, type, quantite, montant)
        else:
            cors.append(tuple(champs[1:]))     # (corr_id, type, ts_corr, categorie, quantite, prix)
    if cle_courante is not None:
        flush(cle_courante, cmds, anns, cors)


if __name__ == "__main__":
    main()
