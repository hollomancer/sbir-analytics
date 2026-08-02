#!/usr/bin/env bash
# SAM.gov probe (v2, diagnostic) for the coverage-expansion SAM-only tasks.
# Run from a normal network (api.sam.gov is IP-blocked from the Claude Code hosted env).
#   export SAM_API_KEY=your_personal_sam_key ; ./sam_probe.sh
# Needs: bash, curl, jq.
set -uo pipefail
: "${SAM_API_KEY:?set SAM_API_KEY}"
FROM="${FROM:-01/01/2024}"   # MM/dd/yyyy, span <= 1 year
TO="${TO:-12/31/2024}"
OPP="https://api.sam.gov/opportunities/v2/search"

echo "== reachability =="
curl -sS -o /dev/null -w '   HTTP %{http_code}\n' \
  "$OPP?api_key=$SAM_API_KEY&postedFrom=$FROM&postedTo=$TO&limit=1"

echo
echo "== ptype census (where is the volume? is u really J&A?) =="
for pt in a o p k u s r i; do
  n=$(curl -sS "$OPP?api_key=$SAM_API_KEY&postedFrom=$FROM&postedTo=$TO&ptype=$pt&limit=1" \
        | jq -r '.totalRecords // "err"')
  printf '   ptype=%s  totalRecords=%s\n' "$pt" "$n"
done

echo
echo "== award notices (ptype=a): do their bodies self-label SBIR Phase III / 638? =="
curl -sS "$OPP?api_key=$SAM_API_KEY&postedFrom=$FROM&postedTo=$TO&ptype=a&limit=300" > awards.json
echo "   award notices pulled: $(jq -r '.opportunitiesData|length' awards.json) (of $(jq -r '.totalRecords' awards.json))"
jq -r '.opportunitiesData[]? | [.noticeId,(.title//""|gsub("[\t\n]";" ")),(.awardee.name//.award.awardee.name//""),.description] | @tsv' awards.json > awards_index.tsv
: > awards_638_hits.tsv
hits=0; checked=0
while IFS=$'\t' read -r nid title awardee descurl; do
  checked=$((checked+1))
  # title-level cheap check first
  hay="$title"
  # fetch body if it has a description URL
  if [ -n "${descurl:-}" ] && [[ "$descurl" == http* ]]; then
    hay="$hay $(curl -sS "${descurl}&api_key=$SAM_API_KEY" 2>/dev/null)"
  fi
  if printf '%s' "$hay" | grep -qiE "15 U\.?S\.?C\.? *638|section 638|\bSBIR\b|\bSTTR\b|phase *III"; then
    hits=$((hits+1)); printf '%s\t%s\t%s\n' "$nid" "$awardee" "$title" >> awards_638_hits.tsv
  fi
  sleep 0.1
done < <(head -300 awards_index.tsv)
echo "   SBIR/638-citing award notices: $hits / $checked checked  -> awards_638_hits.tsv"
echo "   (a healthy hit-count here = award notices are the self-labeling source, not J&As)"

echo
echo "== T4 OT: dump Contract Awards schema so we can fix the filter =="
AW="https://api.sam.gov/contract-awards/v1/search"
curl -sS "$AW?api_key=$SAM_API_KEY&limit=2" > ca_sample.json 2>/dev/null
echo "   top-level keys: $(jq -r 'keys? // "n/a"' ca_sample.json 2>/dev/null | tr '\n' ' ')"
echo "   first record fields (look for a contract-type / OT field):"
jq -r '(.contractData? // .results? // .awardData? // .[])[0]? | keys?' ca_sample.json 2>/dev/null | sed 's/^/     /' | head -40
echo "   (paste ca_sample.json's structure back and I'll build the OT query)"

echo
echo "Send back: the ptype census, the award-notice hit count (+ a few awardee/title rows),"
echo "and ca_sample.json's field list. That decides T1 (J&A vs award-notice) and fixes T4."
