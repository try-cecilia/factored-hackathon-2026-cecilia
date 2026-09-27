"""Where raw files come from: the organizer's S3 bucket, or a local directory.

Both sources expose the same two operations — resolve a flat table's file,
and list a partitioned table's daily files (optionally filtered by date) —
and both return local paths plus the canonical source URI recorded in
lineage. The local source is what makes the test suite hermetic (fixture
CSVs, no network, no credentials).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import dotenv_values

_PARTITION_RE = re.compile(r"year=(\d{4})/month=(\d{2})/day=(\d{2})/")


@dataclass(frozen=True)
class SourceFile:
    local_path: Path
    uri: str
    size: int
    partition: date | None = None


def _partition_of(key: str) -> date | None:
    m = _PARTITION_RE.search(key.replace("\\", "/"))
    return date(int(m[1]), int(m[2]), int(m[3])) if m else None


def _in_window(d: date | None, since: date | None, until: date | None) -> bool:
    if d is None:
        return True
    return (since is None or d >= since) and (until is None or d <= until)


class LocalSource:
    """Reads an already-populated raw directory (e.g. tests/fixtures/raw)."""

    def __init__(self, raw_dir: Path):
        self.raw_dir = Path(raw_dir)

    def flat(self, filename: str) -> SourceFile:
        path = self.raw_dir / filename
        if not path.exists():
            raise FileNotFoundError(path)
        return SourceFile(path, f"file://{path.resolve()}", path.stat().st_size)

    def partitions(self, prefix: str, since: date | None = None, until: date | None = None) -> list[SourceFile]:
        out = []
        for path in sorted((self.raw_dir / prefix).glob("year=*/month=*/day=*/*.csv")):
            d = _partition_of(str(path))
            if _in_window(d, since, until):
                out.append(SourceFile(path, f"file://{path.resolve()}", path.stat().st_size, d))
        return out


class S3Source:
    """Downloads from the organizer's read-only bucket into raw_dir (cached by size)."""

    def __init__(self, raw_dir: Path, bucket: str | None = None):
        self.raw_dir = Path(raw_dir)
        self.bucket = bucket or os.environ.get("DATASET_BUCKET", "")
        if not self.bucket:  # the organizer's bucket name stays out of the public repo, like its keys
            raise RuntimeError("DATASET_BUCKET is not set: copy it from the organizer's data dictionary into .env")
        self._client = None

    def _s3(self):
        if self._client is None:
            import boto3

            key_id, secret, region = _aws_credentials()
            # Path-style + explicit SigV4: virtual-hosted-style requests are
            # rejected by some egress proxies (including the dev sandbox).
            self._client = boto3.client(
                "s3",
                region_name=region,
                aws_access_key_id=key_id,
                aws_secret_access_key=secret,
                config=boto3.session.Config(signature_version="s3v4", s3={"addressing_style": "path"}),
            )
        return self._client

    def _download(self, key: str, size: int) -> Path:
        dest = self.raw_dir / key.removeprefix("data/")
        if dest.exists() and dest.stat().st_size == size:
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        # Plain GetObject rather than download_file: s3transfer's default
        # flexible-checksum headers are rejected by some egress proxies.
        body = self._s3().get_object(Bucket=self.bucket, Key=key)["Body"]
        with open(tmp, "wb") as f:
            for chunk in body.iter_chunks(chunk_size=8 * 1024 * 1024):
                f.write(chunk)
        tmp.replace(dest)
        return dest

    def flat(self, filename: str) -> SourceFile:
        key = f"data/{filename}"
        size = self._s3().head_object(Bucket=self.bucket, Key=key)["ContentLength"]
        return SourceFile(self._download(key, size), f"s3://{self.bucket}/{key}", size)

    def partitions(self, prefix: str, since: date | None = None, until: date | None = None) -> list[SourceFile]:
        out = []
        paginator = self._s3().get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=f"data/{prefix}/"):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if not key.endswith(".csv"):
                    continue
                d = _partition_of(key)
                if _in_window(d, since, until):
                    out.append(SourceFile(self._download(key, obj["Size"]), f"s3://{self.bucket}/{key}", obj["Size"], d))
        return sorted(out, key=lambda f: f.uri)


def _aws_credentials() -> tuple[str, str, str]:
    """Credentials from .env take precedence over the process environment.

    Some hosts (including the dev sandbox) pre-set placeholder AWS_* variables
    for their own purposes; a blanket load_dotenv(override=True) to beat them
    once caused a test to delete the real warehouse (it also overrode
    DUCKDB_PATH). So only the three AWS keys are taken from .env here.
    """
    file_vals = dotenv_values(".env")
    pick = lambda k, default=None: file_vals.get(k) or os.environ.get(k, default)  # noqa: E731
    key_id, secret = pick("AWS_ACCESS_KEY_ID"), pick("AWS_SECRET_ACCESS_KEY")
    if not key_id or not secret:
        raise RuntimeError("AWS credentials missing: set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY in .env")
    return key_id, secret, pick("AWS_DEFAULT_REGION", "us-east-2")


def make_source(kind: str, raw_dir: Path):
    if kind == "s3":
        return S3Source(raw_dir)
    if kind == "local":
        return LocalSource(raw_dir)
    raise ValueError(f"unknown source kind: {kind}")
