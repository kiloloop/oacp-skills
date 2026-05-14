# Receiver autonomy — mode, 4-gate evaluator, audit, threshold checkpoint

Referenced from `SKILL.md` Step 4. Read this when processing a message whose type may auto-accept under `auto_review` (currently: `task_request`, `question`, `brainstorm_request`, `brainstorm_followup`, `handoff`). For pure-notification flows (`notification`, `review_lgtm`, `review_addressed`, `handoff_complete`), the gates do not apply — skip this file.

Implements OACP Phase 1 autonomy (oacp-cli v0.3.1+). The conformance fixtures shipped with the OACP autonomy spec are the canonical decision contract — reason-code names and `matched_pattern` strings here are pinned to those fixtures, do not invent new spellings.

## A. Resolve receiver autonomy policy

Once per `/check-inbox` invocation, before iterating messages:

```bash
CONFIG_PATH="${INBOX_DIR%/inbox}/config.yaml"  # i.e. agents/<receiver>/config.yaml
```

- **Missing config** → `MODE=always_pause`. Skip gate evaluation. Treat every message under the legacy Step 5 rules in SKILL.md.
- **Malformed config** (YAML parse error, non-numeric thresholds, scalar `allow_without_task_profile`, unknown enum value for any `*_ops` / `*_side_effects` / `*_visibility` / `*_or_deploy` field) → `MODE=always_pause`, decision `paused` with `reason_codes: [config_malformed]`. Still write the audit event (section D) with `policy_path: null`, `policy_sha256: null`.
- **Valid config** → `MODE=<autonomy.default_mode>` (`always_pause` or `auto_review`). Cache `THRESHOLDS=autonomy.auto_review_thresholds` and `ALLOW_WITHOUT_PROFILE=autonomy.allow_without_task_profile` for gate evaluation. Compute `POLICY_SHA256=$(shasum -a 256 "$CONFIG_PATH" | awk '{print $1}')`.

If `MODE=always_pause` (whether by config or by missing file), **skip sections B/C and process each message under the legacy Step 5 rules.** Audit events are still recorded (section D) for traceability: `decision: paused`, `reason_codes: [mode_always_pause]`.

## B. 4-gate evaluator (only when `MODE=auto_review`)

For each message, run gates in order with **early-out on the first failure**. On full pass, all accumulated pass codes go to the audit record. On failure, ONLY the failing gate's code(s) (plus `matched_pattern` when applicable) go to the audit record — accumulated pass codes are discarded.

### Gate 1 — Message integrity

- Message YAML parses and validates against the OACP schema (required fields: `id`, `from`, `to`, `type`, `priority`, `created_at_utc`, `subject`, `body`).
- Message has not expired (if `expires_at_utc` is present, current UTC time must be earlier).
- Compute `MESSAGE_SHA256=$(shasum -a 256 "$msg_path" | awk '{print $1}')` and record it.
- Message ID has not already been auto-accepted by this receiver (check `agents/<receiver>/audit/autonomy_decisions/` for an existing file referencing this `message_id` with `decision: auto_accepted`).
- `autonomy_hint`, if present, is **advisory only** — never escalates the verdict.

Pass codes: `message_valid`, `message_not_expired`, `message_hash_recorded`.
Fail codes: `message_invalid`, `message_expired`, `message_replayed`.

### Gate 2 — Declared task profile

Required for `task_request` and `question`. Types listed in `ALLOW_WITHOUT_PROFILE` (default: `brainstorm_request`) may auto-accept without a profile and get `task_profile_not_required` + `task_type_allowed`. All other types fall through with the same two codes.

For types requiring a profile, extract a YAML block from `body` that begins with `task_profile:` (block-scalar form). Parse it.

- **Block absent** → fail with `task_profile_missing`.
- **Block unparsable** (malformed YAML, non-block-scalar, schema mismatch) → fail with `task_profile_unparsable`.
- **Block parses** → cross-check against `THRESHOLDS`:
  - `estimated_minutes > max_estimated_minutes` → fail with `risk_threshold_exceeded`.
  - `expected_files_touched > max_expected_files_touched` → fail with `risk_threshold_exceeded`.
  - Any boolean risk flag (`destructive_ops`, `external_side_effects`, `touches_auth_config_or_secrets`, `touches_dependencies`, `public_visibility`) is `true` AND the corresponding threshold knob is `pause` → fail with `risk_threshold_exceeded`.

Pass codes (when all pass): `task_profile_present`, `task_type_allowed`, `risk_threshold_passed`.

### Gate 3 — Receiver classification (hard stops, ambiguous scope)

Match each category case-insensitively against the message `body`. Stop on the **first** match across categories evaluated in the order listed below (matched substring becomes `matched_pattern`, recorded verbatim using the canonical casing below, not the casing found in the body).

- **Destructive command tokens** → fail with `hard_stop_destructive_command`. Patterns (substring match — these are unambiguous command-line tokens with `-` / spaces): `rm -rf`, `--force`, `--no-verify`, `--dangerously-skip-permissions`. `matched_pattern` is the canonical token (e.g. `rm -rf`).
- **External side-effect verbs** → fail with `hard_stop_external_side_effect`. Patterns (substring match, case-insensitive): `deploy`, `push to main`, `merge the pr`, `publish`, `rotate credential` (matches `rotate credentials` too), `install the new dependency`, `install dependency`. `matched_pattern` is recorded lowercase (e.g. `deploy`).
- **Sensitive scope** → fail with `hard_stop_sensitive_scope`. **Word-boundary** match required (regex `\b<token>\b` semantics; do not match inside larger words such as `autonomy`, `author`, `authorize`, `secretary`). Patterns: `auth`, `secret`, `secrets`, `credential`, `credentials`, `public repo`, `pricing`, `commercial`, `memory SSOT`. `matched_pattern` is recorded as the canonical token (e.g. `auth`, not `auth config`).
- **Ambiguous file scope** → fail with `file_scope_ambiguous`. Substring match (these are multi-word phrases, low false-positive risk). Bright-line phrases that contradict the declared `expected_files_touched`: `all files`, `all of the files`, `every file`, `entire repository`, `entire repo`, `the whole codebase`, `across the codebase`. `matched_pattern` is the canonical phrase as listed.

