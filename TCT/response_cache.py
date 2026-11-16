"""Opt-in HTTP response reuse. Imported only when execution caching is enabled.

Only JSON object key order is canonicalized. Arrays, query IDs, predicate order,
URLs, and literal values retain their meaning. Snapshots are not answer proofs.
"""

from base64 import b64decode, b64encode
from collections import defaultdict
from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from threading import RLock
import time

import requests

from .config import get_runtime_config
from .execution import ExecutionRecordingError
from .journal import ArtifactStore

POLICY_VERSION = "tct.http-cache.v1"
CANONICALIZER_VERSION = "json-object-order.v1"
DEFAULT_TTL = {"normalization": 86400, "capabilities": 3600, "trapi": 900}


class CacheError(ExecutionRecordingError):
    """Requested caching failed; must not be mistaken for an empty answer."""


class CacheReplayError(CacheError):
    """A snapshot was absent, exhausted, or damaged. Never falls back to HTTP."""


def canonical_bytes(value):
    def require_json(item):
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise TypeError("Cache identity requires string JSON object keys")
            for child in item.values():
                require_json(child)
        elif isinstance(item, list):
            for child in item:
                require_json(child)
        elif item is not None and type(item) not in (str, bool, int, float):
            raise TypeError("Cache identity requires JSON-compatible request options")

    require_json(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def validate_policy(value, *, partial=False):
    if value is True:
        value = {}
    allowed = {
        "mode",
        "scope",
        "authorization_partition",
        "dataset_versions",
        "epoch",
        "ttl",
        "snapshot_run",
    }
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError("cache must be a boolean or a cache policy object")
    policy = {
        "mode": "use",
        "scope": "run",
        "dataset_versions": {},
        "epoch": "default",
        "ttl": DEFAULT_TTL.copy(),
    } | value
    if policy["mode"] not in ("use", "refresh", "bypass", "replay"):
        raise ValueError("cache.mode must be use, refresh, bypass, or replay")
    if policy["scope"] not in ("run", "cross_run"):
        raise ValueError("cache.scope must be run or cross_run")
    for name in ("epoch", "authorization_partition", "snapshot_run"):
        if name in policy and (
            not isinstance(policy[name], str) or not policy[name].strip()
        ):
            raise ValueError(f"cache.{name} must be a nonempty string")
    versions = policy["dataset_versions"]
    if not isinstance(versions, dict) or any(
        not isinstance(k, str) or not k or not isinstance(v, str) or not v
        for k, v in versions.items()
    ):
        raise ValueError("cache.dataset_versions must map dependency names to versions")
    ttl = policy["ttl"]
    if (
        not isinstance(ttl, dict)
        or set(ttl) - set(DEFAULT_TTL)
        or any(
            type(v) not in (int, float) or not math.isfinite(v) or v < 0
            for v in ttl.values()
        )
    ):
        raise ValueError(
            "cache.ttl must contain finite, nonnegative seconds by service kind"
        )
    policy["ttl"] = DEFAULT_TTL | ttl
    if not partial and policy["mode"] == "replay" and not policy.get("snapshot_run"):
        raise ValueError("cache replay requires snapshot_run")
    if not partial and policy["mode"] != "replay" and "snapshot_run" in policy:
        raise ValueError("snapshot_run is only valid in replay mode")
    if (
        not partial
        and policy["scope"] == "cross_run"
        and not policy.get("authorization_partition")
    ):
        raise ValueError(
            "cross-run caching requires an explicit authorization_partition"
        )
    return json.loads(canonical_bytes(policy))


class CacheStore(ArtifactStore):
    def __init__(self, root, *, readonly=False):
        self.readonly = readonly
        if readonly:
            self.root = Path(root).expanduser().resolve()
            self.artifacts = self.root / "artifacts"
        else:
            super().__init__(root)
            with self.connect() as db:
                db.executescript("""
                    CREATE TABLE IF NOT EXISTS entries (
                        namespace TEXT NOT NULL, key TEXT NOT NULL,
                        artifact TEXT NOT NULL, expires REAL,
                        PRIMARY KEY(namespace, key));
                    CREATE TABLE IF NOT EXISTS history (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        run_id TEXT NOT NULL, key TEXT NOT NULL,
                        artifact TEXT, receipt TEXT NOT NULL);
                    CREATE INDEX IF NOT EXISTS history_run ON history(run_id, sequence);
                """)

    @contextmanager
    def connect(self):
        path = self.root / "cache.sqlite3"
        db = (
            sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=30)
            if self.readonly
            else sqlite3.connect(path, timeout=30)
        )
        try:
            with db:
                yield db
        finally:
            db.close()

    def read(self, artifact):
        if (
            not isinstance(artifact, str)
            or len(artifact) != 64
            or any(c not in "0123456789abcdef" for c in artifact)
        ):
            raise ValueError("Invalid cache artifact digest")
        raw = (self.artifacts / artifact).read_bytes()
        if hashlib.sha256(raw).hexdigest() != artifact:
            raise ValueError("Cache artifact checksum mismatch")
        return json.loads(raw)

    def lookup(self, namespace, key, now):
        with self.connect() as db:
            row = db.execute(
                "SELECT artifact, expires FROM entries WHERE namespace=? AND key=?",
                (namespace, key),
            ).fetchone()
        if row and (row[1] is None or row[1] > now):
            return self.read(row[0])
        return None

    def save(self, run_id, key, snapshot, receipt, *, pin, shared_expiry):
        artifact = self.artifact(snapshot) if snapshot is not None else None
        receipt["snapshot_hash"] = artifact
        with self.connect() as db:
            if pin:
                db.execute(
                    "INSERT OR REPLACE INTO entries VALUES (?, ?, ?, NULL)",
                    ("run:" + run_id, key, artifact),
                )
            if shared_expiry is not None:
                db.execute(
                    "INSERT OR REPLACE INTO entries VALUES ('shared', ?, ?, ?)",
                    (key, artifact, shared_expiry),
                )
            db.execute(
                "INSERT INTO history(run_id, key, artifact, receipt) VALUES (?, ?, ?, ?)",
                (run_id, key, artifact, canonical_bytes(receipt).decode()),
            )

    def history(self, run_id):
        with self.connect() as db:
            return db.execute(
                "SELECT key, artifact FROM history WHERE run_id=? ORDER BY sequence",
                (run_id,),
            ).fetchall()

    def take_replay(self, run_id, source_run, key, artifacts):
        # Keep the source index read-only. A separate transactional cursor makes
        # separate CLI processes/MCP calls consume the same replay deterministically.
        db = sqlite3.connect(self.root / "replay.sqlite3", timeout=30)
        try:
            with db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS cursors (run_id TEXT, source_run TEXT, key TEXT, consumed INTEGER NOT NULL, PRIMARY KEY(run_id, source_run, key))"
                )
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT consumed FROM cursors WHERE run_id=? AND source_run=? AND key=?",
                    (run_id, source_run, key),
                ).fetchone()
                index = row[0] if row else 0
                if index >= len(artifacts):
                    raise ValueError("No remaining snapshot for this effective request")
                artifact = artifacts[index]
                if artifact is None:
                    raise ValueError(
                        "Original attempt did not capture a complete response"
                    )
                snapshot = self.read(artifact)
                db.execute(
                    "INSERT OR REPLACE INTO cursors VALUES (?, ?, ?, ?)",
                    (run_id, source_run, key, index + 1),
                )
            return snapshot
        finally:
            db.close()


