# Biotech Catalyst rNPV — pre-registered valuation research

**STATUS:** In progress — pre-registration pending; no results or investment views exist yet

A multi-asset framework for pre-registered, risk-adjusted net present value (rNPV)
valuation of clinical-stage biotech assets ahead of a named binary catalyst. Every
input is declared in a versioned `assets/<asset_id>/assumptions.yaml` file, with a
source URL, a source type, and a verification status, before any model code is run.

The first asset under study is Descartes-08 (Cartesian Therapeutics, NASDAQ: RNAC),
ahead of the Phase 3 AURORA readout in generalised myasthenia gravis
(NCT06799247, company-guided 1Q 2027).

## Repository layout

| Path | Contents |
| --- | --- |
| `assets/_template/` | Blank assumptions file defining the schema shape |
| `assets/<asset_id>/` | One folder per asset; the only asset-specific content |
| `src/catalyst_rnpv/` | Package: schema definition and config loader |
| `tests/` | Loader and validator tests |
| `docs/decision-log.md` | Dated, append-only record of design decisions |
| `data/` | Download manifest; `data/raw/` is gitignored |
| `scripts/` | Operational scripts |

## Assumptions files

Each parameter entry carries `value`, `unit`, `distribution`, `source_url`,
`source_type`, `justification`, `status`, and `as_of`. The loader collects every
schema and consistency violation in one pass rather than failing on the first, so a
file can be corrected in a single edit. See `src/catalyst_rnpv/schema.py` for the
authoritative field list and `src/catalyst_rnpv/config.py` for the rules.

```python
from catalyst_rnpv.config import load_asset_config

cfg = load_asset_config("rnac_descartes08")
cfg.param("discount_rate").status
```

## Methodology

_pending_

## Results

_pending_

## Limitations

Selection note: the asset screen deliberately targets maximal winner's-curse exposure; the analysis is therefore predisposed toward concluding market over-optimism, and results must be interpreted against that bias.

Further limitations will be recorded here as the pre-registration is finalised.

Research and educational artefact. Not investment advice.