Hard stops are enforced even if `MODE=auto_review` and `task_profile` declared the risk flag `false` — the body wins over the declaration.

> **Word-boundary discipline**: a body like `"explaining OACP autonomy to new users"` must NOT trigger `auth`. A body like `"Update auth config, secrets handling..."` MUST trigger `auth`. The boundary check is the difference. When in doubt, treat the token as a whole word.

Pass code (when no Gate 3 pattern matches): `hard_stops_clear`.

### Gate 4 — Runtime / workspace

Verdict is **conditional** on workspace state checked at execution time, not at gate evaluation:

- Will the receiver's worktree be clean, or can the task be isolated to a fresh branch?
- Is any conflicting active task running on the same repo?
- Are the required tools available?

Gate 4 records `workspace_check_required` and lets the message auto-accept; the runtime must verify before actually starting work and pause if anything fails. If the runtime cannot verify (no repo context, tool unavailable), it must self-pause with `workspace_check_failed`.

Pass code: `workspace_check_required`.

## C. Verdict

- All gates pass → `decision: auto_accepted`, `mode: auto_review`. SKILL.md Step 5 proceeds **without human confirmation**, even for `task_request` and `question` types that would otherwise prompt.
- Any gate fails → `decision: paused`, `mode: auto_review`. SKILL.md Step 5 processes the message under legacy rules (ask the user before acting; do not delete the message until processed).
- `MODE=always_pause` → `decision: paused`, `mode: always_pause`, `reason_codes: [mode_always_pause]`. Legacy rules.
- LLM judgment may reduce false positives only **after** all four deterministic gates pass. It must never override a hard-stop fail.

Tell the user the verdict before executing: `"<msg-id> — auto_accepted (auto_review mode)"` or `"<msg-id> — paused (reason: <codes>)"`.

## D. Audit event writing (every decision)

Write one YAML file per decision to:

```
${INBOX_DIR%/inbox}/audit/autonomy_decisions/<YYYYMMDDTHHMMSSZ>_<message-id>.yaml
```

Create the directory if missing (`mkdir -p "${AUDIT_DIR}"`). The file shape is pinned by the OACP autonomy spec's "Audit Events" section:

```yaml
schema_version: 1
spec_version: "0.3.0"
created_at_utc: "<now in UTC, ISO-8601 Z>"
receiver: claude
sender: <message.from>
message_id: <message.id>
message_type: <message.type>
message_subject: <message.subject>
message_path: <path relative to project root, e.g. agents/claude/inbox/...yaml>
message_sha256: <hash from Gate 1>
decision: <auto_accepted | paused>
mode: <auto_review | always_pause>
policy_path: <agents/<receiver>/config.yaml, or null if config missing/malformed>
policy_sha256: <POLICY_SHA256, or null>
reason_codes:
  - <code>
matched_pattern: <substring from Gate 3, only when applicable>
thresholds:
  max_estimated_minutes: <from config>
  max_expected_files_touched: <from config>
task_profile:
  estimated_minutes: <from message, or null>
  expected_files_touched: <from message, or null>
  destructive_ops: <from message, or null>
runtime:
  agent: claude
  model: <current model id>
result:
  final_state: <pending until Step 5 completes; updated to done|paused|error>
  reply_message_id: <msg-id of any oacp send reply, or null>
  artifacts: []
```

Write the file immediately after gate evaluation with `final_state: pending`, then update it after Step 5 completes. If updating fails, leave the `pending` record in place — partial audit beats none.

## E. Threshold-exceeded checkpoint (post-acceptance)

After an auto-accepted task starts executing, the receiver **must self-pause** if the work expands beyond the declared `task_profile`. Conditions:

- Actual files touched > declared `expected_files_touched`.
- Actual estimated time grew past `max_estimated_minutes`.
- Work now requires a capability the profile declared as `false` (e.g., the task expanded into credential access, dependency change, or destructive-op territory).
- Work now matches a Gate 3 pattern the original message did not.

On any of these:

1. **Stop** before the action that would breach.
2. **Notify the sender** via `oacp send` with a `notification` reply on the original `parent_message_id`. Use one of these canonical body openers so senders can pattern-match the pause:
   - `Blocked: autonomy threshold exceeded — files_touched expected <N>, now <M>`
   - `Blocked: autonomy threshold exceeded — prompt was docs-only, now requires <capability>`
   - `Blocked: autonomy threshold exceeded — task expanded into untyped/unconfigured capability`
3. **Update the audit event** for this message: append `reason_codes: [+threshold_exceeded_post_accept]`, set `result.final_state: paused`, record the notification's `reply_message_id`.
4. **Surface to the user** for explicit re-authorization. Do **not** delete the original inbox message — the resumed work still needs the context.

This checkpoint is mandatory regardless of `--autonomous` flag state.
