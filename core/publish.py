"""Publish pass snapshots to the site release repo.

Zips go to prerelease chunk tags {pass}.{n} (<=500 assets each, ncode order
from works.json); the manifest goes to {pass}.M as a regular release so
releases/latest/download/ always resolves to the newest pass's manifest.
Needs GH_TOKEN with contents:write on the target repo.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from core.summary import pass_label

CHUNK_SIZE = 500


def chunk_tag(label: str, work_index: int) -> str:
    return f"{label}.{work_index // CHUNK_SIZE + 1}"


def _gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def _ensure_release(repo: str, tag: str, title: str, prerelease: bool) -> None:
    if _gh("release", "view", tag, "--repo", repo).returncode == 0:
        return
    cmd = ["release", "create", tag, "--repo", repo, "--title", title, "--notes", ""]
    if prerelease:
        cmd.append("--prerelease")
    result = _gh(*cmd)
    if result.returncode != 0 and "already exists" not in result.stderr:
        raise RuntimeError(f"creating {tag}: {result.stderr.strip()}")


def publish_zips(zips: list[Path], works_path: Path, label: str, repo: str, site: str) -> int:
    order = {w["ncode"]: i for i, w in enumerate(json.loads(works_path.read_text()))}
    published = 0
    for zip_path in zips:
        ncode = zip_path.stem.removeprefix(f"corpus-{site}-")
        if ncode not in order:
            print(f"skipping {zip_path.name}: not in works list")
            continue
        tag = chunk_tag(label, order[ncode])
        _ensure_release(repo, tag, tag, prerelease=True)
        result = _gh("release", "upload", tag, str(zip_path), "--repo", repo, "--clobber")
        if result.returncode != 0:
            raise RuntimeError(f"uploading {zip_path.name}: {result.stderr.strip()}")
        published += 1
    return published


def build_manifest(stats: dict, works_path: Path, label: str, repo: str, site: str) -> dict:
    by_ncode = {w["ncode"]: (i, w) for i, w in enumerate(json.loads(works_path.read_text()))}
    entries = []
    for ncode, entry in sorted(stats["works"].items()):
        if ncode not in by_ncode:
            continue
        index, work = by_ncode[ncode]
        tag = chunk_tag(label, index)
        entries.append(
            {
                "ncode": ncode,
                "title": entry["title"],
                "writer": work["writer"],
                "chapters": entry["chapters"],
                "sentences": entry["sentences"],
                "bytes": entry["bytes"],
                "sha256": entry.get("sha256"),
                "url": f"https://github.com/{repo}/releases/download/{tag}/corpus-{site}-{ncode}.zip",
                "revision": entry["revision"],
            }
        )
    return {
        "site": site,
        "schema": 1,
        "pass": label,
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "works": entries,
    }


def publish_manifest(
    stats_path: Path, works_path: Path, label: str, repo: str, site: str, out_dir: Path
) -> int:
    stats = json.loads(stats_path.read_text())
    manifest = build_manifest(stats, works_path, label, repo, site)
    index = {
        "schema": 1,
        "generated": manifest["generated"],
        "sites": {
            site: {
                "manifest": f"manifest-{site}.json",
                "pass": label,
                "works": len(manifest["works"]),
            }
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / f"manifest-{site}.json"
    index_path = out_dir / "index.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    index_path.write_text(json.dumps(index, indent=1))

    tag = f"{label}.M"
    _ensure_release(repo, tag, f"{label} (manifest)", prerelease=False)
    result = _gh(
        "release", "upload", tag, str(manifest_path), str(index_path), "--repo", repo, "--clobber"
    )
    if result.returncode != 0:
        raise RuntimeError(f"uploading manifest: {result.stderr.strip()}")
    return len(manifest["works"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--site", required=True)
    ap.add_argument("--works", required=True)
    ap.add_argument("--pass-file", required=True)
    ap.add_argument("--zips", nargs="*", help="bank zips to upload")
    ap.add_argument("--manifest-from", help="stats json; publish the pass manifest")
    args = ap.parse_args()

    label = pass_label(Path(args.pass_file))
    if args.zips:
        n = publish_zips(
            [Path(p) for p in args.zips], Path(args.works), label, args.repo, args.site
        )
        print(f"published {n} zips to {args.repo} pass {label}")
    if args.manifest_from:
        n = publish_manifest(
            Path(args.manifest_from),
            Path(args.works),
            label,
            args.repo,
            args.site,
            Path("out/manifest"),
        )
        print(f"published manifest for {n} works to {args.repo} {label}.M")
    return 0


if __name__ == "__main__":
    sys.exit(main())
