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

    @classmethod
    def load(cls) -> "TranslatorResources":
        """Load resources from Translator APIs (calls load_translator_resources internally)."""
        from .translator_metakg import load_translator_resources

        api_names, meta_kg, _kp_info = load_translator_resources()

        api_with_metakg = list(set(meta_kg["API"]))
        api_predicates: dict[str, list[str]] = {}
        for api in api_with_metakg:
            api_predicates[api] = list(set(meta_kg[meta_kg["API"] == api]["Predicate"]))

        return cls(api_names=api_names, meta_kg=meta_kg, api_predicates=api_predicates)

    @classmethod
    def from_tuple(cls, triplet: tuple) -> "TranslatorResources":
        """Create from the legacy ``(APInames, metaKG, API_predicates)`` tuple."""
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
