"""Declarative schema for asset assumptions files.

This module contains no I/O, no network access, and no model mathematics. It
defines the vocabulary of an ``assets/<asset_id>/assumptions.yaml`` file and the
frozen dataclasses that a validated file is parsed into. Enforcement lives in
:mod:`catalyst_rnpv.config`.
"""

from __future__ import annotations

import datetime
from collections.abc import Mapping
from dataclasses import dataclass

# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------

#: Keys permitted at the top level of an assumptions file.
TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {
        "asset_id",
        "asset_name",
        "company",
        "ticker",
        "catalyst",
        "parameters",
    }
)

#: Keys permitted inside the ``catalyst`` block.
CATALYST_KEYS: frozenset[str] = frozenset(
    {
        "trial_id",
        "description",
        "guided_date",
        "source_url",
    }
)

#: Fields every parameter entry must carry, exactly — no more, no fewer.
PARAMETER_FIELDS: frozenset[str] = frozenset(
    {
        "value",
        "unit",
        "distribution",
        "source_url",
        "source_type",
        "justification",
        "status",
        "as_of",
    }
)

#: Permitted provenance categories for a parameter.
SOURCE_TYPES: frozenset[str] = frozenset(
    {
        "sec_filing",
        "trial_registry",
        "publication",
        "cms_pricing",
        "fda_document",
        "icer_nice",
        "company_pr",
        "estimate",
    }
)

#: Permitted verification statuses for a parameter.
STATUSES: frozenset[str] = frozenset(
    {
        "VERIFIED",
        "UNVERIFIED",
        "ESTIMATE",
        "PLACEHOLDER",
    }
)

#: Distribution type -> the exact set of parameter names it requires.
DISTRIBUTION_PARAMS: Mapping[str, frozenset[str]] = {
    "point": frozenset(),
    "bernoulli": frozenset({"p"}),
    "beta": frozenset({"alpha", "beta"}),
    "pert": frozenset({"low", "mode", "high"}),
    "triangular": frozenset({"low", "mode", "high"}),
    "lognormal": frozenset({"mu", "sigma"}),
    "shifted_lognormal": frozenset({"shift", "mu", "sigma"}),
    "gamma": frozenset({"shape", "scale"}),
}

#: Keys permitted inside a ``distribution`` block.
DISTRIBUTION_KEYS: frozenset[str] = frozenset({"type", "params"})


# --------------------------------------------------------------------------
# Parsed representations
# --------------------------------------------------------------------------


class ConfigError(Exception):
    """Raised when an assumptions file is invalid.

    Carries every violation found, not just the first, in :attr:`errors`.
    """

    def __init__(self, errors: list[str]):
        self.errors: list[str] = list(errors)
        super().__init__("; ".join(self.errors) if self.errors else "invalid configuration")


@dataclass(frozen=True)
class Distribution:
    """An uncertainty distribution declared for a parameter."""

    type: str
    params: dict[str, float]


@dataclass(frozen=True)
class Parameter:
    """One validated parameter entry from an assumptions file."""

    key: str
    value: float | None
    unit: str
    distribution: Distribution | None
    source_url: str | None
    source_type: str
    justification: str
    status: str
    as_of: datetime.date | None


@dataclass(frozen=True)
class AssetConfig:
    """A fully validated assumptions file for a single asset."""

    asset_id: str
    asset_name: str
    company: str
    ticker: str
    catalyst: dict
    parameters: Mapping[str, Parameter]

    def param(self, key: str) -> Parameter:
        """Return the parameter entry for ``key``.

        Raises:
            KeyError: if ``key`` is not declared, naming the closest alternatives.
        """
        try:
            return self.parameters[key]
        except KeyError:
            known = sorted(self.parameters)
            near = [k for k in known if key in k or k in key]
            hint = f" Did you mean: {', '.join(near)}?" if near else ""
            raise KeyError(
                f"parameter {key!r} is not declared in asset {self.asset_id!r}."
                f"{hint} Declared parameters: {', '.join(known) if known else '(none)'}"
            ) from None

    def value(self, key: str) -> float:
        """Return the numeric value of ``key``.

        Raises:
            KeyError: if the parameter is not declared.
            ConfigError: if the parameter is a PLACEHOLDER or its value is null.
        """
        entry = self.param(key)
        if entry.status == "PLACEHOLDER":
            message = (
                f"{self.asset_id}.{key}: parameter is PLACEHOLDER and has no value; "
                "source it before use"
            )
            raise ConfigError([message])
        if entry.value is None:
            raise ConfigError([f"{self.asset_id}.{key}: value is null (status {entry.status})"])
        return float(entry.value)
