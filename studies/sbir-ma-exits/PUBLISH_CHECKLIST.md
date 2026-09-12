# Zenodo v1 human publication checklist

Human action only. This branch does not create or publish a Zenodo record.

## Publication gate

The repository inventory classifies the M&A rate and timing findings as a dated research note. It says they are not approved for citation as evidence. This package adds an exploratory study contract and a public-preprint format. It does not validate the findings. The human publisher must accept that status before deposit.

## Exact publication steps

1. Log in to Zenodo with the account that will own the record.
2. Create a new upload for a publication and choose `Preprint`.
3. Reserve the DOI before uploading the final PDF.
4. Replace the DOI placeholder token `10.5281/zenodo.XXXXXXX` in
   `studies/sbir-ma-exits/paper.md` with the reserved DOI. It occurs exactly
   twice: the page footer and the title-page deposit status. Do not
   search-and-replace `[UNVERIFIED — human review]`; that marker labels other
   unverified items, not the DOI. Then recompute the hash and update
   `frozen_artifacts` in `studies/sbir-ma-exits/study.yaml`, or
   `scripts/ci/validate_study_manifests.py` fails on the publish commit:

   ```bash
   sha256sum studies/sbir-ma-exits/paper.md
   ```
5. Do not add the DOI to `CITATION.cff`. That file declares no
   `preferred-citation` on purpose. The paper is exploratory, and
   `preferred-citation` tells citation software to cite the paper instead of
   the repository. Leave the field absent.
6. Rebuild the PDF from the repository root:

   ```bash
   pandoc studies/sbir-ma-exits/paper.md \
     --pdf-engine=xelatex \
     --output studies/sbir-ma-exits/paper.pdf
   ```

   Then confirm the build actually ran, rather than depositing a placeholder:

   ```bash
   head -c 200 studies/sbir-ma-exits/paper.pdf
   ```

   The output must not report `ReportLab Generated PDF document`. Confirm
   `M&A` renders as `M&A` and not `M & A`, and that the repository URL in the
   Appendix A table is not broken across a line.

7. Render and inspect every PDF page. Confirm the DOI footer, page numbers, tables, links, and disclaimer.
8. Enter the record metadata from `studies/sbir-ma-exits/zenodo.json`.
9. Set the publication date to the actual human deposit date.
10. Confirm the author is `Conrad Hollomon`, with `Independent researcher` only.
11. Confirm the personal email is `hollomancer@protonmail.ch`.
12. Confirm the exact sentence appears in the record and PDF: "This work was conducted in a personal capacity and does not represent the position of any agency."
13. Select `CC BY 4.0` for the paper. Do not change the repository code license from MIT.
14. Confirm the exact sentence appears in the record description, the record notes, and the PDF title page: "This package preserves a dated, exploratory repository finding. It does not promote the analysis to validated or citable evidence under the repository's study rules."
15. Add the GitHub repository as the related identifier with relation `isSupplementedBy`.
16. Upload `studies/sbir-ma-exits/paper.pdf` as the paper file.
17. Preview the public record. Check title, abstract, keywords, version `1.0.0`, license, author, and related identifier.
18. Publish the Zenodo record.
19. After publication, verify that the DOI resolves and matches the PDF footer.

## Collected unverified items

- `10.5281/zenodo.XXXXXXX` Reserved Zenodo DOI placeholder in `paper.md`. It does not exist until a human reserves it.
- `[UNVERIFIED — human review]` Final out-of-sample false-positive rate for accepted M&A detections. The committed diagnostics do not supply this value.
- `[UNVERIFIED — human review]` Exact frozen input snapshot and hash for the 34,460-firm denominator. The committed documents state the denominator, but the input bytes are not committed.
