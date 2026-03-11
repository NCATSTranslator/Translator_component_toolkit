"""Backward-compatibility shim. Use TCT.visualization instead."""
import warnings

warnings.warn(
    "TCT.TCT_Visualization is deprecated. Use TCT.visualization instead.",
    DeprecationWarning,
    stacklevel=2,
)
from .visualization import *  # noqa: E402, F401, F403
