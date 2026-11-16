These JSON service responses and native-output goldens are copied unchanged from
Phase 1's single-NLQ benchmark on codex/trapi-benchmarks (0b24011). They are
explicitly synthetic. case.json retains the original corpus attachment hash and
baseline identity. No biomedical assertion, historic count or live coverage is a
golden. composition.json adds explicit query mappings and a closed replay recipe
for that same question. It uses the existing filters/join, replacing input literals
with recorded-source references. Its source IDs hash the original requests and
responses. Structural empty-attribute additions are reported by the reducer.
