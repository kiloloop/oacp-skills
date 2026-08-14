---
name: oacp
description: Use the OACP (Open Agent Coordination Protocol) CLI and message protocol to coordinate multi-agent work — send messages between agents, sign and verify them, watch inboxes, run review loops, follow OACP conventions. Trigger whenever the user mentions OACP, runs `oacp` commands, references `.oacp` workspace markers, dispatches messages between agents (notifications, task requests, review requests), or coordinates work across runtimes — even if they don't say "OACP" explicitly.
---

# /oacp — OACP Protocol & CLI

OACP is a file-based coordination protocol for multi-agent workflows. Each project lives under `$OACP_HOME/projects/<project>/`, each agent has an `inbox/` and `outbox/`, and messages are YAML files. This skill teaches you how to operate within that protocol — verify the environment, send messages, watch inboxes, and follow review-loop semantics.

For runtime-agnostic protocol concepts (message schema, lifecycle, type semantics) read `shared/INTENT.md`.

## 1. Version check (run this first)

Before any OACP operation, verify the CLI is installed and meets the version contract declared in `skill.yaml` (`requires_oacp: ">=0.4.2"`):

```bash
oacp --version
```

If the command is missing or the version is below `0.4.2`, fail loudly and ask the user to install or upgrade:

```bash
pip install --upgrade 'oacp-cli[crypto]>=0.4.2'   # [crypto] extra enables message signing + verification
# or, if installed via uv:
uv tool install --upgrade 'oacp-cli[crypto]'
```

Why this matters: protocol fields and CLI flags evolve. Running this skill against an older CLI produces silent schema drift — messages may write but parse incorrectly, or `oacp watch` flags may not exist. Verify first; fix before continuing.

## 2. Workspace orientation

OACP workspaces live outside the project repo. Three things must exist:

- **`$OACP_HOME`** — environment variable. Defaults to `$HOME/oacp`. Set it in your shell profile if your workspace is elsewhere.
- **`.oacp` marker** — file in the project repo root. Either a JSON file with `{"project_name": "<name>"}` or a symlink into `$OACP_HOME/projects/<name>/`.
- **Project workspace** — `$OACP_HOME/projects/<project>/agents/<agent>/{inbox,outbox}/`.

To create a fresh workspace:

```bash
oacp init <project> --agents claude,codex      # create project + agent inboxes
oacp setup claude --project <project>          # write .oacp marker + runtime config in CWD
oacp doctor --project <project>                # verify workspace health
```

To add an agent later:

```bash
oacp add-agent <project> <agent> --runtime <claude|codex|...>
```

## 3. Sending a message — the canonical workflow

`oacp send` composes and writes a protocol-compliant message to the recipient's inbox and the sender's outbox in one call. Use it as the only sanctioned way to send — never hand-write inbox YAML.

```bash
oacp send <project> \
  --from <sender_agent> \
  --to <recipient_agent> \
  --type <type> \
  --subject "<one-line>" \
  --body "<markdown body>" \
  --priority P1 \
  --parent-message-id <id-of-message-this-replies-to>   # only on a reply
```

Useful optional flags:

- `--body-file <path>` — read body from a file (preferred for multi-paragraph bodies)
- `--related-pr <N>` — link to a GitHub PR (used by `review_request` / `review_feedback`)
- `--related-packet <id>` — link to a design packet (review for specs, not PRs)
- `--in-reply-to <id>` / `--conversation-id <id>` — thread linkage
- `--oacp-dir <path>` — override `$OACP_HOME` (rarely needed)
- `--dry-run` — print the YAML without writing
- `--json` — machine-readable output

**Verify the send landed.** `oacp send` prints the inbox path it wrote to. Confirm the file exists:

```bash
test -f "<inbox_path_from_oacp_send_output>" && echo OK
```

Do **not** grep for the `msg-id` — the on-disk filename hash differs from the in-body id, so an id grep returns false negatives.

### Picking a message type

| Type | When to use |
|------|-------------|
| `notification` | Inform the recipient of something — no reply required. |
| `task_request` | Ask the recipient to do work. They reply with `notification` when done. |
| `question` | Ask for information. They reply with `notification`. |
| `review_request` | Request review of a PR (`--related-pr`) or design packet (`--related-packet`). |
| `review_feedback` | Reviewer → author: changes requested. |
| `review_lgtm` | Reviewer → author: approval. |
| `review_addressed` | Author → reviewer: feedback addressed. Informational — does **not** trigger re-review on its own; send a fresh `review_request` to start round N+1. |
| `handoff` | Transfer context for the recipient to continue. They reply with `handoff_complete`. |
| `handoff_complete` | Acknowledge the handoff was received and acted on. |
| `brainstorm_request` | Ask for unstructured exploration. |
| `brainstorm_followup` | Continue a brainstorm thread with new constraints. |
| `follow_up` | Generic follow-up on an earlier thread when no other type fits. |

