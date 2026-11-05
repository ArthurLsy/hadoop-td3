#!/bin/bash
# Pipeline MarchéPlus sur le cluster Docker (MapReduce Streaming).
#
# Usage : ./pipeline.sh JOUR LOT FICHIER.csv [FICHIER.csv ...]
#   ex. ./pipeline.sh 20261115 1 ../donnees/commandes_20261115.csv ../donnees/annulations_20261115.csv ../donnees/consultations_20261115.csv
#       ./pipeline.sh 20261115 2 ../donnees/corrections_20261115.csv        # lot correctif du lendemain
#
# Étapes : contrôle des flux -> dépôt brut immuable -> jobs Streaming -> contrôles ->
#          publication atomique (renommage + marqueur _VALIDE) -> copie dans persistant/.
# Codes de sortie : 0 publié | 2 publication bloquée par les contrôles | 3 flux manquant/vide |
#                   4 brut déjà présent mais différent (immuable) | autre : échec technique (rien de publié)
set -euo pipefail

JOUR="$1"; LOT="$2"; shift 2
FICHIERS=("$@")
[ ${#FICHIERS[@]} -gt 0 ] || { echo "Usage : $0 JOUR LOT fichiers..."; exit 64; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/src"
PERS="$ROOT/environnement/persistant"
BASE=/marcheplus
JAR=/opt/hadoop-3.2.1/share/hadoop/tools/lib/hadoop-streaming-3.2.1.jar
RUN="$(date +%Y%m%dT%H%M%S)"
WORK="$(mktemp -d)"
NN="docker exec -i namenode"
TMP="$BASE/tmp/jour=$JOUR/run=$RUN"
DUREES="$WORK/durees.tsv"; : > "$DUREES"
SEUIL="${SEUIL_REJETS:-0.05}"

log() { echo "[$(date +%H:%M:%S)] $*"; }

# Lecture HDFS avec reprise : si un DataNode vient de tomber mais que le NameNode le croit encore vivant,
# une lecture peut échouer (UnresolvedAddressException) sans basculer sur un autre réplica.
# On réessaie ; un échec persistant est signalé comme ERREUR DE LECTURE, jamais comme "contenu différent".
hdfs_cat() {  # hdfs_cat chemin  -> contenu sur stdout
  local i tmp; tmp="$(mktemp)"
  for i in 1 2 3 4 5 6 7 8; do
    if $NN bash -c "set -o pipefail; hdfs dfs -cat '$1'" > "$tmp" 2>/dev/null; then cat "$tmp"; rm -f "$tmp"; return 0; fi
    sleep 1
  done
  rm -f "$tmp"; echo "ERREUR DE LECTURE HDFS : $1 (8 essais)" >&2; return 1
}
trap 'rc=$?; [ $rc -ne 0 ] && [ $rc -lt 2 -o $rc -gt 4 ] && echo "[ECHEC technique code=$rc] rien n a été publié. Travail partiel : $TMP (HDFS), $WORK (local)" >&2' EXIT

# ------------------------------------------------------------------ 1. Contrôle des flux en entrée
log "1/7 Contrôle des flux (jour=$JOUR lot=$LOT)"
a_fichier() { for f in "${FICHIERS[@]}"; do case "$(basename "$f")" in $1) [ -s "$f" ] && return 0;; esac; done; return 1; }
for f in "${FICHIERS[@]}"; do
  [ -s "$f" ] || { echo "FLUX MANQUANT OU VIDE : $f -> aucune publication" >&2; exit 3; }
done
if [ "$LOT" = "1" ]; then
  for flux in 'commandes_*' 'annulations_*' 'consultations_*'; do
    a_fichier "$flux" || { echo "FLUX MANQUANT : $flux (obligatoire pour le lot 1) -> aucune publication" >&2; exit 3; }
  done
fi

# ------------------------------------------------------------------ 2. Dépôt brut immuable
log "2/7 Dépôt dans la zone brute (immuable)"
BRUT="$BASE/brut/jour=$JOUR/lot=$LOT"
$NN rm -rf /tmp/in && $NN mkdir -p /tmp/in
for f in "${FICHIERS[@]}"; do docker cp "$f" "namenode:/tmp/in/$(basename "$f")"; done
if $NN hdfs dfs -test -d "$BRUT" 2>/dev/null; then
  for f in "${FICHIERS[@]}"; do
    b="$(basename "$f")"
    h_local="$($NN md5sum "/tmp/in/$b" | cut -d' ' -f1)"
    hdfs_cat "$BRUT/$b" > "$WORK/verif.tmp" || exit 1
    h_hdfs="$(md5sum < "$WORK/verif.tmp" | cut -d' ' -f1)"
    [ "$h_local" = "$h_hdfs" ] || { echo "BRUT IMMUABLE : $b existe déjà dans $BRUT avec un contenu différent -> refus" >&2; exit 4; }
  done
  log "    lot déjà déposé à l'identique : rejeu, le brut n'est pas réécrit"
else
  $NN hdfs dfs -mkdir -p "$BRUT"
  $NN bash -c "hdfs dfs -put /tmp/in/*.csv '$BRUT/'"
fi

# ------------------------------------------------------------------ 3. Jobs MapReduce Streaming
$NN rm -rf /tmp/src && docker cp "$SRC" namenode:/tmp/src
$NN hdfs dfs -mkdir -p "$TMP"

entrees() {  # entrees PREFIXE... : -input pour chaque fichier existant des lots 1..LOT
  local args=() l p f
  for l in $(seq 1 "$LOT"); do
    for p in "$@"; do
      for f in $($NN hdfs dfs -ls -C "$BASE/brut/jour=$JOUR/lot=$l" 2>/dev/null | grep -E "/${p}_[^/]*\.csv$" || true); do
        args+=(-input "$f")
      done
    done
  done
  echo "${args[@]}"
}

stream() {  # stream NOM NB_REDUCERS SORTIE "ENTREES" MAPPER REDUCER
  local nom="$1" nr="$2" sortie="$3" entrees="$4" m="$5" r="$6" t0
  t0=$(date +%s)
  log "    job $nom (reducers=$nr)"
  # shellcheck disable=SC2086
  $NN hadoop jar "$JAR" -D mapreduce.job.name="marcheplus-$nom-$JOUR" -D mapreduce.job.reduces="$nr" \
      -files "/tmp/src/$m,/tmp/src/$r" $entrees -output "$sortie" \
      -mapper "python3 $m" -reducer "python3 $r" > "$WORK/$nom.log" 2>&1 \
      || {
        # Le client Streaming peut perdre le fil après la fin du job (pas de JobHistory Server MapReduce
        # dans ce cluster, ou client ralenti par une panne) : seul le marqueur _SUCCESS écrit par le
        # committer HDFS atteste que le job a réussi. Un job tué ou en échec n'en a pas.
        if $NN hdfs dfs -test -e "$sortie/_SUCCESS" 2>/dev/null; then
          log "    ATTENTION : le client Streaming a échoué mais $sortie/_SUCCESS existe -> job réussi côté YARN, on continue"
        else
          tail -25 "$WORK/$nom.log" >&2; echo "JOB $nom EN ECHEC (pas de _SUCCESS dans $sortie)" >&2; exit 1
        fi
      }
  printf '%s\t%s\n' "$nom" "$(( $(date +%s) - t0 ))" >> "$DUREES"
}

log "3/7 Jobs Streaming (sorties temporaires dans $TMP)"
IN_COMMERCE="$(entrees commandes annulations corrections)"
IN_CONS="$(entrees consultations)"
stream job1_nettoyage_jointure 2 "$TMP/job1" "$IN_COMMERCE" mapper.py reducer.py
stream job2_agregats           1 "$TMP/agg"  "-input $TMP/job1" agg_mapper.py agg_reducer.py
if [ -n "$IN_CONS" ]; then
  stream job3a_consultations   2 "$TMP/cons" "$IN_CONS" cons_mapper.py cons_reducer.py
  stream job3b_top5            1 "$TMP/top5" "-input $TMP/cons" top5_mapper.py top5_reducer.py
fi

# ------------------------------------------------------------------ 4. Rapatriement des sorties + brut pour contrôle
log "4/7 Récupération des sorties"
mkdir -p "$WORK/raw"
for d in job1 agg cons top5; do
  : > "$WORK/$d.tsv"
  if $NN hdfs dfs -test -d "$TMP/$d" 2>/dev/null; then
    for part in $($NN hdfs dfs -ls -C "$TMP/$d" | grep '/part-'); do hdfs_cat "$part" >> "$WORK/$d.tsv" || exit 1; done
  fi
done
for l in $(seq 1 "$LOT"); do
  for f in $($NN hdfs dfs -ls -C "$BASE/brut/jour=$JOUR/lot=$l"); do
    hdfs_cat "$f" > "$WORK/raw/lot${l}_$(basename "$f")" || exit 1
  done
done
COMMERCE=("$WORK"/raw/*commandes_* "$WORK"/raw/*annulations_*)
for c in "$WORK"/raw/*corrections_*; do [ -e "$c" ] && COMMERCE+=("$c"); done
CONSULT=("$WORK"/raw/*consultations_*)

# ------------------------------------------------------------------ 5. Orphelines (règle des 3 flux) + anomalies
log "5/7 File d'attente des orphelines"
ETAT_PREC="$PERS/etat/orphelines_jour=$JOUR.tsv"
python3 "$SRC/orphelines.py" --job1 "$WORK/job1.tsv" --lot "$LOT" --etat-prec "$ETAT_PREC" \
        --etat-sortie "$WORK/orphelines_etat.tsv" --expirees "$WORK/orphelines_expirees.tsv"
{
  awk -F'\t' '$1 ~ /^(REJ|DOUBLON|ORPH|CORRORPH|ALERTE|BLOQUANT)$/ {print "commerce\t" $0}' "$WORK/job1.tsv"
  awk -F'\t' '$1 ~ /^(REJ|DOUBLON)$/ {print "consultations\t" $0}' "$WORK/cons.tsv"
  sed 's/^/commerce\t/' "$WORK/orphelines_expirees.tsv"
} | sort > "$WORK/anomalies.tsv"
grep -E '^(LIGNE|VERSION)' "$WORK/job1.tsv" | sort > "$WORK/versions_et_lignes.tsv"
sort "$WORK/agg.tsv" > "$WORK/ca_par_categorie.tsv"
sort "$WORK/top5.tsv" > "$WORK/top5_consultations.tsv"

# ------------------------------------------------------------------ 6. Contrôles avant publication
log "6/7 Contrôles de cohérence"
set +e
python3 "$SRC/controles.py" --job1 "$WORK/job1.tsv" --agg "$WORK/agg.tsv" --cons "$WORK/cons.tsv" \
        --commerce "${COMMERCE[@]}" --consultations "${CONSULT[@]}" --seuil "$SEUIL" --sortie "$WORK/rapport_controles.json"
RC=$?
set -e

if [ $RC -ne 0 ]; then
  ECH="$BASE/echecs/jour=$JOUR/run=$RUN"
  $NN hdfs dfs -mkdir -p "$ECH"
  $NN bash -c "mkdir -p /tmp/ech && rm -rf /tmp/ech/*"
  docker cp "$WORK/." namenode:/tmp/ech/ >/dev/null
  $NN bash -c "hdfs dfs -put /tmp/ech/*.tsv /tmp/ech/*.json '$ECH/'"
  log "PUBLICATION BLOQUEE : le résultat n'est PAS officiel. Détails dans $ECH (HDFS) et $WORK (local)."
  log "Le dernier résultat publié (s'il existe) reste inchangé."
  exit 2
fi

# ------------------------------------------------------------------ 7. Publication atomique + persistance
NBV=$($NN hdfs dfs -ls -C "$BASE/publie/jour=$JOUR" 2>/dev/null | grep -c '/v=' || true)
if [ "$NBV" -gt 0 ]; then   # rejeu : même résultat que la dernière version => pas de nouvelle version
  H_NEW="$(cat "$WORK/ca_par_categorie.tsv" "$WORK/top5_consultations.tsv" "$WORK/anomalies.tsv" | md5sum | cut -d' ' -f1)"
  : > "$WORK/ancienne_version.tmp"
  for f in ca_par_categorie.tsv top5_consultations.tsv anomalies.tsv; do
    hdfs_cat "$BASE/publie/jour=$JOUR/v=$NBV/$f" >> "$WORK/ancienne_version.tmp" || exit 1
  done
  H_OLD="$(md5sum < "$WORK/ancienne_version.tmp" | cut -d' ' -f1)"
  if [ "$H_NEW" = "$H_OLD" ]; then
    $NN hdfs dfs -rm -r -f -skipTrash "$TMP" >/dev/null || true
    log "RESULTAT IDENTIQUE à v=$NBV : aucune nouvelle version publiée (rejeu idempotent)."
    exit 0
  fi
fi

log "7/7 Publication atomique"
STAGE="$TMP/publie"
$NN hdfs dfs -mkdir -p "$STAGE"
$NN bash -c "mkdir -p /tmp/pub && rm -rf /tmp/pub/*"
for f in ca_par_categorie.tsv top5_consultations.tsv anomalies.tsv versions_et_lignes.tsv durees.tsv rapport_controles.json; do
  docker cp "$WORK/$f" "namenode:/tmp/pub/$f"
done
$NN bash -c "hdfs dfs -put /tmp/pub/* '$STAGE/'"
NBV=$($NN hdfs dfs -ls -C "$BASE/publie/jour=$JOUR" 2>/dev/null | grep -c '/v=' || true)
V=$((NBV + 1))
printf '{"jour":"%s","version":%d,"lot":%s,"run":"%s","valide_le":"%s"}\n' "$JOUR" "$V" "$LOT" "$RUN" "$(date -u +%FT%TZ)" > "$WORK/_VALIDE"
docker cp "$WORK/_VALIDE" namenode:/tmp/pub/_VALIDE
$NN hdfs dfs -put /tmp/pub/_VALIDE "$STAGE/_VALIDE"          # marqueur écrit AVANT le renommage
$NN hdfs dfs -mkdir -p "$BASE/publie/jour=$JOUR" "$BASE/propre/jour=$JOUR"
# Un /propre/v=V sans /publie/v=V correspondant ne peut venir que d'une publication interrompue : on le remplace.
$NN hdfs dfs -rm -r -f -skipTrash "$BASE/propre/jour=$JOUR/v=$V" >/dev/null 2>&1 || true
$NN hdfs dfs -mv "$TMP/job1" "$BASE/propre/jour=$JOUR/v=$V"   # zone propre (lignes versionnées)
$NN hdfs dfs -mv "$STAGE" "$BASE/publie/jour=$JOUR/v=$V"      # renommage atomique = publication
echo "v=$V" > "$WORK/COURANT"
docker cp "$WORK/COURANT" namenode:/tmp/pub/COURANT
$NN bash -c "hdfs dfs -rm -f '$BASE/publie/jour=$JOUR/COURANT' >/dev/null 2>&1; hdfs dfs -put /tmp/pub/COURANT '$BASE/publie/jour=$JOUR/COURANT'"

if [ "${SANS_PERSISTANCE:-0}" = "1" ]; then
  log "    SANS_PERSISTANCE=1 : copie vers persistant/ ignorée (mesures de montée en charge)"
else
  # Persistance hors cluster (dossier de l'hôte monté sur /persistant)
  mkdir -p "$PERS/etat"
  $NN bash -c "mkdir -p '/persistant/publie/jour=$JOUR' '/persistant/brut/jour=$JOUR' && \
    rm -rf '/persistant/publie/jour=$JOUR/v=$V' '/persistant/brut/jour=$JOUR/lot=$LOT' && \
    hdfs dfs -get '$BASE/publie/jour=$JOUR/v=$V' '/persistant/publie/jour=$JOUR/' && \
    hdfs dfs -get '$BRUT' '/persistant/brut/jour=$JOUR/' && \
    hdfs dfs -get '$BASE/publie/jour=$JOUR/COURANT' '/persistant/publie/jour=$JOUR/COURANT.tmp' && \
    mv -f '/persistant/publie/jour=$JOUR/COURANT.tmp' '/persistant/publie/jour=$JOUR/COURANT'"
  cp "$WORK/orphelines_etat.tsv" "$PERS/etat/orphelines_jour=$JOUR.tsv"

fi
$NN hdfs dfs -rm -r -f -skipTrash "$TMP" >/dev/null || true

if [ "${SANS_PERSISTANCE:-0}" = "1" ]; then log "PUBLIE : $BASE/publie/jour=$JOUR/v=$V  (HDFS uniquement, pas de copie durable)"; else log "PUBLIE : $BASE/publie/jour=$JOUR/v=$V  (copie durable : environnement/persistant/publie/jour=$JOUR/v=$V)"; fi
echo
echo "=== CA par catégorie (catégorie, brut, annulations, net, nb commandes) ==="; cat "$WORK/ca_par_categorie.tsv"
echo "=== Durées des jobs (s) ==="; cat "$WORK/durees.tsv"
echo "Fichiers locaux : $WORK"
