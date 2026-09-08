# Actions Migration Follow-ups — Requirements

**Target epistemic tier:** `pipelines`

- **Research question:** none directly. Operational obligation: the scheduled GitHub Actions
  workflows were retired along with the deterministic repository and setup checks they ran.
  This spec restores those checks so repository hygiene stays a measured fact rather than an
  asserted policy. It answers no inventory question in
  [docs/research-questions.md](../../docs/research-questions.md).

This operational spec restores deterministic repository and setup checks after
the scheduled GitHub Actions workflows were retired. The detailed decisions and
acceptance evidence remain in:

- [repo-checks-restoration.md](repo-checks-restoration.md)
- [setup-script-verification.md](setup-script-verification.md)
