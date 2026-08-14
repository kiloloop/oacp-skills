---
name: self-improve
description: "Audit and improve Codex operating guidance: skills, curated project memory, AGENTS.md, and relevant configuration. Use for explicit self-improve requests, routine wrap-up drift checks, stale or conflicting guidance, or an approved cleanup. Route release-wide OACP migrations and context-budget audits to audit-oacp-skills. Do not hand-edit generated Codex memories or installed plugin/system artifacts."
---

# Self-improve

Audit the durable guidance layer, prove how it behaves in the active runtime,
and apply only approved changes. Verify current capabilities from live evidence
and official sources rather than hardcoding release or model names.

## Scope and depth

| Request | Review scope |
|---|---|
| `$self-improve` | Skills used this session, curated project memory, AGENTS.md, and relevant config |
| `$self-improve skills` | Skills actually used this session |
| `$self-improve memory` | Curated project memory only |
| `$self-improve agents-md`, `config`, or `claude-md` | AGENTS.md and relevant Codex config |
| `$self-improve <skill-name>` | The named skill, its effective-state chain, and editable source |
| Wrap-up caller | Session-delta targets first; broaden only on evidence of drift |

An explicit or natural-language self-improve request performs the requested
scope. A wrap-up caller starts with skills used, guidance/memory/config changed,
and failures, workarounds, conflicts, or discovery gaps observed this session.
Do not turn routine wrap-up into a release-wide audit without such evidence.

Route major Codex model/app/CLI or OACP release migrations, multi-skill
capability changes, and context-budget audits to `$audit-oacp-skills`. Route a
changelog summary without guidance-impact analysis to `$codex-changelog`.

Treat audit, review, diagnosis, and report requests as read-only. A numbered
approval authorizes only its listed local edits. Commit, push, PR, merge,
messaging, and other external writes remain separate unless explicitly listed.

## 1. Resolve targets and ownership

Use the active Skills catalog and exact locators first. Read every selected
`SKILL.md` completely, then load only the references or scripts required for
the selected scope.

Classify each target before proposing edits:

- **Authored source:** editable only after approval.
- **Symlinked skill or guidance:** edit the resolved source and name its repo.
- **Installed artifact:** plugin cache, bundled/system skill, or provider
  resource; inspect read-only and locate an authoring/update path.
- **Cross-runtime namesake:** report drift without synchronizing another
  runtime automatically.

Generated Codex memory under `${CODEX_HOME:-$HOME/.codex}/memories/` is
generated state, not hand-maintained project memory. Do not hand-edit or apply
line-budget trimming to it. Inspect configuration through an explicit key
allowlist and redact tokens, credentials, environment values, and private
endpoints. Never broadly search credential-adjacent config or session trees.

Load only the applicable section of
[references/audit-checks.md](references/audit-checks.md) for detailed skill,
curated-memory, or AGENTS/config checks.

## 2. Prove effective state

For every target, verify the relevant chain:

```text
authored source -> discovery/configuration -> callers/dependents -> observed behavior
```

Source validity alone is insufficient. Check applicable auxiliary metadata,
canonical discovery paths, symlinks, manifests, hooks, setup generators, and
direct skill/AGENTS callers within explicit authored roots. Run one live or
test probe when available. Mark an unavailable probe as `unverified`; do not
silently treat authored intent as effective behavior.

If a dependent is outside the approved scope, report it as follow-up instead of
editing it. This step must catch valid-but-undiscoverable skills, stale caller
syntax, generated configuration that differs from its source, and scripts whose
documented effect is not observable.

For current OpenAI/Codex behavior, use `$openai-docs` or `$codex-changelog` as
appropriate. Capability-check unstable CLI surfaces and distinguish authored,
configured, and runtime-observed states.

## 3. Analyze and capture acceptance evidence

Use these tags:

| Tag | Meaning |
|---|---|
| `[FIX]` | Clear bug or incorrect instruction |
| `[STALE]` | Time-sensitive content is outdated |
| `[GAP]` | Required workflow, wiring, or safety coverage is missing |
| `[CONFLICT]` | Sources or effective states disagree |
| `[STRUCTURAL]` | The workflow needs architectural rather than surgical work |
| `[BLOAT]` | Content can move or disappear without losing required behavior |

