"""catalyst_rnpv — pre-registered rNPV valuation research scaffolding.

This package currently contains the assumptions-file schema and its loader only.
No valuation model, simulation, or finance mathematics exists yet; it will be added
under its own modules once the pre-registration is complete.
"""

from catalyst_rnpv.config import load_asset_config, validate
from catalyst_rnpv.schema import AssetConfig, ConfigError, Distribution, Parameter

__version__ = "0.0.1"

__all__ = [
    "AssetConfig",
    "ConfigError",
    "Distribution",
    "Parameter",
    "load_asset_config",
    "validate",
]