See `shared/INTENT.md` for the full lifecycle of each type.

### Worked example — dispatch a task end-to-end

```bash
# 1. Compose the body in a file (cleaner for multi-paragraph bodies).
cat > /tmp/task-body.md <<'EOF'
## Task
Add unit tests for the parser module.

## Acceptance
- All public functions covered
- Tests pass under the existing pytest config

## Done criteria
PR merged with green CI.
EOF

# 2. Send the task_request.
oacp send my-project \
  --from claude --to codex \
  --type task_request \
  --priority P1 \
  --subject "Add unit tests for parser module" \
  --body-file /tmp/task-body.md

# 3. The recipient processes via /check-inbox and replies on completion:
#    oacp send my-project --from codex --to claude --type notification \
#      --subject "Re: Add unit tests for parser module" \
#      --parent-message-id <your_msg_id> \
#      --body "Done — merged in <PR-link>."

# 4. You receive the reply via your inbox watcher (Section 4).
```

## 4. Reading the inbox

Two CLIs: one-shot listing vs. event-driven watching.

**One-shot** — `oacp inbox <project> --agent <agent>` lists pending messages without consuming them.

**Event-driven** — `oacp watch` emits a line per new message, suitable for a Monitor process or a shell loop:

```bash
oacp watch --project my-project --agent claude                       # human-readable
oacp watch --project my-project --agent claude --json                # JSON Lines
oacp watch --project my-project --agent claude --state-id watch-1a2b --since epoch
oacp watch --all-projects --agent claude                             # multi-project (coordinator pattern)
```

Flags:

- `--state-id <id>` (v0.4.0+) — use a per-subscriber cursor file (`state/watch/<agent>.<state-id>.json`) so multiple concurrent watchers each receive every event independently. Omit for the legacy shared cursor. With per-subscriber cursors, **duplicate delivery across sessions is the norm** — confirm a message file still exists before processing it.
- `--since now` (default) suppresses replay of pre-existing inbox messages on first run; `--since epoch` replays the existing backlog once on the first scan (recommended with a fresh `--state-id` so messages predating the watcher still fire); `--since 5m` / `2h` / ISO-8601 for windows. Only applies before the cursor file exists.
- `--show-archived` emits events when messages disappear (off by default — self-loops are noisy when the watching agent is also the inbox owner).

**Don't process messages here.** This skill teaches the *plumbing*. To actually act on incoming messages by type, invoke the companion `/check-inbox` skill, which has the auto-execute rules. The recommended pattern: a Monitor running `oacp watch` emits `NEW_MESSAGE` lines as chat notifications; you respond to each by running `/check-inbox`.

## 4b. Message signing & trust (v0.4.2+)

OACP messages carry an optional detached-JWS **auth trailer** (Ed25519). Signing is opt-in per sender; verification posture is per receiver. Requires the `[crypto]` extra.

```bash
oacp key gen --agent claude                    # generate a signing key under $OACP_HOME/keys/
oacp key list                                  # inspect local keys
oacp trust import <kid>.pub.json \
  --project my-project --agent codex           # pin claude's identity for receiver codex
oacp trust list --project my-project           # catalog entries + receiver pins
oacp send my-project --from claude --to codex --type notification \
  --subject "signed hello" --body "..." --sign # sign one message explicitly
oacp verify <message.yaml> \
  --project my-project --receiver codex        # check the trailer against codex's pins
```

- **Sender side**: `--sign` signs one message; setting the sender's `signing.sign_messages` config knob signs every send by default.
- **Receiver side**: `signing.verify_mode` in `agents/<receiver>/config.yaml` — `warn` reports verification results without rejecting; `enforce` makes the autonomy gate reject anything not `signed-verified` at intake (evidence copy quarantined to `dead_letter/`, decision `intake_rejected`). Pin every peer **before** processing their first message — under enforce, an unpinned sender's messages cannot verify.
- **Audit stamping**: after an autonomy decision record exists, `oacp verify <msg> ... --attach-audit <audit.yaml>` writes the canonical `result.message_auth` block into it. Never hand-write that block.
- **Policy signing**: `oacp trust sign-policy --project <p> --agent <receiver>` signs the receiver's own policy files so the gate can detect tampering (`policy_auth` block in every decision).

## 5. Review loop — Author → Reviewer (direct)

The OACP review loop is **agent-to-agent direct dispatch**, not coordinator-mediated. When you open a PR and want review:

