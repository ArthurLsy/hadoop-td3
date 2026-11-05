#!/usr/bin/env python3
"""Job 3a - mapper : nettoyage des consultations. Clé = categorie|produit, valeur = session|horodatage.
Rejets : "REJ|md5 \t REJ \t CONSULTATION \t raison \t ligne brute". client_id vide toléré (inutile pour le top 5)."""
import hashlib
import re
import sys
from datetime import datetime

FORMATS_DATE = ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M")


def date_normalisee(s):
    for f in FORMATS_DATE:
        try:
            return datetime.strptime(s, f).strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            pass
    return None


def rejeter(raison, brut):
    print("REJ|%s\tREJ\tCONSULTATION\t%s\t%s" % (hashlib.md5(brut.encode("utf-8")).hexdigest(), raison, brut))


for ligne in sys.stdin:
    brut = ligne.rstrip("\r\n")
    if not brut.strip() or brut.startswith("session_id,"):
        continue
    c = [x.strip() for x in brut.split(",")]
    if len(c) != 6:
        rejeter("NB_COLONNES", brut)
        continue
    session, client, produit, cat, url, ts = c
    cat = cat.lower()
    if not re.match(r"^S\d+$", session):
        rejeter("SESSION_ID_INVALIDE", brut)
    elif not re.match(r"^P\d+$", produit):
        rejeter("PRODUIT_ID_INVALIDE", brut)
    elif not cat:
        rejeter("CATEGORIE_VIDE", brut)
    elif date_normalisee(ts) is None:
        rejeter("DATE_INVALIDE", brut)
    else:
        print("%s|%s\t%s|%s" % (cat, produit, session, date_normalisee(ts)))
