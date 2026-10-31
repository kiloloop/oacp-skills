#!/usr/bin/env python3
"""Semantic compare of a lockfile's package map between two git refs.

A line diff of a lockfile is alignment noise; the reviewer needs which packages
were removed, added, or moved version. Step 4's round-1 sizing quotes this
output for any PR that touches a lockfile.

    python3 lockfile_compare.py --repo <dir> --base <ref> --head <ref> [--path pnpm-lock.yaml]

Supports pnpm-lock.yaml (pnpm 12 writes several YAML documents into one file,
so it is read with safe_load_all) and npm's package-lock.json. Exit 0 on a
successful compare; 1 on a missing file or an unknown lockfile format.
"""
import argparse
import json
import subprocess
import sys


def show(repo: str, ref: str, path: str) -> str:
    out = subprocess.run(["git", "-C", repo, "show", f"{ref}:{path}"], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"ERROR: git show {ref}:{path} failed: {out.stderr.strip()}")
    return out.stdout


def packages(text: str, path: str) -> dict[str, set[str]]:
    """Map package name -> set of resolved versions."""
    found: dict[str, set[str]] = {}
    if path.endswith("pnpm-lock.yaml"):
        import yaml
        for doc in yaml.safe_load_all(text):
            for key in (doc or {}).get("packages", {}) or {}:
                name, _, ver = key.rpartition("@")
                found.setdefault(name, set()).add(ver)
    elif path.endswith("package-lock.json"):
        for key, meta in json.loads(text).get("packages", {}).items():
            if key and "version" in meta:
                found.setdefault(key.rsplit("node_modules/", 1)[-1], set()).add(meta["version"])
    else:
        sys.exit(f"ERROR: unknown lockfile format: {path}")
    return found


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--path", default="pnpm-lock.yaml")
    args = ap.parse_args()

    a = packages(show(args.repo, args.base, args.path), args.path)
    b = packages(show(args.repo, args.head, args.path), args.path)
    removed = sorted(n for n in a if n not in b)
    added = sorted(n for n in b if n not in a)
    changed = sorted(n for n in a if n in b and a[n] != b[n])

    print(f"{args.path} packages map, {args.base} -> {args.head}: "
          f"{sum(map(len, a.values()))} -> {sum(map(len, b.values()))} entries")
    print(f"names removed {len(removed)}: {', '.join(removed) or '-'}")
    print(f"names added {len(added)}: {', '.join(added) or '-'}")
    print(f"names version-changed {len(changed)}")
    for n in changed:
        print(f"  {n}: {', '.join(sorted(a[n]))} -> {', '.join(sorted(b[n]))}")


if __name__ == "__main__":
    main()
