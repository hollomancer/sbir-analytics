# SBIR M&A Dated Signal Study — Source-Handling Review

> **Status:** Technical handling review completed 2026-08-30; not legal advice,
> not a license determination, and not an authorization to acquire SEC sources
> or release any artifact. It supports the owner decision recorded in the
> [freeze packet](freeze-packet.md).

## Official-source findings

| Source | Official operational finding | Required handling decision |
|---|---|---|
| SBIR.gov bulk awards | SBIR.gov states that award information is public, files are refreshed monthly, and the downloadable award file has more fields than the API. Its published policy also says that public award information excludes confidential business information. [Awards](https://www.sbir.gov/awards), [Data Resources](https://www.sbir.gov/data-resources), [Policy](https://www.sbir.gov/about/policies). | The downloaded file nevertheless contains contact, address, and abstract fields. Keep the raw file and any row-level derivative private; allowlist only the fields needed by a future approved method. Public availability does not authorize redistribution of a copied extract. Owner must decide whether even aggregate release is appropriate. |
| SEC Form D | The SEC describes Form D data as derived from filed structured data and Commission-generated identifiers, and says it assists analysis but is not a substitute for the filings. [Form D data](https://www.sec.gov/files/Form_D.pdf). | Retain identifiers and the exact business-combination predicate privately. Treat names and related-person data as restricted working data; do not redistribute rows or declare an ownership change from the predicate alone. |
| SEC EDGAR/EFTS | SEC describes EDGAR as public filing access but requires efficient, identified automation; its fair-access guidance caps a user at 10 requests/second and warns that unclassified bots may be blocked. [Developer Resources](https://www.sec.gov/about/developer-resources), [EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces). | Any later client must identify itself, stay below the stated limit, retrieve only necessary records, and retain accession/form/query/provenance privately. Matched filing text, issuer names, and audit rows remain non-public unless a later release decision says otherwise. |

## Prior-implementation reuse decision

The archived implementation established a useful *candidate-signal* pattern:

- Form D offerings marked as business combinations;
- EDGAR/EFTS mention search across `8-K`, `10-K`, `DEFM14A`, `PREM14A`,
  `SC TO-T`, and `SC 14D9`; and
- directional review that distinguishes an apparent target from a licensor,
  acquirer, comparator, or ambiguous mention.

Those are proposed inputs to a later frozen method only. The earlier implementation's
one-event-per-exact-company-name merge, hybrid earliest/last mention date, confidence tiers,
and historical JSONL are not reusable: the input and refinement artifacts are unavailable,
the name merge cannot establish a firm or deal, and the date is not a transaction date. This
is consistent with the existing [M&A signal-count design](../sbir-ma-match-rate-by-fy/design.md).

## Resulting status

The review supports a restricted, private handling plan but does **not** complete the
privacy/license/release-scope approval table. The owner must explicitly decide each source's
permitted retention, derived-audit, aggregate-release, and row-level-release scope before
the source/estimand contract can be frozen.
