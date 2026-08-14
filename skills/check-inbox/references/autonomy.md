# Receiver autonomy — mode, 4-gate evaluator, audit, envelopes, grants, threshold checkpoint

Referenced from `SKILL.md` Step 4. Read this when processing a message whose type may auto-accept under `auto_review` (currently: `task_request`, `question`, `brainstorm_request`, `brainstorm_followup`, `handoff` — plus, on receivers with `continuation_grants` enabled, `review_request` / `review_addressed`). For pure-notification flows (`notification`, `handoff_complete`, `follow_up`) the gates do not apply — skip this file.

Implements OACP receiver autonomy as shipped through the oacp-cli 0.4.x line: the Phase 1 4-gate evaluator (v0.3.1), runtime envelope compilation (v0.4.1), signed intake with `verify_mode: enforce` and `dead_letter/` quarantine (v0.4.2), and thread-scoped continuation grants (v0.4.3). The conformance fixtures shipped with the OACP autonomy spec are the canonical decision contract — reason-code names and `matched_pattern` strings here are pinned to those fixtures, do not invent new spellings.

## A. Resolve receiver autonomy policy

Once per `/check-inbox` invocation, before iterating messages:

```bash
CONFIG_PATH="${INBOX_DIR%/inbox}/config.yaml"  # i.e. agents/<receiver>/config.yaml
```

- **Missing config** → `MODE=always_pause`. Skip gate evaluation. Treat every message under the legacy Step 5 rules in SKILL.md.
- **Malformed config** (YAML parse error, non-numeric thresholds, scalar `allow_without_task_profile`, unknown enum value for any `*_ops` / `*_side_effects` / `*_visibility` / `*_or_deploy` field) → `MODE=always_pause`, decision `paused` with `reason_codes: [config_malformed]`. Still write the audit event (section D) with `policy_path: null`, `policy_sha256: null`.
- **Valid config** → `MODE=<autonomy.default_mode>` (`always_pause` or `auto_review`). Cache `THRESHOLDS=autonomy.auto_review_thresholds` and `ALLOW_WITHOUT_PROFILE=autonomy.allow_without_task_profile` for gate evaluation. `policy_sha256` is the SHA-256 of a canonical, key-sorted serialization of the parsed policy (excluding any `auth` trailer key), so comments and formatting do not produce false drift.
- **Signed policy (v0.4.2+)**: the receiver config may carry its own policy signature. The gate records a `policy_auth` block (`status: unsigned | verified | invalid | unsupported`) in every decision; an `invalid` status fails closed with `policy_auth_invalid` — the gate refuses to evaluate a tampered policy, distinguishably from a merely malformed or absent one.

If `MODE=always_pause` (whether by config or by missing file), **skip sections B/C and process each message under the legacy Step 5 rules.** Audit events are still recorded (section D) for traceability: `decision: paused`, `reason_codes: [mode_always_pause]`.

## B. 4-gate evaluator (only when `MODE=auto_review`)

For each message, run gates in order with **early-out on the first failure**. On full pass, all accumulated pass codes go to the audit record. On failure, the failing gate's code(s) (plus `matched_pattern` when applicable) drive `reason_codes`; other pinned conditions that also held but did not drive the early-out are recorded in `co_occurring_reason_codes` (deduplicated, empty on auto-accepted decisions) so threshold-calibration analytics can read both together.

### Gate 1 — Message integrity

- **Signed intake (v0.4.2+)**: under a receiver config with `signing.verify_mode: enforce`, the message's auth trailer must verify as `signed-verified` against the receiver's pins **before** any other gate runs. Anything else — unsigned, unverifiable, invalid — is rejected at intake: a mode-600 evidence copy is quarantined to the agent's `dead_letter/` directory and the gate writes an `intake_rejected` decision instead of evaluating. Under `verify_mode: warn`, verification is reported but not enforced.
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

