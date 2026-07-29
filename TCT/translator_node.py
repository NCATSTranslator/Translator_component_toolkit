# translator graph node
from dataclasses import dataclass
import typing

@dataclass
class TranslatorAttribute:
    """
    Class that represents Translator node or edge attributes
    """

    attribute_type_id: str

    value: typing.Any

    value_type_id: str | None = None

    original_attribute_name: str | None = None

    value_url: str | None = None

    attribute_source: str | None = None

    description: str | None = None

    attributes: list | None = None



@dataclass
class TranslatorNode:
    """
    Class for Translator graph nodes.
    """

    curie: str
    "CURIE identifier"

    label: str | None = None
    "human-readable name for the node"

    types: list[str] | None = None
    "list of biolink types"

    # TODO: add quantifiers/qualifiers?
    # TODO: add edges too?

    synonyms: list[str] | None = None
    "list of synonymous labels"

    curie_synonyms: list[str] | None = None
    "list of synonymous CURIE ids (in the same order as synonyms)"

    attributes: list[TranslatorAttribute] | None = None
    "List of node attributes (which are key-value pairs."

    taxa: list[str] | None = None
    "List of taxa for the given node (i.e. 'NCBITaxon:9606')"

    # identifier is just another way to access/set the CURIE.
    @property
    def identifier(self):
        """identifier is the CURIE id for the node."""
        return self.curie

    @identifier.setter
    def identifier(self, i):
        """identifier is the CURIE id for the node."""
        self.curie = i

    @property
    def categories(self):
        return self.types

    @property
    def name(self):
        """name is an alias for the human-readable label."""
        return self.label

    @classmethod
    def from_dict(cls, data_dict:dict, return_synonyms=False):
        """Creates a TranslatorNode object from a data dict."""
        if 'curie' not in data_dict:
            raise ValueError('The input data dict must have a "curie" key.')
        n = cls(data_dict['curie'])
        if 'label' in data_dict:
            n.label = data_dict['label']
        if 'types' in data_dict:
            # Do the types have the `biolink:` prefix? If not, add them.
            n.types = list(map(lambda ty: f"biolink:{ty}" if not ty.startswith('biolink:') else ty, data_dict['types']))
        if 'taxa' in data_dict:
            n.taxa = data_dict['taxa']
        if return_synonyms:
            if 'synonyms' in data_dict:
                n.synonyms = data_dict['synonyms']
            elif 'names' in data_dict:
                # NameRes refers to synonyms as "names".
                n.synonyms = data_dict['names']
        return n



@dataclass
class TranslatorEdge:
    """
    Class that represents Translator edges.
    """

    subject: str
    "The subject is a CURIE id for a node."

    object: str
    "The obj (object) is a CURIE id for a node."

    predicate: str
    "Predicates"

    sources: list | None = None

    attributes: list[TranslatorAttribute] | None = None
