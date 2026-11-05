#!/bin/bash
# Restaure dans HDFS (cluster recréé) les résultats validés et le brut conservés dans persistant/.
# Usage : ./restore.sh            (restaure tout ce qui est dans persistant/)
# Vérifie ensuite, fichier par fichier, que HDFS contient exactement le contenu de persistant/ (md5).
set -euo pipefail
BASE=/marcheplus
NN="docker exec -i namenode"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PERS="$ROOT/environnement/persistant"

[ -d "$PERS/publie" ] || { echo "Rien à restaurer : $PERS/publie n'existe pas"; exit 1; }
$NN hdfs dfs -mkdir -p "$BASE/publie" "$BASE/brut"

echo "== Restauration depuis /persistant"
$NN bash -c "for d in /persistant/publie/*/ ; do j=\$(basename \$d); hdfs dfs -mkdir -p $BASE/publie/\$j; hdfs dfs -put -f \$d/* $BASE/publie/\$j/ ; done" 2>&1 | grep -v SASL || true
$NN bash -c "for d in /persistant/brut/*/ ; do j=\$(basename \$d); hdfs dfs -mkdir -p $BASE/brut/\$j; hdfs dfs -put -f \$d/* $BASE/brut/\$j/ ; done" 2>&1 | grep -v SASL || true

echo "== Vérification md5 (persistant/ <-> HDFS)"
ECARTS=0; N=0
while IFS= read -r f; do
  rel="${f#$PERS/}"
  h_loc="$(md5 -q "$f")"
  h_hdfs="$($NN bash -c "hdfs dfs -cat '$BASE/$rel' 2>/dev/null | md5sum" < /dev/null | cut -d' ' -f1)"
  N=$((N+1))
  if [ "$h_loc" != "$h_hdfs" ]; then echo "ECART  $rel"; ECARTS=$((ECARTS+1)); fi
done < <(find "$PERS/publie" "$PERS/brut" -type f ! -name '.gitkeep' | sort)
echo "$N fichiers vérifiés, $ECARTS écart(s)"
[ "$ECARTS" -eq 0 ] && echo "OK  restauration identique" || { echo "ECHEC restauration"; exit 1; }
for j in $($NN hdfs dfs -ls -C "$BASE/publie" | grep -v SASL | xargs -n1 basename); do
  echo "version courante de $j : $($NN hdfs dfs -cat "$BASE/publie/$j/COURANT" 2>/dev/null | grep -v SASL)"
done