1. **Author sends `review_request` directly to the reviewer's inbox** (`--to <reviewer>`, `--related-pr <N>`). Do not route through a coordinator.
2. Reviewer's `/check-inbox` picks it up and dispatches `/review-loop-reviewer`.
3. Reviewer replies with `review_lgtm` (approve) or `review_feedback` (blocking / non-blocking findings).
4. On feedback, author runs `/review-loop-author` to address it, pushes the fix, sends `review_addressed` (informational), then sends a **fresh `review_request`** to trigger round N+1. The reviewer is stateless — `review_addressed` alone does not invoke a new review.
5. Loop until `review_lgtm`. Author merges.

When a 2-LGTM gate is enforced, it typically counts: author's self-review (informational, since GitHub Apps cannot formally approve their own PRs) + reviewer's `review_lgtm`.

**Continuation grants (v0.4.3+)**: receivers may enable `continuation_grants` in their autonomy config so that, after one human approval of a review loop, subsequent same-thread `review_request` rounds dispatch without a per-round confirm. The grant is run-authorization only — it never confers verdict authority, and reviewer-side guards apply identically on granted rounds. See the `/check-inbox` skill's autonomy reference for the full semantics.

## 6. Health checks

Run `oacp doctor` to verify environment, workspace, inbox health, schemas, and agent status:

```bash
oacp doctor                                       # env + global checks
oacp doctor --project <project>                   # full workspace + agent status
oacp doctor --project <project> --fix             # auto-fix safe issues (missing inboxes, stale timestamps)
oacp doctor --project <project> --fix --json      # structured output
```

For deeper diagnostics or interactive triage, invoke the companion `/doctor` skill.

## 7. Org memory (cross-project facts)

OACP supports an org-level memory layer at `$OACP_HOME/org-memory/` for facts that span projects (decisions, rules, recent events).

```bash
oacp org-memory init                                                 # bootstrap org-memory
oacp write-event --agent claude --project my-project \
  --type decision --slug api-style --body "Use REST for public APIs" # append a structured event
```

Use `oacp write-event` for structured cross-project facts (decisions, incidents, releases). Use `oacp send` for agent-to-agent messages within a project. They are different primitives — don't conflate.

## 8. Validating a message

If `oacp send` rejects a message, or you've inherited a hand-written YAML, validate it explicitly:

```bash
oacp validate <path-to-message.yaml>
```

This checks the YAML against the protocol schema and reports the first failure with field path and reason.

## 9. Conventions

- **Archive, don't delete.** Recipients move fully-processed messages to `inbox/archive/` with a no-clobber atomic move under the original filename — byte-preserving, so signed-message evidence survives. The legacy `processed/` directory is not a protocol location, and deleting loses receiver-side evidence. Pending, held, or approval-gated messages stay in `inbox/`.
- **Subject prefixes:** `WIP:` for in-progress updates, `Re:` for replies (auto-applied when you set `--parent-message-id`).
- **Priorities:** `P0` (blocker, page now) → `P3` (informational). Default to `P2`. Use `P1` for actionable-this-session.
- **Notify on merge, not on PR-open.** When working a `task_request`, the final completion `notification` goes after merge, not at PR-open. Use a `WIP:` notification for progress updates if needed.
- **One-message-one-task.** Don't pile multiple distinct asks into one message body — split into separate `task_request`s so each can be tracked and replied to independently.

## 10. Companion skills

| Skill | When to invoke |
|-------|----------------|
| `/check-inbox` | Process pending inbox messages by type. Pair with `oacp watch` for continuous monitoring. |
| `/doctor` | Run `oacp doctor` with auto-fix and report blockers. |
| `/review-loop-reviewer` | You received a `review_request` — analyze the PR and reply with findings. |
| `/review-loop-author` | You received `review_feedback` — apply fixes and reply with `review_addressed`. |
| `/self-improve` | Audit and improve your own skills, memory, and config. |

## Failure modes to recognize

- **`oacp send` succeeds, recipient never sees it.** The send can write the outbox copy and silently fail the inbox write. Always verify with `test -f "<inbox_path>"` against the path `oacp send` printed.
- **Filename hash ≠ `msg-id`.** A message with id `msg-20260430-claude-39dd` may land at `..._d453.yaml`. Verify by path, not by id grep.
- **Sandbox blocks `oacp send`.** If your runtime sandboxes filesystem writes outside the project repo, `$OACP_HOME` writes will fail. Surface the error to the user — don't paper over it.
- **Stale CLI.** If a flag listed here doesn't exist (`oacp watch --state-id`, `oacp verify --attach-audit`), re-run the version check from Section 1 — the installed CLI may be older than the contract.
- **Message held as unverified.** Under a receiver's `enforce` posture, a message from an unpinned or badly-signed sender is quarantined to `dead_letter/` instead of processing. That is the protocol working, not a bug — import the sender's key stub (`oacp trust import`) and have them re-send, or surface to the user if the signature is genuinely invalid.