- **Block absent** → fail with `task_profile_missing` (or `risk_obvious_no_profile` when the body itself makes the risk obvious).
- **Block unparsable** (malformed YAML, non-block-scalar, schema mismatch) → fail with `task_profile_unparsable`; internally inconsistent declarations fail with `declaration_error`.
- **Block parses** → cross-check against `THRESHOLDS`, with one granular reason code per breach:
  - `estimated_minutes > max_estimated_minutes` → `estimated_minutes_exceeds_threshold`.
  - `expected_files_touched > max_expected_files_touched` → `expected_files_touched_exceeds_threshold`.
  - Boolean risk flags map to per-flag pause codes when `true` and the corresponding threshold knob is `pause`: `destructive_ops` → `destructive_ops_pause`, `touches_auth_config_or_secrets` → `auth_config_or_secrets_pause`, `touches_dependencies` → `dependency_changes_pause`, `public_visibility` → `public_visibility_pause`, `external_side_effects` → `external_side_effects_pause`. Receivers with the PR-artifact allowance configured admit `external_side_effects: true` only when the declared side-effect actions are PR artifacts (`creates_or_updates_pr`, `comments_on_github`, …); anything beyond that fails with `external_side_effects_not_pr_artifact`.
- The profile may also declare per-action side-effect booleans (`creates_or_updates_pr`, `comments_on_github`, `commits_changes`, `merges_pr`, `files_issues`, `sends_oacp_reply_only`), `target_repo`, `risk_tier`, and a `continuation_grants` request block (see section G) — all recorded into the audit event's `scope_envelope`.

Pass codes (when all pass): `task_profile_present`, `task_type_allowed`, `risk_threshold_passed`.

### Gate 3 — Receiver classification (hard stops, advisories, ambiguous scope)

Match each category case-insensitively against the message `body` with **word-boundary** semantics (a token must not match inside larger words such as `autonomy`, `author`, `secretary`; path-like tokens such as `packets/deploy/` are not deploy verbs). The first driving match becomes `matched_pattern`, recorded using the canonical casing below.

Since v0.4.2 the classifier distinguishes **non-demotable hard stops** from **demotable matches** that an honest declaration can downgrade to a logged advisory:

- **Destructive command tokens** (never demotable) → `hard_stop_destructive_command`. Tokens: `rm -rf`, `--force`, `--no-verify`, `--dangerously-skip-permissions`.
- **External side-effect verbs** → `hard_stop_external_side_effect`. Demotable verbs: `deploy`, `publish`, `merge`. Non-demotable phrases: `push to main`, `rotate credentials`, `install dependency` (inflected forms match).
- **Sensitive scope** → `hard_stop_sensitive_scope`. Declaration-aware tokens (tied to `touches_auth_config_or_secrets`): `auth`, `secrets`, `credentials`, and config-file phrasing (`config.yaml`, `config files`, `workspace config`, …). Non-demotable: `public repo` / `public repository`, `memory SSOT`.
- **Content sensitivity** (never demotable, reported separately from action risk) → `hard_stop_content_sensitivity`. Tokens: `pricing`, `commercial`.
- **Ambiguous file scope** → `file_scope_ambiguous`. Phrase: `all files`.

**Demotion rules** (all recorded as `lexical_advisory` notes so fenced or demoted text is never invisible to the audit):

