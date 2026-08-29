# debrief

Capture a structured session summary and publish it to the OACP org-memory debrief store as one immutable, hash-verified record.

## Prerequisites

- `oacp` CLI ≥ 0.4.4 — the release whose `oacp doctor` validates the debrief store's setup. The writer has no `oacp` dependency of its own and runs against any published wheel; 0.4.4 is the floor for the *check*, not for publishing.
- Python 3.9+ for `scripts/write_debrief.py` (standard library only, no dependencies)

An existing org-memory tree is *not* required — the writer provisions its own.

## Runtimes

- **Claude Code**: install to `.claude/skills/debrief/SKILL.md`
- **Codex**: install to `.agents/skills/debrief/SKILL.md`

Both runtime slices call the same runtime-agnostic writer at
`scripts/write_debrief.py`; there is no runtime-specific writer fork.

## Install

```bash
# Claude Code
mkdir -p .claude/skills/debrief/scripts
cp skills/debrief/claude/SKILL.md .claude/skills/debrief/SKILL.md
cp skills/debrief/scripts/write_debrief.py .claude/skills/debrief/scripts/

# Codex
mkdir -p .agents/skills/debrief/scripts
cp skills/debrief/codex/SKILL.md .agents/skills/debrief/SKILL.md
cp skills/debrief/scripts/write_debrief.py .agents/skills/debrief/scripts/
```

Optionally initialize the store once per OACP home. The writer creates whatever
part of the tree is missing on first publish, so this is a convenience rather
than a required step:

```bash
oacp org-memory init
```

## Usage

```text
/debrief           # generate the summary and publish it
/debrief --dry-run # generate and display it; write nothing
```

## The store

```text
$OACP_HOME/org-memory/debriefs/<project>/<YYYY>/<MM>/<YYYYMMDD>-<agent>-<session>.md
```

- `<project>` — workspace name, byte-for-byte as it appears under `$OACP_HOME/projects/`
- `<YYYY>/<MM>` — year and zero-padded month of the session start, **in UTC**, both agreeing with the filename date prefix
- `<session>` — 1-32 lowercase alphanumerics, never hyphens (it is parsed as the substring after the final hyphen, which is what keeps hyphenated agent names unambiguous)

Each record carries required frontmatter — `schema_version`, `project`, `agent`, `runtime`, `session`, `started_utc`, `ended_utc`, `content_sha256`, `immutable: true` — followed by the free-form Markdown body. `content_sha256` is the SHA-256 of the exact body bytes, with no whitespace or newline normalization.

## Append-only

One session, one file, written once and never rewritten:

- A later session the same day writes a **new** file with a different session id — never an append.
- Corrections are new artifacts (a new debrief, or an event referencing the original), never edits to a landed record.
- Republishing byte-identical content is idempotent success; publishing *different* content at an existing path is a hard failure that recovers under a new session id.

## Writer contract

`scripts/write_debrief.py` implements failure-atomic publication:

1. Compose and validate the record; reject a bad schema before touching the store.
2. Stage in `.stage.<final-name>.<nonce>` beside the target — created `O_CREAT|O_EXCL|O_NOFOLLOW` under an unpredictable nonce, so the inode is always one this writer made. Flush, then verify size and content hash *through that same descriptor*.
3. Publish with an atomic no-replace `link()`, then unlink the staging name and confirm the canonical path resolves to the staged `(st_dev, st_ino)`. A replacing rename is forbidden, and so is writing through the canonical path directly.
4. Read the canonical file back and confirm the hash.

Failures leave the canonical namespace clean — at worst a private staging file remains, and a later successful publication of the same record sweeps it. A pre-existing staging path is never adopted: linking an inode this writer did not create would leave the "immutable" record mutable through whatever else points at it. The target must be a regular file; symlinks and non-regular files are refused rather than followed.

## Tests

```bash
python3 -m pytest skills/debrief/tests/ -q
```

The suite pins the seven writer-conformance cases the protocol requires: short write before publish, interrupted publication recovery, read-back mismatch, idempotent retry, differing-content collision, symlink at target, and concurrent identical and differing writers.

It also pins two classes nothing downstream can catch. **Staging ownership**: a symlink, a foreign regular file, or a multi-linked file at the staging path is refused rather than published, the published record is the only name for its inode, and a stale stage is swept once the record lands. **Frontmatter serialization**: every identity value the protocol grammars accept — `true`, `null`, `no`, `0x1f`, `*alias` — reads back from a real YAML parser as the same string, and a body that is not valid UTF-8 is rejected before the store is touched.

## Curation guard

Raw debriefs never enter `recent.md` or `events/` — only curated folds do. Promote durable outcomes with `oacp write-event`, setting `source_ref` to the debrief filename stem so the two reconcile.
