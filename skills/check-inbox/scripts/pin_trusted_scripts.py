#!/usr/bin/env python3
"""Pin the skill shell scripts the envelope hook may run, under envelope.trusted_scripts.

The envelope hook (oacp-cli >= 0.5.4) trusts a `bash <script>` by pin only: a pinned script
runs under an active envelope without asking while the file still hashes to its pin, and any
unpinned script asks "not registered". A pin is the human's review of exact bytes, so this
script is the human's to run — an agent should prepare nothing but the dry run and hand the
two commands over; a receiver-config write plus its re-sign is authority self-modification.

usage:
  python3 -I pin_trusted_scripts.py <oacp_home> <oacp_scripts_dir> [--apply]
      [--agent claude] [--skills-dir ~/.claude/skills]
  # then, per project it wrote:
  oacp trust sign-policy --project <p> --agent claude --oacp-dir <oacp_home>

<oacp_scripts_dir> is the installed oacp package's _scripts/ directory: the block is validated
with the envelope compiler's own loader before any write. <skills-dir> is where these skills
are installed; each pin is recorded under that spelling (the hook compares real paths), and a
script whose skill is not installed there is skipped. Dry run by default; --apply writes every
projects/*/agents/<agent>/config.yaml: a config without an envelope block gets one (just above
the `auth:` trailer, which the re-sign replaces); a config that already has one is refreshed in
place — each PINS entry's digest is recomputed from the file on disk, a PINS entry the block
lacks is appended, and every other pin and envelope key is kept exactly as it was. The block is
serialized with PyYAML and the result is parsed back before any write: a config whose parsed
pins or other keys would differ from the intended mapping is refused, not written. A config
whose block already matches is skipped. Re-run both steps after any edit to a pinned file, or
the hook asks "does not match its pinned sha256" until the pin is refreshed.

One script at a time, the CLI has the same write as a verb — it appends or refreshes the one
pin, validates, and re-signs in one step:
  oacp trust pin-script <path> --agent claude --all-projects --oacp-dir <oacp_home>
"""
import hashlib
import os
import sys

import yaml

# The skill shell scripts a receiver may run under any envelope, relative to the skills dir,
# with the data-only env names a caller may prefix. A script that deletes or pushes (wrap-up's
# cleanup_branches.sh) is left to the human's own hand.
PINS = [
    ("check-inbox/scripts/send_done_and_finalize.sh", []),
    ("check-inbox/scripts/finalize_done.sh", []),
    ("check-inbox/scripts/oacp_archive.sh", []),
    ("review-loop-author/scripts/oacp_archive.sh", []),
    ("review-loop-author/scripts/diff_sizes.sh", []),
    ("self-improve/scripts/pass_marker.sh", []),
]


