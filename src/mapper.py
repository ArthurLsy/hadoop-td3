#!/usr/bin/env python3
"""Mapper de nettoyage + préparation de la jointure (MapReduce Streaming).

Entrée  : lignes CSV de commandes, d'annulations et/ou de corrections (source reconnue
          au préfixe de l'identifiant CMD... / ANN... et au nombre de colonnes).
Sortie  : "cle \t valeur"
  - commande valide    : "CMD|ligne \t C \t categorie \t quantite \t prix"
  - annulation valide  : "CMD|ligne \t A \t annulation_id \t type \t quantite \t montant"
  - correction valide  : "CMD|ligne \t K \t correction_id \t type \t horodatage_correction \t categorie \t quantite \t prix"
  - ligne invalide     : "REJ|md5 \t REJ \t source \t raison \t ligne brute"
La clé de jointure est (commande_id, ligne_id).
"""
import hashlib
import re
import sys
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

STATUTS = {"PAYEE", "EXPEDIEE", "LIVREE", "ANNULEE"}
TYPES = {"ANNULATION", "RETOUR"}
TYPES_CORRECTION = {"AJOUT", "MODIFICATION", "SUPPRESSION"}
FORMATS_DATE = ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M")
RE_NOMBRE = re.compile(r"^-?\d+(\.\d+)?$")
RE_ENTIER = re.compile(r"^-?\d+$")
CENT = Decimal("0.01")


def rejeter(source, raison, brut):
    h = hashlib.md5(brut.encode("utf-8")).hexdigest()
    print("REJ|%s\tREJ\t%s\t%s\t%s" % (h, source, raison, brut))


def date_normalisee(s):
    """Date au format ISO, ou None si elle n'est pas lisible."""
    for f in FORMATS_DATE:
        try:
            return datetime.strptime(s, f).strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            pass
    return None


def decimal_2(s):
    """Décimal arrondi au centime, ou None si ce n'est pas un nombre."""
    if not RE_NOMBRE.match(s):
        return None
    return Decimal(s).quantize(CENT, rounding=ROUND_HALF_UP)


def reparer_virgule(champs, attendu, idx):
    """Un décimal écrit avec une virgule (35,99) éclate en deux champs :
    on recolle les champs idx et idx+1 quand le résultat est cohérent."""
    if len(champs) == attendu + 1 and champs[idx].isdigit() and champs[idx + 1].isdigit():
        return champs[:idx] + [champs[idx] + "." + champs[idx + 1]] + champs[idx + 2:]
    return champs


def valider_ligne(source, c, brut):
    """Valide les 10 premiers champs communs aux commandes et aux corrections.
    Retourne (cle, categorie, quantite, prix) ou None (rejet déjà émis)."""
    cid, lid, client, produit, cat, qte, prix, devise, statut, ts = [x.strip() for x in c[:10]]
    if not re.match(r"^CMD\d+$", cid):
        return rejeter(source, "COMMANDE_ID_INVALIDE", brut)
    if not re.match(r"^[1-9]\d*$", lid):
        return rejeter(source, "LIGNE_ID_INVALIDE", brut)
    cat = cat.lower()
    if not cat:
        return rejeter(source, "CATEGORIE_VIDE", brut)
    if not RE_ENTIER.match(qte) or int(qte) <= 0:
        return rejeter(source, "QUANTITE_INVALIDE", brut)
    p = decimal_2(prix)
    if p is None or p <= 0:
        return rejeter(source, "PRIX_INVALIDE", brut)
    if devise != "EUR":
        return rejeter(source, "DEVISE_NON_EUR", brut)
    if statut not in STATUTS:
        return rejeter(source, "STATUT_INVALIDE", brut)
    if date_normalisee(ts) is None:
        return rejeter(source, "DATE_INVALIDE", brut)
    return "%s|%d" % (cid, int(lid)), cat, int(qte), p


def traiter_commande(c, brut):
    if len(c) != 10:
        return rejeter("COMMANDE", "NB_COLONNES", brut)
    v = valider_ligne("COMMANDE", c, brut)
    if v:
        print("%s\tC\t%s\t%d\t%s" % v)


def traiter_correction(c, brut):
    if len(c) != 13:
        return rejeter("CORRECTION", "NB_COLONNES", brut)
    typ, corr_id, ts = [x.strip() for x in c[10:]]
    if typ not in TYPES_CORRECTION:
        return rejeter("CORRECTION", "TYPE_INVALIDE", brut)
    if not re.match(r"^COR\d+$", corr_id):
        return rejeter("CORRECTION", "CORRECTION_ID_INVALIDE", brut)
    ts = date_normalisee(ts)
    if ts is None:
        return rejeter("CORRECTION", "DATE_CORRECTION_INVALIDE", brut)
    v = valider_ligne("CORRECTION", c, brut)
    if v:
        print("%s\tK\t%s\t%s\t%s\t%s\t%d\t%s" % (v[0], corr_id, typ, ts, v[1], v[2], v[3]))


def traiter_annulation(brut):
    c = reparer_virgule(brut.split(","), 8, 6)
    if len(c) != 8:
        return rejeter("ANNULATION", "NB_COLONNES", brut)
    aid, cid, lid, typ, motif, qte, montant, ts = [x.strip() for x in c]
    if not re.match(r"^ANN\d+$", aid):
        return rejeter("ANNULATION", "ANNULATION_ID_INVALIDE", brut)
    if not re.match(r"^CMD\d+$", cid):
        return rejeter("ANNULATION", "COMMANDE_ID_INVALIDE", brut)
    if not re.match(r"^[1-9]\d*$", lid):
        return rejeter("ANNULATION", "LIGNE_ID_INVALIDE", brut)
    if typ not in TYPES:
        return rejeter("ANNULATION", "TYPE_INVALIDE", brut)
    if not RE_ENTIER.match(qte) or int(qte) <= 0:
        return rejeter("ANNULATION", "QUANTITE_INVALIDE", brut)
    m = decimal_2(montant)
    if m is None or m < 0:
        return rejeter("ANNULATION", "MONTANT_INVALIDE", brut)
    if date_normalisee(ts) is None:
        return rejeter("ANNULATION", "DATE_INVALIDE", brut)
    print("%s|%d\tA\t%s\t%s\t%d\t%s" % (cid, int(lid), aid, typ, int(qte), m))


def main():
    for ligne in sys.stdin:
        brut = ligne.rstrip("\r\n")
        if not brut.strip():
            continue
        if brut.startswith(("commande_id,", "annulation_id,")):  # en-têtes
            continue
        if brut.startswith("CMD"):
            c = brut.split(",")
            # Une correction a 13 colonnes (14 si un prix décimal éclaté par une virgule).
            if len(c) >= 13 and c[-3] in TYPES_CORRECTION:
                traiter_correction(reparer_virgule(c, 13, 6), brut)
            else:
                traiter_commande(reparer_virgule(c, 10, 6), brut)
        elif brut.startswith("ANN"):
            traiter_annulation(brut)
        else:
            rejeter("INCONNUE", "SOURCE_NON_RECONNUE", brut)


if __name__ == "__main__":
    main()
