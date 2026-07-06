# bizfileOnline JSON API — Captured Endpoints

Reverse-engineered 2026-05-16 via Chrome DevTools (Playwright MCP) on
`bizfileonline.sos.ca.gov`. Used by the UCC-1 pilot (`sbir_etl/ucc/`).
All endpoints are public — no authentication header observed.

## UCC search

```
POST https://bizfileonline.sos.ca.gov/api/Records/uccsearch
Content-Type: application/json

{
  "SEARCH_VALUE": "<debtor or secured party name>",
  "STATUS": "ALL",            // | "ACTIVE_UNLAPSED" | "ACTIVE_ALL"
  "RECORD_TYPE_ID": "0",      // "0" = All; "2170" = Financing Statement
  "FILING_DATE": {"start": null, "end": null},
  "LAPSE_DATE": {"start": null, "end": null}
}
```

Response:

```json
{
  "template": [
    {"label": "UCC Type", "id": "RECORD_TYPE"},
    {"label": "Debtor Information", "id": "TITLE"},
    {"label": "File Number", "id": "RECORD_NUM"},
    {"label": "Secured Party Info", "id": "SEC_PARTY"},
    {"label": "Status", "id": "STATUS"},
    {"label": "Filing Date", "id": "FILING_DATE"},
    {"label": "Lapse Date", "id": "LAPSE_DATE"}
  ],
  "rows": {
    "<internal_id>": {
      "SORT_INDEX": 0,
      "ID": 1752168,                                      // internal row ID
      "RECORD_NUM": "197728978614",                       // filing number
      "RECORD_TYPE": "Notice of State Tax Lien",
      "TITLE": ["INHIBRX, INC. - LA JOLLA, CA"],          // debtor (one or more)
      "SEC_PARTY": ["EMPLOYMENT DEVELOPMENT DEPARTMENT - SACRAMENTO, CA"],
      "STATUS": "Active",
      "FILING_DATE": "08/20/2019",
      "LAPSE_DATE": "08/20/2029",
      "ALERT": false
    }
  },
  "edge": {"offset": 0, "limit": 100, "total": 1}
}
```

**Important**: free-text `SEARCH_VALUE` matches against BOTH debtor and
secured-party fields. Debtor-side filtering is the responsibility of the
matcher.

**File Type IDs** (Advanced filter `RECORD_TYPE_ID`):

| Display label | ID |
|---|---|
| All | `0` |
| Financing Statement | `2170` |
| Judgment Lien | unknown (not captured; capture if needed) |
| State Tax Lien | unknown |
| Federal Tax Lien | unknown |
| Attachment | unknown |

## Filing detail

```
GET https://bizfileonline.sos.ca.gov/api/FilingDetail/ucc/{ID}/false
```

where `{ID}` is the `ID` field from a search row (internal id), not
`RECORD_NUM`. The trailing `/false` toggles inclusion of certified-copy
metadata; pilot uses `/false`.

Response:

```json
{
  "DRAWER_DETAIL_LIST": [
    {"LABEL": "Debtor Name",          "VALUE": "INHIBRX, INC.",                                        "TYPE": null, "LINKLABEL": null, "ALERT_YN": false, "TITLE": null, "MODAL_SIZE": null},
    {"LABEL": "Debtor Address",       "VALUE": "11025 N TORREY PINES RD STE 200, LA JOLLA, CA  920371030", ...},
    {"LABEL": "Secured Party Name",   "VALUE": "EMPLOYMENT DEVELOPMENT DEPARTMENT", ...},
    {"LABEL": "Secured Party Address","VALUE": "722 CAPITOL MALL, SACRAMENTO, CA  95814", ...}
  ],
  "AR_BUTTON_LABEL": null,
  "HIDE_CERT_BUTTON": true,
  "HIDE_REQUEST_ACCESS": false,
  "HIDE_HISTORY": false,
  "HIDE_AMENDMENT_BUTTON": true,
  "CERT_BUTTON_REDIRECTS_TO": null
}
```

## History (UCC-3 lifecycle)

```
GET https://bizfileonline.sos.ca.gov/api/History/ucc/{RECORD_NUM}
```

where `{RECORD_NUM}` is the file number (e.g., `197728978614`).

Response:

```json
{
  "AMENDMENT_LIST": [
    {
      "AMENDMENT_TYPE": "Lien Financing Stmt",
      "AMENDMENT_NUM":  "197728978614",
      "AMENDMENT_DATE": "8/20/2019",
      "DOWNLOAD_LINK":  "/api/report/GetImageByNum/250129160006229131128234092177080232043021072164"
    },
    {
      "AMENDMENT_TYPE": "Termination",
      "AMENDMENT_NUM":  "1977361234",
      "AMENDMENT_DATE": "9/23/2019",
      "DOWNLOAD_LINK":  "/api/report/GetImageByNum/243205054237248135168140249024054205041249027000"
    }
  ],
  "HISTORY_LIST": [],
  "TEMPLATE": [
    {"id": "AMENDMENT_TYPE", "label": "Document Type"},
    {"id": "AMENDMENT_NUM",  "label": "File Number"},
    {"id": "AMENDMENT_DATE", "label": "Date"},
    {"id": "DOWNLOAD_LINK",  "label": "Image Download", "type": "download"}
  ]
}
```