- A **complete, consistent profile** whose corresponding declaration is `false` demotes side-effect and sensitive-scope matches to a logged `lexical_advisory`. Missing, unparsable, or contradictory profiles get no demotion.
- A profile explicitly declaring `merges_pr: true` demotes the lexical `merge` match to `lexical_advisory_declared` so the declared merge reaches the granular Gate-2 path — it still pauses there on first admission, and only a human-approved continuation grant covering `merges_pr` admits the follow-up. Merge wording **without** the declaration stays a hard stop.
- **Sender-marked guardrail fences**: a well-formed ` ```oacp-guardrails ` fenced block (non-operative safety language like "Do not merge, deploy, or publish") is excluded from demotable pause classification; its matches are logged as advisories. Non-demotable classes are scanned across the raw body and remain hard even inside the fence.
- **Negation clauses**: demotable matches in clauses headed by `no`, `not`, `never`, `do not`, `out of scope`, `exclude(d)`, `avoid`, `prohibited`, `forbidden`, and similar are suppressed (a negation-form Markdown heading scopes over its following block, ending at the first blank line or next heading). Non-demotable hard stops remain hard even in negated clauses.
- For types listed in `allow_without_task_profile`, demotable side-effect verbs are logged as notes instead of hard stops; destructive tokens still pause.

Hard stops are enforced even if `MODE=auto_review` — for non-demotable classes, the body wins over any declaration.

Pass code (when no Gate 3 pattern drives a pause): `hard_stops_clear`.

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
- Signed-intake failure under `verify_mode: enforce` (v0.4.2+) → `decision: intake_rejected` with the evidence copy quarantined to `dead_letter/`; the message is never evaluated or executed.
- `MODE=always_pause` → `decision: paused`, `mode: always_pause`, `reason_codes: [mode_always_pause]`. Legacy rules.
- Review-lifecycle messages on receivers with `continuation_grants` enabled get `review_continuation_*` verdicts instead — see section G.
- LLM judgment may reduce false positives only **after** all four deterministic gates pass. It must never override a hard-stop fail.

Tell the user the verdict before executing: `"<msg-id> — auto_accepted (auto_review mode)"` or `"<msg-id> — paused (reason: <codes>)"`.

## D. Audit event writing (every decision)

Write one YAML file per decision to:

```
${INBOX_DIR%/inbox}/audit/autonomy_decisions/<YYYYMMDDTHHMMSSZ>_<message-id>.yaml
```

Create the directory if missing (`mkdir -p "${AUDIT_DIR}"`). The full file shape is pinned by the OACP autonomy spec's "Audit Events" section (schema_version 2 since v0.4.3) — the spec is canonical; this is the working summary:

```yaml
schema_version: 2
spec_version: "0.4.3"
created_at_utc: "<now in UTC, ISO-8601 Z>"
receiver: <agent>
sender: <message.from>
message_id: <message.id>
message_type: <message.type>
message_subject: <message.subject>
conversation_id: <message.conversation_id, or null>   # thread identity (schema v2)
parent_message_id: <message.parent_message_id, or null>
message_path: <path relative to project root, e.g. agents/<agent>/inbox/...yaml>
message_sha256: <hash from Gate 1>
decision: <auto_accepted | paused | intake_rejected>
mode: <auto_review | always_pause>
policy_path: <agents/<receiver>/config.yaml, or null if config missing/malformed>
policy_sha256: <canonical policy hash, or null>
policy_auth: {status: <unsigned|verified|invalid|unsupported>, signer_agent: ..., signer_kid: ..., reason: ...}
reason_codes:
  - <code>
matched_pattern: <token from Gate 3, only when applicable>
co_occurring_reason_codes: []      # pinned codes that also held but did not drive the early-out
breached: []
thresholds:
  max_estimated_minutes: <from config>
  max_expected_files_touched: <from config>
scope_envelope: {...}              # normalized profile: time, files, risk + side-effect booleans, grants
task_profile: {...}                # declared profile as sent
continuation_grant: {present: ..., enabled: ...}
logged_notes: []                   # lexical advisories (lexical_advisory, lexical_advisory_declared)
runtime:
  agent: <agent>
  model: <serving model id>        # normalized at the writer; null only with a reason
  model_source: "env:OACP_RUNTIME_MODEL"
evaluator: {source: ..., content_sha256: ..., git_sha: ..., executed: true}
result:
  final_state: <pending until Step 5 completes; updated to done|paused|error>
  completion_kind: <auto_accepted | admission_paused | ...>
  envelope_enforcement: <hooks | none>
  threshold_checkpoint: {...}      # section E outcome, incl. declaration_errors + reauthorization
  human_outcome: {...}             # recorded human decision + grant decision, when a pause was cleared
  message_auth: {...}              # stamped via `oacp verify --attach-audit`, never hand-written
  reply_message_id: <msg-id of any oacp send reply, or null>
  artifacts: []