def _response(snapshot):
    if "transport_error" in snapshot:
        name = snapshot["transport_error"]
        error_type = getattr(requests.exceptions, name, requests.RequestException)
        if not isinstance(error_type, type) or not issubclass(
            error_type, requests.RequestException
        ):
            error_type = requests.RequestException
        raise error_type(f"Replayed transport failure: {name}")
    response = requests.Response()
    response.status_code = snapshot["status_code"]
    response._content = b64decode(snapshot["body_base64"], validate=True)
    response._content_consumed = True
    response.headers.update(snapshot["headers"])
    response.url = snapshot["url"]
    response.reason = snapshot["reason"]
    response.encoding = snapshot["encoding"]
    return response


def _cacheable(snapshot, kind):
    if "transport_error" in snapshot or snapshot["status_code"] != 200:
        return False
    if any(k.lower() == "set-cookie" for k in snapshot["headers"]):
        return False
    try:
        payload = json.loads(b64decode(snapshot["body_base64"]))
        canonical_bytes(payload)  # Non-finite values are not successful evidence.
    except (ValueError, UnicodeError):
        return False
    if not isinstance(payload, (dict, list)):
        return False
    if isinstance(payload, dict) and (
        payload.get("error")
        or payload.get("errors")
        or payload.get("status") not in (None, "Success", "OK")
    ):
        return False
    if kind == "trapi":
        if not isinstance(payload, dict):
            return False
        message = payload.get("message")
        kg = message.get("knowledge_graph") if isinstance(message, dict) else None
        return (
            isinstance(kg, dict)
            and isinstance(kg.get("nodes"), dict)
            and isinstance(kg.get("edges"), dict)
        )
    return True


