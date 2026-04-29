"""Container class for the (APInames, metaKG, API_predicates) triplet."""

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class TranslatorResources:
    """Bundles the API names, meta knowledge graph, and API predicates used throughout TCT.

    This replaces the common pattern of passing ``(APInames, metaKG, API_predicates)``
    as three separate arguments.
    """

    api_names: dict[str, str]
    meta_kg: pd.DataFrame
    api_predicates: dict[str, list[str]] = field(default_factory=dict)
    kp_info: pd.DataFrame = field(default_factory=pd.DataFrame)

    @classmethod
    def load(cls) -> "TranslatorResources":
        """Load resources from Translator APIs (calls load_translator_resources internally)."""
        from .translator_metakg import load_translator_resources

        api_names, meta_kg, kp_info = load_translator_resources()

        api_with_metakg = list(set(meta_kg["API"]))
        api_predicates: dict[str, list[str]] = {}
        for api in api_with_metakg:
            api_predicates[api] = list(set(meta_kg[meta_kg["API"] == api]["Predicate"]))

        return cls(api_names=api_names, meta_kg=meta_kg, api_predicates=api_predicates, kp_info=kp_info)

    @classmethod
    def from_tuple(cls, triplet: tuple) -> "TranslatorResources":
        """Create from the legacy ``(APInames, metaKG, API_predicates)`` or 4-tuple."""
        if len(triplet) == 4:
            api_names, meta_kg, api_predicates, kp_info = triplet
            return cls(api_names=api_names, meta_kg=meta_kg, api_predicates=api_predicates, kp_info=kp_info)
        api_names, meta_kg, api_predicates = triplet
        return cls(api_names=api_names, meta_kg=meta_kg, api_predicates=api_predicates)

    def as_tuple(self) -> tuple:
        """Return the legacy ``(api_names, meta_kg, api_predicates)`` tuple."""
        return (self.api_names, self.meta_kg, self.api_predicates)

    def filter(self, api_list: list[str]) -> "TranslatorResources":
        """Return a new TranslatorResources scoped to the specified APIs."""
        filtered_names = {k: self.api_names[k] for k in api_list if k in self.api_names}
        filtered_kg = self.meta_kg[self.meta_kg["API"].isin(filtered_names.keys())]
        filtered_preds = {k: v for k, v in self.api_predicates.items() if k in filtered_names}
        return TranslatorResources(api_names=filtered_names, meta_kg=filtered_kg, api_predicates=filtered_preds)

    def rebuild_predicates(self) -> None:
        """Rebuild api_predicates from current meta_kg (call after mutating meta_kg)."""
        apis = list(set(self.meta_kg["API"]))
        self.api_predicates = {
            api: list(set(self.meta_kg[self.meta_kg["API"] == api]["Predicate"]))
            for api in apis
        }

    def __iter__(self):
        import warnings

        warnings.warn(
            "Unpacking TranslatorResources as a tuple is deprecated. "
            "Use the object directly: resources.api_names, resources.meta_kg, "
            "resources.api_predicates",
            DeprecationWarning,
            stacklevel=2,
        )
        yield self.api_names
        yield self.meta_kg
        yield self.api_predicates

    def __len__(self):
        return 3


def resolve_resources(resources, *, APInames=None, metaKG=None, API_predicates=None):
    """Resolve legacy kwargs into a TranslatorResources instance.

    Supports both the ``(APInames, metaKG, API_predicates)`` pattern
    used by ``TCT.py`` and the ``(APInames, API_predicates)`` pattern
    used by ``translator_query.py``.
    """
    if resources is not None and isinstance(resources, TranslatorResources):
        return resources
    if APInames is not None:
        import warnings

        warnings.warn(
            "Passing APInames/metaKG/API_predicates as separate arguments is deprecated. "
            "Use resources=TranslatorResources(...) instead.",
            DeprecationWarning,
            stacklevel=3,
        )
        return TranslatorResources(
            api_names=APInames,
            meta_kg=metaKG if metaKG is not None else pd.DataFrame(),
            api_predicates=API_predicates or {},
        )
    if resources is not None:
        raise TypeError("Expected TranslatorResources for 'resources'.")
    raise TypeError(
        "Either 'resources' or 'APInames'+'API_predicates' must be provided."
    )