Check trigger behavior, workflow inputs/outputs, stopping conditions, approval
boundaries, safety, current paths/commands/config, ownership, duplication, run
learnings, and validation. Promote repeatable run lessons with
`$consolidate-learnings`; never append a second procedure as a learned log.

For every proposed change, define a before/after acceptance probe and capture
its current result before editing. Use context measurement only when the
finding concerns a hot-path skill, progressive disclosure, a release-wide
migration, or a context budget. Reuse `$audit-oacp-skills` measurement with the
same tokenizer for the comparison; routine correctness fixes do not require a
token baseline.

## 4. Report and request approval

Group findings by requested scope. For each finding provide the target and line
when available, live evidence, impact, specific outcome, and acceptance probe.
Say `No issues found` for an in-scope category with no findings.

End a changeable audit with a self-contained numbered menu containing:

- the recommended choice first when clear;
- every proposed change number;
- target files/repos and exact outcomes;
- allowed replies: `all`, `none`, or item numbers;
- whether commit, push, PR, messaging, or another external action is included.

Do not edit before approval unless the original request already authorized the
exact change.

## 5. Apply and verify approved changes

1. Re-read every live target and nearest `AGENTS.md`; confirm repo, branch,
   status, ownership, and unrelated concurrent changes.
2. Preserve user and other-agent work. In a shared skills repository, edit
   only Codex-owned `codex/` or explicitly approved shared files.
3. Keep installed/plugin/system/provider artifacts read-only. Coordinate with
   another runtime only when messaging is authorized.
4. Before editing OACP runtime memory, acquire the project's
   `.memory-write.lock`; defer when another valid writer holds it and remove a
   lock created by this run on exit.
5. Apply only approved edits with `apply_patch`, inspect the diff, and confirm
   the intended files changed.
6. Re-run the exact acceptance probe captured before editing, followed by
   proportional project-native validation. For a changed skill, run the skill
   validator, check frontmatter and direct links, exercise representative
   positive/negative triggers, and verify effective discovery when applicable.
7. When context measurement was warranted, compare with the same tokenizer and
   explain increases as well as reductions. Lower token count is not a
   correctness result.

For an OACP runtime-memory edit, use an explicit owner token because a shell
`trap` cannot span separate Codex tool calls. Never remove a valid writer lock
solely because it is old.

Acquire before the first edit:

```bash
LOCK_DIR="$OACP_ROOT/projects/${PROJECT}/.memory-write.lock"
LOCK_OWNER_FILE="$(mktemp)"
python3 - "$LOCK_OWNER_FILE" <<'PY'
import datetime
import json
import secrets
import socket
import sys

owner = {
    "token": secrets.token_hex(16),
    "host": socket.gethostname(),
    "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(owner, handle)
PY
chmod 600 "$LOCK_OWNER_FILE"
if mkdir "$LOCK_DIR" 2>/dev/null; then
  chmod 700 "$LOCK_DIR"
  cp -- "$LOCK_OWNER_FILE" "$LOCK_DIR/owner"
  chmod 600 "$LOCK_DIR/owner"
  echo "Memory lock acquired"
else
  echo "Memory lock held by another writer; defer memory edits"
fi
```

If acquisition fails, leave the existing directory untouched and defer all
runtime-memory edits. Lock recovery requires separately proving the prior
writer is gone; age alone is never proof. Release after the last edit,
including an edit failure, only when the stored owner is byte-identical to this
run's token:

```bash
if [ -d "$LOCK_DIR" ] && cmp -s "$LOCK_OWNER_FILE" "$LOCK_DIR/owner"; then
  command rm -f -- "$LOCK_DIR/owner"
  rmdir -- "$LOCK_DIR"
else
  echo "Memory lock ownership changed or was not acquired; refusing release"
fi
command rm -f -- "$LOCK_OWNER_FILE"
```

## 6. Commit or publish only when requested

Commit, push, PR creation, merge, and messaging are separate actions. When
explicitly requested, follow each owning repo's `AGENTS.md`, reconfirm its root,
branch, and status, stage only approved files, and keep repositories
independent. Runtime memory and unrelated untracked state are never included
merely because guidance changed.

## 7. Summarize

Report scope and sources, effective-state evidence, findings applied or
deferred, files changed by owning repo, exact validation and before/after probe
results, external-action state, and remaining risks.

Keep changes surgical. Do not invent current facts, hardcode ephemeral model or
release details, or let an audit drift into unapproved runtime namespaces.
