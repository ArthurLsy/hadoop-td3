#!/bin/bash
# Simule localement le pipeline Streaming (cat | map | sort | reduce) et vérifie les contrôles.
# Usage : ./run_local.sh commandes.csv annulations.csv [attendu.tsv] [corrections.csv]
set -euo pipefail
export LC_ALL=C
D="$(cd "$(dirname "$0")" && pwd)"
CMD="$1"; ANN="$2"; ATTENDU="${3:-}"; COR="${4:-}"
OUT="$(mktemp -d)"
# Concaténation sûre : certains CSV fournis n'ont pas de retour à la ligne final.
tout() { for f in "$CMD" "$ANN" $COR; do cat "$f"; echo; done; }

tout | python3 "$D/mapper.py" | sort | python3 "$D/reducer.py" > "$OUT/job1.tsv"
python3 "$D/agg_mapper.py" < "$OUT/job1.tsv" | sort | python3 "$D/agg_reducer.py" > "$OUT/agg.tsv"

cnt() { grep -c "^$1	" "$OUT/job1.tsv" || true; }
N_IN=$(tout | grep -vE '^(commande_id|annulation_id),' | grep -c . || true)
N_LIGNE=$(cnt VERSION); N_CORO=$(cnt CORRORPH); N_ANNOK=$(cnt ANNOK); N_ORPH=$(cnt ORPH); N_DOUB=$(cnt DOUBLON); N_REJ=$(cnt REJ); N_BLOQ=$(cnt BLOQUANT)

echo "=== Agrégats (categorie, brut, annulations, net, nb_commandes) ==="
cat "$OUT/agg.tsv"
echo
echo "=== Contrôles ==="
SOMME=$((N_LIGNE + N_CORO + N_ANNOK + N_ORPH + N_DOUB + N_REJ))
echo "lignes en entrée      : $N_IN"
echo "valides + rejets      : $SOMME  (versions=$N_LIGNE, corrections orphelines=$N_CORO, annulations rattachées=$N_ANNOK, orphelines=$N_ORPH, doublons=$N_DOUB, rejets=$N_REJ)"
[ "$N_IN" -eq "$SOMME" ] && echo "OK  entrée = valides + rejetées" || { echo "ECHEC  entrée != valides + rejetées"; exit 1; }
# Contrôle indépendant : brut(LIGNE) - annulations(ANNOK) doit égaler la somme des nets agrégés
BRUT=$(awk -F'\t' '$1=="LIGNE"{s+=$5} END{printf "%.2f",s}' "$OUT/job1.tsv")
ANNS=$(awk -F'\t' '$1=="ANNOK"{s+=$5} END{printf "%.2f",s}' "$OUT/job1.tsv")
NET=$(awk -F'\t' '{s+=$4} END{printf "%.2f",s}' "$OUT/agg.tsv")
ATT=$(awk -v b="$BRUT" -v a="$ANNS" 'BEGIN{printf "%.2f",b-a}')
echo "brut=$BRUT annulations rattachées=$ANNS net attendu=$ATT net agrégé=$NET"
[ "$ATT" = "$NET" ] && echo "OK  brut - annulations = net" || { echo "ECHEC brut - annulations != net"; exit 1; }
echo "anomalies bloquantes   : $N_BLOQ"
if [ "$N_BLOQ" -gt 0 ]; then
  echo "PUBLICATION BLOQUEE : anomalies bloquantes à examiner ->"; grep "^BLOQUANT" "$OUT/job1.tsv" | head -20
  echo "Sorties détaillées : $OUT/job1.tsv"; exit 2
fi
if [ -n "$ATTENDU" ]; then
  if diff <(sort "$OUT/agg.tsv") <(sort "$ATTENDU") > "$OUT/diff.txt"; then echo "OK  résultat identique au tableau attendu"; else echo "ECHEC écart avec le tableau attendu :"; cat "$OUT/diff.txt"; exit 1; fi
fi
echo "Sorties détaillées : $OUT/job1.tsv"