def digest(path: str) -> str:
    with open(os.path.expanduser(path), "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def real(path: str) -> str:
    return os.path.realpath(os.path.expanduser(path))


def render_block(section) -> str:
    """The top-level `envelope:` block for `section`, serialized by PyYAML (quotes as needed)."""
    return yaml.safe_dump({"envelope": section}, sort_keys=False, default_flow_style=False,
                          allow_unicode=True, width=4096)


def splice_block(text: str, block: str) -> str:
    """Replace the top-level envelope: block, or insert the block before auth: (else append)."""
    parts = text.splitlines(keepends=True)
    start = next((i for i, line in enumerate(parts) if line.startswith("envelope:")), None)
    if start is None:
        auth_index = next((i for i, line in enumerate(parts) if line.startswith("auth:")), None)
        if auth_index is None:
            return text.rstrip("\n") + "\n" + block
        return "".join(parts[:auth_index]) + block + "".join(parts[auth_index:])
    end = len(parts)
    for i in range(start + 1, len(parts)):
        if parts[i].strip() and not parts[i][0].isspace() and not parts[i].startswith("#"):
            end = i
            break
    return "".join(parts[:start]) + block + "".join(parts[end:])


def same_pin(a, b) -> bool:
    return (a.get("path"), a.get("sha256"), list(a.get("env") or [])) == (
        b.get("path"), b.get("sha256"), list(b.get("env") or []))


def merge(existing, desired):
    """existing pins with each desired pin replaced (by real path) or appended; others kept as is."""
    merged = []
    changes = []
    by_real = {real(pin["path"]): pin for pin in desired}
    seen = set()
    for pin in existing:
        key = real(pin["path"])
        if key in by_real and key not in seen:
            want = by_real[key]
            seen.add(key)
            if not same_pin(pin, want):
                changes.append(f"refreshed: {want['path']}")
            merged.append(want)
        else:
            merged.append(pin)
    for pin in desired:
        if real(pin["path"]) not in seen:
            merged.append(pin)
            changes.append(f"added: {pin['path']}")
    return merged, changes


def plan(text, desired, loader):
    """(new_text, merged, changes) for one config, or raise ValueError when it cannot be written
    exactly. `loader` is the envelope compiler's trusted_scripts validator."""
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError("config is not a mapping")
    loader(data)  # a malformed existing block fails here, before anything is planned
    section = data.get("envelope") or {}
    existing = list(section.get("trusted_scripts") or [])
    merged, changes = merge(existing, desired)
    if existing and not changes:
        return None, merged, changes
    new_section = dict(section)
    new_section["trusted_scripts"] = merged
    new_text = splice_block(text, render_block(new_section))
    parsed = yaml.safe_load(new_text) or {}
    if (parsed.get("envelope") or {}) != new_section:
        raise ValueError("serialized envelope block does not parse back to the intended mapping")
    if len(loader(parsed)) != len(merged):
        raise ValueError("the compiler's loader does not accept the merged pins")
    for key in set(data) | set(parsed):
        if key not in ("envelope", "auth") and parsed.get(key) != data.get(key):
            raise ValueError(f"top-level key {key!r} would change")
    return new_text, merged, changes


def option(argv, name, default):
    if name in argv:
        index = argv.index(name)
        if index + 1 < len(argv):
            return argv[index + 1]
    return default


def main(argv) -> int:
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    home, compiler_dir = argv[1], argv[2]
    apply = "--apply" in argv[3:]
    agent = option(argv, "--agent", "claude")
    skills_dir = option(argv, "--skills-dir", "~/.claude/skills").rstrip("/")
    sys.path.insert(0, compiler_dir)
    import envelope_compiler  # noqa: E402

    desired = []
    for rel, env in PINS:
        path = f"{skills_dir}/{rel}"
        if not os.path.isfile(os.path.expanduser(path)):
            print(f"skipped (not installed): {path}", file=sys.stderr)
            continue
        pin = {"path": path, "sha256": digest(path)}
        if env:
            pin["env"] = list(env)
        desired.append(pin)
    if not desired:
        print(f"no pinnable scripts under {skills_dir}", file=sys.stderr)
        return 1
    print(render_block({"trusted_scripts": desired}))

    projects_dir = os.path.join(home, "projects")
    written, refused = [], []
    for project in sorted(os.listdir(projects_dir)):
        cfg = os.path.join(projects_dir, project, "agents", agent, "config.yaml")
        if not os.path.isfile(cfg):
            continue
        with open(cfg, encoding="utf-8") as handle:
            text = handle.read()
        try:
            new_text, merged, changes = plan(text, desired, envelope_compiler.trusted_scripts)
        except Exception as exc:  # the compiler's loader raises its own error type
            print(f"{project}: REFUSED — {exc}; nothing written", file=sys.stderr)
            refused.append(project)
            continue
        if new_text is None:
            print(f"{project}: {len(merged)} pins up to date — skipped")
            continue
        verb = "pinned" if apply else "would pin"
        print(f"{project}: {verb} {len(merged)} scripts ({'written' if apply else 'dry run'})")
        for change in changes:
            print(f"  {change}")
        if apply:
            with open(cfg, "w", encoding="utf-8") as handle:
                handle.write(new_text)
            written.append(project)
    if written:
        print("\nnow re-sign each policy:")
        for project in written:
            print(f"  oacp trust sign-policy --project {project} --agent {agent} --oacp-dir {home}")
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
