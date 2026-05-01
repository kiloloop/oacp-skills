# wrap-up — Shared Intent

## What it does

Sequenced end-of-session hygiene. Composes cleanup, optional debrief, org-memory event capture, self-improve, commit, optional memory snapshot push, and remote push into a single command. Designed to be invoked once at the end of a working session so the agent leaves a clean tree, durable memory, and an up-to-date remote.

## Workflow

The skill walks through eight steps in strict order. Steps are runtime-agnostic in intent; runtime-specific instructions live in each runtime's `SKILL.md`.

1. **Cleanup** — remove just-merged PR worktrees, delete merged local branches (safe `-d` only), prune stale worktrees, and report (but do not auto-delete) processed inbox messages.
2. **Debrief (optional)** — invoke `/debrief` if installed; otherwise write to `$CORTEX_HOME` if set; otherwise drop a 20-line summary at `./.oacp/debriefs/YYYY-MM-DD.md`. Failure is non-fatal.
3. **Org-memory events** — write `event` / `decision` / `rule` entries via `oacp write-event` for outcomes other agents and projects need to know about. Skip silently if org-memory is not initialized.
4. **Self-improve (hard dependency)** — invoke `/self-improve` (full scope), pause for user approval, apply approved changes. An optional follow-up pass (`/self-improve self-improve`) reviews the self-improve skill itself.
5. **Commit current repo** — stage explicit files, exclude secrets, commit with a `wrap-up:` prefix.
6. **OACP memory sync** — `oacp memory push` if the `$OACP_HOME/.oacp-memory-repo` marker is present. Independent of Step 7; failure does not block.
7. **Pull-rebase + push** — rebase the current branch onto its upstream, then push.
8. **Summary** — print a structured status block covering each step's outcome.

`--dry-run` runs Steps 1–4 (cleanup, debrief, org-memory, self-improve) but skips commits, pushes, and memory sync (Steps 5–7).

## Inputs

- The current repo's working tree (required)
- `$OACP_HOME` (optional) — defaults to `$HOME/oacp` (matching the OACP CLI's documented fallback). Used for inbox cleanup, org-memory events, and memory sync.
- `$CORTEX_HOME` (optional) — clone of `kiloloop/cortex` for the debrief target when `/debrief` is not installed.
- `--dry-run` flag (optional) — preview mode.

## Hard dependency

- **`/self-improve` skill** (Step 4) — must be installed in the runtime. If absent, the skill fails with an install hint pointing at `skills/self-improve/` in the same repo.

## Optional integrations

- **`/debrief` skill** — preferred debrief target when installed.
- **`oacp` CLI ≥ 0.3.0** — required for Step 3 (`oacp write-event`) and Step 6 (`oacp memory push`).
- **Cloned `kiloloop/cortex`** — set `$CORTEX_HOME` to enable the second-tier debrief target. Public repo: <https://github.com/kiloloop/cortex>.

## Acceptance criteria

- Never force-deletes branches — uses `git branch -d` only, never `-D`.
- Never auto-deletes inbox messages — reports them only; user confirms deletion.
- Never commits `.env`, credentials, secrets, or `settings.json` files.
- Always pull-rebases before push (Step 7) to avoid conflicts with other runtimes.
- Debrief failure is non-fatal — Steps 3–8 still run.
- Org-memory sync (Step 6) is independent of the current-repo push (Step 7) — failure on one does not block the other.
- The skill never inlines runtime-specific sandbox bypass flags. Runtime permissions and SSH-agent socket access are described in prose and configured in the runtime, not in the skill body.

## Outputs

A summary block printed to the user covering: cleanup counts, debrief target, org-memory event count, self-improve findings/applied, commit SHA, memory-sync SHA (or skip reason), and push status.