class CacheSession:
    def __init__(self, settings, policy, run, *, previous=None):
        self.policy, self.run = policy, run
        self.root = settings.get("store")
        if (
            policy["scope"] == "cross_run" or policy["mode"] == "replay"
        ) and not self.root:
            raise ValueError(
                "cross-run caching and snapshot replay require an explicit store"
            )
        if policy["mode"] == "replay" and policy["snapshot_run"] == run.run_id:
            raise ValueError("Replay requires a run_id distinct from snapshot_run")
        same = (
            previous is not None and previous.run is run and previous.root == self.root
        )
        self.memory = previous.memory if same else {}
        self.lock = previous.lock if same else RLock()
        self.replay = (
            previous.replay
            if same
            and previous.policy.get("snapshot_run") == policy.get("snapshot_run")
            else None
        )
        self.store = None
        try:
            if self.root:
                self.store = CacheStore(self.root, readonly=policy["mode"] == "replay")
            if policy["mode"] == "replay" and self.replay is None:
                self.replay = defaultdict(list)
                for key, artifact in self.store.history(policy["snapshot_run"]):
                    self.replay[key].append(artifact)
                if not self.replay:
                    raise ValueError("Snapshot run has no service observations")
        except Exception as error:
            raise CacheError(
                "Cannot initialize cache", operation_completed=False, run_id=run.run_id
            ) from error

    def _identity(self, method, url, arguments, kind, original, reformulation):
        # Credentials participate in the digest, never in the stored manifest.
        # The explicit partition identifies the caller's auth/access epoch,
        # including implicit credentials (netrc, proxy, etc.).
        auth = (
            arguments.get("auth")
            or arguments.get("cookies")
            or any(
                k.lower() in ("authorization", "cookie", "proxy-authorization")
                for k in arguments.get("headers", {})
            )
        )
        if auth and not self.policy.get("authorization_partition"):
            raise ValueError("Authenticated caching requires authorization_partition")
        runtime = get_runtime_config()
        request = {"method": method.upper(), "url": url, "arguments": arguments}
        original_request = (
            request | {"arguments": original} if original is not None else request
        )
        original_hash = digest(original_request)
        key = digest(
            {
                "request": request,
                "service_kind": kind,
                "authorization_partition": self.policy.get(
                    "authorization_partition", "within-run"
                ),
                "dataset_versions": self.policy["dataset_versions"],
                "epoch": self.policy["epoch"],
                "runtime": {
                    "environment": runtime.environment,
                    "overrides": dict(runtime.overrides),
                },
                "policy_version": POLICY_VERSION,
                "canonicalizer_version": CANONICALIZER_VERSION,
                "adapter_version": "tct.http-response.v1",
            }
        )
        changed = original_hash != digest(request)
        if changed and not reformulation:
            raise ValueError(
                "A changed original request requires a reformulation identifier"
            )
        return key, {
            "original_request_hash": original_hash,
            "effective_execution_hash": key,
            "response_content_hash": None,
            "mode": self.policy["mode"],
            "reformulation": reformulation if changed else None,
            "policy_version": POLICY_VERSION,
            "canonicalizer_version": CANONICALIZER_VERSION,
        }

    def _emit(self, key, snapshot, receipt, *, pin=False, shared=False):
        receipt["response_content_hash"] = (
            snapshot.get("response_content_hash") if snapshot else None
        )
        receipt["snapshot_hash"] = digest(snapshot) if snapshot is not None else None
        try:
            with self.lock:
                if self.store and self.policy["mode"] != "replay":
                    expiry = (
                        time.time() + self.policy["ttl"][receipt["service_kind"]]
                        if shared
                        else None
                    )
                    self.store.save(
                        self.run.run_id,
                        key,
                        snapshot,
                        receipt,
                        pin=pin,
                        shared_expiry=expiry,
                    )
                if pin:
                    self.memory[key] = snapshot
                self.run.cache_events.append(dict(receipt))
        except Exception as error:
            raise CacheError(
                "Cannot persist cache observation",
                operation_completed=True,
                run_id=self.run.run_id,
            ) from error

    def request(
        self,
        request,
        url,
        arguments,
        *,
        method,
        kind,
        original=None,
        reformulation=None,
        consume=None,
        receipt=None,
    ):
        receipt = receipt if receipt is not None else {}
        try:
            key, identity = self._identity(
                method, url, arguments, kind, original, reformulation
            )
            receipt.update(identity, service_kind=kind)
            snapshot = None
            with self.lock:
                if self.policy["mode"] == "replay":
                    snapshot = self.store.take_replay(
                        self.run.run_id,
                        self.policy["snapshot_run"],
                        key,
                        self.replay[key],
                    )
                elif self.policy["mode"] == "use":
                    snapshot = self.memory.get(key)
                    if snapshot is None and self.store:
                        snapshot = self.store.lookup(
                            "run:" + self.run.run_id, key, time.time()
                        )
                        if (
                            snapshot is None
                            and self.policy["scope"] == "cross_run"
                            and kind in DEFAULT_TTL
                        ):
                            snapshot = self.store.lookup("shared", key, time.time())
        except Exception as error:
            cls = CacheReplayError if self.policy["mode"] == "replay" else CacheError
            raise cls(
                str(error), operation_completed=False, run_id=self.run.run_id
            ) from error
        if snapshot is not None:
            replay = self.policy["mode"] == "replay"
            receipt["outcome"] = "replayed" if replay else "warm"
            self._emit(key, snapshot, receipt, pin=not replay)
            return _response(snapshot)
        receipt["outcome"] = {
            "use": "cold",
            "refresh": "refreshed",
            "bypass": "bypassed",
        }[self.policy["mode"]]
        try:
            response = request(url, **arguments)
        except requests.RequestException as error:
            snapshot = {"transport_error": type(error).__name__}
            receipt["status"] = "transport_error"
            try:
                self._emit(key, snapshot, receipt)
            except CacheError as storage_error:
                error.add_note(str(storage_error))
            raise
        try:
            body = consume(response) if consume is not None else response.content
            if not isinstance(body, bytes):
                raise TypeError("Caching requires a buffered byte response")
            snapshot = {
                "status_code": response.status_code,
                "body_base64": b64encode(body).decode(),
                "headers": dict(response.headers),
                "url": response.url or url,
                "encoding": response.encoding,
                "reason": response.reason,
                "response_content_hash": hashlib.sha256(body).hexdigest(),
            }
        except Exception:
            receipt["status"] = "incomplete_snapshot"
            self._emit(key, None, receipt)
            raise
        eligible = _cacheable(snapshot, kind)
        receipt["status"] = "cacheable" if eligible else "not_cacheable"
        pin = eligible and self.policy["mode"] != "bypass"
        shared = pin and self.policy["scope"] == "cross_run" and kind in DEFAULT_TTL
        self._emit(key, snapshot, receipt, pin=pin, shared=shared)
        return response