**Mapping from `AMENDMENT_TYPE` to `FilingType`** (see `schema.py`):

| AMENDMENT_TYPE | FilingType |
|---|---|
| `Lien Financing Stmt` | `INITIAL` |
| `Amendment` | `AMENDMENT` |
| `Continuation` | `CONTINUATION` |
| `Assignment` | `ASSIGNMENT` |
| `Termination` | `TERMINATION` |

The earliest "Lien Financing Stmt" in the list is the anchor; all other
entries are UCC-3 events whose `parent_filing_number` is the anchor's
`AMENDMENT_NUM`.

## Business search (used by CohortStateFilter)

```
POST https://bizfileonline.sos.ca.gov/api/Records/businesssearch
Content-Type: application/json

{
  "SEARCH_VALUE": "<entity name>",
  "SEARCH_FILTER_TYPE_ID": "0",
  "SEARCH_TYPE_ID": "1",
  "FILING_TYPE_ID": "",
  "STATUS_ID": "",
  "FILING_DATE": {"start": null, "end": null},
  "CORPORATION_BANKRUPTCY_YN": false,
  "CORPORATION_LEGAL_PROCEEDINGS_YN": false,
  "OFFICER_OBJECT": {"FIRST_NAME": "", "MIDDLE_NAME": "", "LAST_NAME": ""},
  "NUMBER_OF_FEMALE_DIRECTORS": "99",
  "NUMBER_OF_UNDERREPRESENTED_DIRECTORS": "99",
  "COMPENSATION_FROM": "",
  "COMPENSATION_TO": "",
  "SHARES_YN": false,
  "OPTIONS_YN": false,
  "BANKRUPTCY_YN": false,
  "FRAUD_YN": false,
  "LOANS_YN": false,
  "AUDITOR_NAME": ""
}
```

The padding fields are required by the server even when unused. Minimum
viable payload is the above with `SEARCH_VALUE` filled in.

Response:

```json
{
  "template": [
    {"label": "Entity Information", "id": "TITLE"},
    {"label": "Initial Filing Date", "id": "FILING_DATE"},
    {"label": "Status", "id": "STATUS"},
    {"label": "Entity Type", "id": "ENTITY_TYPE"},
    {"label": "Formed In", "id": "FORMED_IN"},
    {"label": "Agent", "id": "AGENT"}
  ],
  "rows": {
    "<id>": {
      "SORT_INDEX": 0,
      "TITLE": ["INHIBRX BIOSCIENCES, INC. (6195284)"],
      "ID": 8440338,
      "FILING_DATE": "03/29/2024",
      "FORMED_IN": "DELAWARE",                              // jurisdiction
      "AGENT": "...",
      "STATUS": "Active",
      "ENTITY_TYPE": "Stock Corporation - Out of State - Stock",
      "STANDING": "Good Standing",
      ...
    }
  }
}
```

### Rule for "CA-organized"

```python
def is_ca_organized(record: dict) -> bool:
    formed_in = (record.get("FORMED_IN") or "").upper()
    entity_type = (record.get("ENTITY_TYPE") or "").lower()
    return formed_in == "CALIFORNIA" and "out of state" not in entity_type
```

Empirical confirmation: searching "Inhibrx" returns 16 entities, ALL
formed in Delaware (mix of LLCs, LPs, Stock Corp out-of-state). None
qualify as CA-organized — consistent with Inhibrx's actual incorporation
in Delaware, and consistent with the Phase 0 finding that CA-HQ but
DE-incorporated firms are invisible to CA UCC-1 records.

## Filing PDF download

```
GET https://bizfileonline.sos.ca.gov/api/report/GetImageByNum/{TOKEN}
```

Returns the filing PDF. `{TOKEN}` is the opaque value from
`AMENDMENT_LIST[].DOWNLOAD_LINK`. No auth required. Not used by the pilot
analysis itself; useful for manual precision review (Task H3).

## Headers, throttling, anti-bot

- **No authentication** observed on any endpoint
- **`Content-Type: application/json`** required for POSTs
- **Cookies set on first request**: `_d_id` (anti-bot ID), `incap_ses_*`
  (Imperva session) — `httpx.Client` with default cookie jar handles
  these transparently
- **Server**: ASP.NET / Microsoft-IIS/10.0 fronted by Imperva CDN
  (`x-cdn: Imperva` header)
- **Rate limit observed**: ~10 requests / 25 minutes during Phase 0 — no
  429 hit. Production extractor uses 1 req/sec conservative throttle.

## Cookie initialization

Some clients may receive a CSRF/anti-bot challenge on first POST without
cookies. Workaround: issue one GET to the search page before the first
POST so cookies seed:

```python
client = httpx.Client(timeout=30.0, follow_redirects=True)
client.get("https://bizfileonline.sos.ca.gov/search/ucc")  # seed cookies
client.post("https://bizfileonline.sos.ca.gov/api/Records/uccsearch", json=payload)
```

Implementer should test whether the first POST succeeds cold — if not,
add the priming GET.
