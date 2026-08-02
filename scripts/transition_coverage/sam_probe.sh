#!/usr/bin/env bash
# SAM.gov probe for the two SAM-only coverage tasks (spec: transition-coverage-expansion).
#
# RUN FROM A NORMAL NETWORK — NOT the Claude Code hosted sandbox. api.sam.gov returns an
# empty HTTP 404 from that environment's IP (confirmed: persists even with the bash sandbox
# fully disabled, so it's a source-IP / SAM-edge block, not a Claude Code setting).
#
#   export SAM_API_KEY=your_personal_sam_key   # from SAM.gov > Account Details > API Key
#   ./sam_probe.sh
#
# Needs: bash, curl, jq. Writes artifacts to the current directory.
set -euo pipefail
: "${SAM_API_KEY:?set SAM_API_KEY to your SAM.gov personal API key}"
FROM="${FROM:-01/01/2024}"     # MM/dd/yyyy — span MUST be <= 1 year
TO="${TO:-12/31/2024}"
OPP="https://api.sam.gov/opportunities/v2/search"

echo "== sanity: is api.sam.gov reachable from here? =="
code=$(curl -sS -o /dev/null -w '%{http_code}' \
  "$OPP?api_key=$SAM_API_KEY&postedFrom=$FROM&postedTo=$TO&limit=1" || true)
echo "   HTTP $code   (200 = good; 404/empty = still blocked/IP issue; 403 = bad/expired key)"
[ "$code" = "200" ] || { echo "   -> not reachable with a valid response; stop here and check network/key."; exit 1; }

echo
echo "== T1: Justification & Approval (J&A) notices, ptype=u =="
# The Get Opportunities API has no full-text param, so: list J&As, then fetch each
# description body and flag the ones that cite 15 U.S.C. 638 / SBIR Phase III (self-label).
curl -sS "$OPP?api_key=$SAM_API_KEY&postedFrom=$FROM&postedTo=$TO&ptype=u&limit=1000" > jna.json
echo "   J&A notices in window: $(jq -r '.totalRecords' jna.json)"
jq -r '.opportunitiesData[]? | [.noticeId, (.title|gsub("[\t\n]";" ")), .description] | @tsv' jna.json > jna_index.tsv
echo "   indexed $(wc -l < jna_index.tsv) notices -> jna_index.tsv"

: > jna_638_hits.tsv
while IFS=$'\t' read -r nid title descurl; do
  [ -z "${descurl:-}" ] && continue
  # .description is the noticedesc URL; it already carries ?noticeid=, so append &api_key=
  body=$(curl -sS "${descurl}&api_key=$SAM_API_KEY" 2>/dev/null || true)
  if printf '%s' "$body" | grep -qiE "15 U\.?S\.?C\.? *638|section 638|\bSBIR\b.*phase *III|phase *III.*\bSBIR\b|STTR"; then
    printf '%s\t%s\n' "$nid" "$title" >> jna_638_hits.tsv
  fi
  sleep 0.2
done < jna_index.tsv
echo "   J&As citing SBIR Phase III / 638: $(wc -l < jna_638_hits.tsv)  -> jna_638_hits.tsv"
echo "   (that hit-rate + whether the body was retrievable = the T1 go/no-go on §638-J&A as a self-labeling source)"

echo
echo "== T4: Other Transaction (OT) award data, Contract Awards API =="
# NOTE: param schema UNVERIFIED (SAM was blocked when this was authored). Confirm field
# names at https://open.gsa.gov/api/contract-awards/ and adjust the filter below.
AW="https://api.sam.gov/contract-awards/v1/search"
curl -sS "$AW?api_key=$SAM_API_KEY&limit=25&idvType=Other%20Transaction%20Order" > ot_awards.json 2>/dev/null \
  && echo "   wrote ot_awards.json ($(jq -r '.totalRecords // "?"' ot_awards.json 2>/dev/null) records)" \
  || echo "   Contract Awards query needs param tuning — see the doc link above; inspect ot_awards.json"

echo
echo "Done. Send back: jna.json totalRecords, jna_638_hits.tsv (count + a few titles),"
echo "and whether ot_awards.json returned OT records. That decides T1/T4."
