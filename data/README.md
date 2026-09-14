# Data

Raw downloads are not committed. `data/raw/` is gitignored except for its
`.gitkeep`, so the repository stays small and never redistributes third-party
documents. What *is* committed is `manifest.yaml`: the reproducibility record that
lets someone else fetch the same bytes and confirm they match.

## The rule

Every file placed in `data/raw/` gets one entry in `data/manifest.yaml`. A file with
no manifest entry is not evidence and may not be cited in an assumptions file.

## Entry format

Each entry has exactly these fields:

| Field | Meaning |
| --- | --- |
| `name` | The filename as stored under `data/raw/` |
| `url` | The exact URL the file was retrieved from |
| `retrieved` | ISO date (YYYY-MM-DD) of retrieval |
| `sha256` | SHA-256 of the file as downloaded, unmodified |
| `notes` | What the file is, and which parameters it supports |

```yaml
- name: rnac-10q-2026q2.pdf
  url: https://www.sec.gov/Archives/edgar/data/.../rnac-10q.pdf
  retrieved: 2026-09-14
  sha256: 0000000000000000000000000000000000000000000000000000000000000000
  notes: Quarterly report; supports net_cash, debt, shares_as_converted.
```

## Recording a download

```sh
shasum -a 256 data/raw/<file>     # macOS
sha256sum data/raw/<file>         # Linux
```

Paste the digest into the manifest entry alongside the URL and the retrieval date.
Never edit a file in `data/raw/` after hashing it; if a document is superseded,
download the new version under a new name and add a new entry.

## Why the hash matters

Source documents move, get revised, and disappear. The hash is what distinguishes
"the page changed after I cited it" from "I misread it", which is the difference
between a reproducible pre-registration and an unfalsifiable one.
