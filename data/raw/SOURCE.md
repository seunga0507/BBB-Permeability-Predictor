# Dataset Provenance: B3DB

- **Name**: B3DB (Blood-Brain Barrier Database)
- **Paper**: Meng, F., Xi, Y., Huang, J. et al. "A curated diverse molecular database of
  blood-brain barrier permeability with chemical descriptors." *Scientific Data* 8, 289 (2021).
  https://doi.org/10.1038/s41597-021-01069-5 (PMID: 34716354, PMCID: PMC8556334)
- **Repository**: https://github.com/theochem/B3DB
- **License**: CC0 1.0 (public domain dedication, as stated in the repository)
- **Compiled from**: 50 previously published literature/database sources (per repository description)

## File used

- `B3DB/B3DB_classification.tsv`
- Downloaded from GitHub at pinned tag **v1.1.1**, commit `75dab1cc607bb7a03f3de5c576cffd223e767844`
- Download URL: https://raw.githubusercontent.com/theochem/B3DB/75dab1cc607bb7a03f3de5c576cffd223e767844/B3DB/B3DB_classification.tsv
- Downloaded: 2026-09-23
- SHA-256: `47A160AEA1551423EAD2AAB70B301FB1646AEA03CF151FD614EB37C78FA55B82`
- Confirmed byte-identical to the `main` branch copy at time of download.

## Verified content (directly inspected, not taken from secondary sources)

- 7,807 compounds total, each with a `SMILES` and a categorical `BBB+/BBB-` label (0 missing SMILES).
- 4,956 labeled `BBB+`, 2,851 labeled `BBB-`.
- 1,058 of the 7,807 also carry a numeric `logBB` value (`group == 'A'`).
- `group` column (4 values, sizes as observed): `A` (1,058), `B` (3,621), `C` (3,077), `D` (51).
  The repository states this column characterizes "uncertainty of experimental measurements" across
  the combined literature sources. From the data itself:
  - Group **A** rows carry a measured numeric `logBB` value.
  - Group **B** rows carry `threshold == -1.0`, i.e. their BBB+/BBB- label was derived by applying
    the classical logBB >= -1 cutoff (a threshold widely used in the BBB permeability literature)
    to a converted/estimated logBB value.
  - Group **C** rows have no numeric `logBB` or `threshold` value, consistent with their original
    source reporting only a qualitative BBB+/BBB- call.
  - Group **D** (51 rows) is a small residual group; its exact per-source curation notes are
    documented in the source paper's methods/supplementary material, which was not fully accessible
    during this review — it is kept in the dataset as-is rather than guessed at.
- Columns: `NO.`, `compound_name`, `IUPAC_name`, `SMILES`, `CID`, `logBB`, `BBB+/BBB-`, `Inchi`,
  `threshold`, `reference`, `group`, `comments`.

## Endpoint / label definition used in this project

- **Task**: binary classification of blood-brain barrier permeability.
- **Endpoint**: `BBB+/BBB-` column, mapped to `1` (BBB+, permeant) / `0` (BBB-, non-permeant).
- We use the full classification file (all 7,807 curated compounds, all groups), since that is the
  file the B3DB authors distribute specifically for classification tasks. We do not fabricate or
  re-derive labels; rows with an unparseable SMILES are dropped (see `ml/dataset.py`).
