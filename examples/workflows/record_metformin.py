"""Record a bounded metformin query against explicit CI services and replay it."""

import argparse
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

import pandas as pd

import TCT
from TCT.evidence import read_run
from TCT.interfaces.serialization import to_jsonable


RUN_ID = "metformin"
BUDGET_BYTES = 50_000_000
PREDICATE = "biolink:treats"
DRUG = "biolink:Drug"
DISEASE = "biolink:Disease"


def ci_url(value):
    """Require an explicit, public CI endpoint."""
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(".ci.transltr.io")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise argparse.ArgumentTypeError("Expected a public HTTPS CI service URL")
    return value


def find(normalizer, providers):
    TCT.configure(
        environment="ci",
        overrides={
            "name_resolver": "https://name-lookup.ci.transltr.io/",
            "node_normalizer": normalizer,
        },
    )
    api_names = {
        f"provider-{index}": url for index, url in enumerate(providers, start=1)
    }
    return TCT.neighborhood_finder(
        "metformin",
        ["Disease"],
        node_categories=["Drug"],
        predicates_subset=[PREDICATE],
        resources=TCT.TranslatorResources(
            api_names=api_names,
            meta_kg=pd.DataFrame(
                [
                    {
                        "API": name,
                        "Predicate": PREDICATE,
                        "Subject": DRUG,
                        "Object": DISEASE,
                        "URL": url,
                    }
                    for name, url in api_names.items()
                ]
            ),
            api_predicates={name: [PREDICATE] for name in api_names},
        ),
    )


def record(store, normalizer, providers):
    store.mkdir(mode=0o700)
    manifest = {"normalizer": normalizer, "providers": providers}
    (store / "query.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with TCT.execution(
        {
            "store": str(store),
            "run_id": RUN_ID,
            "record": True,
            "cache": True,
            "langfuse": False,
        }
    ):
        result = find(**manifest)
    size = sum(file.stat().st_size for file in store.rglob("*") if file.is_file())
    edge_count = len(result.knowledge_graph["edges"])
    print(f"Recorded {edge_count} edges in {size:,} bytes.")
    if not edge_count or size >= BUDGET_BYTES:
        print(
            "The recording needs at least one edge and must be under 50 MB.",
            file=sys.stderr,
        )
        return 1
    return 0


def verify(store):
    manifest = json.loads((store / "query.json").read_text())
    runs = read_run(store, RUN_ID)
    (captured,) = [
        event
        for event in runs
        if event["operation"] == "neighborhood_finder"
        and event["status"] == "succeeded"
        and event["parent_call_id"] is None
    ]
    with TCT.execution(
        {
            "store": str(store),
            "cache": {"mode": "replay", "snapshot_run": RUN_ID},
            "langfuse": False,
        }
    ):
        result = find(**manifest)
    if captured["output"] != to_jsonable(result):
        raise ValueError("Replay result differs from the recorded finder output")
    print("Offline replay matched the recorded result.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("record", help="Send live requests to CI services.")
    capture.add_argument("store", type=Path, help="New output directory.")
    capture.add_argument("--normalizer", required=True, type=ci_url)
    capture.add_argument("--provider", action="append", required=True, type=ci_url)
    replay = commands.add_parser("verify", help="Replay an existing recording offline.")
    replay.add_argument("store", type=Path)
    args = parser.parse_args(argv)
    if args.command == "verify":
        return verify(args.store)
    if len(args.provider) > 2 or len(args.provider) != len(set(args.provider)):
        capture.error("Provide one or two distinct provider URLs")
    return record(args.store, args.normalizer, args.provider)


if __name__ == "__main__":
    raise SystemExit(main())