```

Write the file immediately after gate evaluation with `final_state: pending`, then update it after Step 5 completes. If updating fails, leave the `pending` record in place — partial audit beats none. Record human decisions on paused records with `oacp autonomy-outcome <audit.yaml> --decision approved|declined|modified` (add `--grant-decision` when the profile requested a continuation grant) rather than hand-editing the YAML.

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
3. **Update the audit event** for this message: record the breach in `result.threshold_checkpoint` (`breached: true`, `breached_fields`, `breach_basis`; a contradictory or dishonest declaration discovered mid-run records `declaration_errors` and the pinned `declaration_error` reason code), set `result.final_state: paused`, record the notification's `reply_message_id`.
4. **Surface to the user** for explicit re-authorization. Do **not** delete the original inbox message — the resumed work still needs the context. A granted re-authorization is recorded in `result.threshold_checkpoint.reauthorization` (channel, actor, decision, scope) — `checkpoint_reauthorized` on success, `checkpoint_reauthorization_stale` when the state moved on before the decision landed.

This checkpoint is mandatory regardless of `--autonomous` flag state.

## F. Envelope compilation (v0.4.1+)

On an `auto_accepted` profile-carrying task, compile the declared `task_profile` plus receiver policy into a runtime envelope **before** executing:

```bash
oacp envelope compile --project "${PROJECT}" --agent "${AGENT_NAME}" --message "<inbox-file>" --oacp-dir "${OACP_HOME}"
```

This writes `active_envelope.json` under the agent's workspace `state/` directory; runtimes with an action-layer hook (e.g., a PreToolUse shim) enforce the declared constraints on every tool call. The compiler imports the autonomy gate's own normalization and pattern constants, so admission and runtime enforcement cannot drift. Rules:

- **Fail closed**: a compile failure pauses the task with `envelope_compile_error` instead of executing unenforced.
- **Clear at completion**: run `oacp envelope clear` once the task reaches a terminal state — before any unrelated later work, or the leftover envelope will deny it.
- Record `result.envelope_enforcement: hooks` (hook shim active) or `none` (no enforcement layer available) in the audit event.
- **Default envelope (v0.4.2+)**: profileless-but-eligible classes (e.g., `brainstorm_request` under `allow_without_task_profile`) compile a restrictive default envelope rather than running unenforced. Skip gracefully on older CLIs without the `envelope` subcommand.

## G. Continuation grants (v0.4.3+)

Standing, thread-scoped authorization that survives the first human approval — so an approved multi-round task doesn't re-prompt on every follow-up in the same thread. Off by default; enable per receiver in `config.yaml` (`autonomy.continuation_grants`).

- **Requesting**: the sender's `task_profile` may carry a `continuation_grants` block, e.g. `approved_thread_continuation.scope: {max_actual_minutes, max_actual_files_touched, creates_or_updates_pr, commits_changes, merges_pr}`. The request is recorded in the audit event; it grants nothing by itself.
- **Granting**: only a human decision grants — record it with `oacp autonomy-outcome <audit.yaml> --decision approved --grant-decision approved`. The grant binds to the sender + thread (`conversation_id` / `parent_message_id`) that received approval.
- **Consuming**: a later message in the same thread evaluates against the granted scope instead of re-pausing — `continuation_grant_accepted` on success; `continuation_grant_scope_exceeded`, `continuation_grant_missing_thread`, `continuation_grant_missing_approval`, `continuation_grant_denied`, or `continuation_grant_ignored_disabled` otherwise. Work outside the granted scope pauses like any other breach.
- **Review-loop grants**: a standing human-approved `review_loop` grant lets `review_request` rounds in the same sender/thread dispatch without a per-round confirm (`review_continuation_accepted`); other `review_continuation_*` codes (expired, revoked, round-exceeded, scope-exceeded, head-mismatch, confirmation-required) mean no valid grant. A grant is **run-authorization only** — it never confers verdict authority, and every reviewer-side guard applies identically on granted rounds.
