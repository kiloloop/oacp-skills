# Receiver autonomy — Codex execution adapter

Use this reference for gate-eligible inbox messages: `task_request`, `question`,
`brainstorm_request`, `brainstorm_followup`, and `handoff`. Also use the
canonical evaluator's generic continuation-grant path for review invocation
candidates (`review_request` or standalone `review_addressed`) when recognition
is enabled. Coalesce addressed context with a newer same-PR request first.
Skip it for notifications, follow-ups, `review_feedback`, `review_lgtm`, and
`handoff_complete`; an unlisted `review_addressed` remains context-only unless
the human explicitly approves its invocation.

This file is an execution adapter, not a copy of the autonomy specification.
The active runtime's `docs/protocol/autonomy.md`,
`tests/conformance/autonomy/`, and `scripts/autonomy_gate.py` are authoritative.
Copy the evaluator's `schema_version` and `spec_version` rather than
receiver-composing them into new records.

## Contents

1. Execute the canonical evaluator
2. Interpret the four gates and safe fallback
3. Adopt and enrich the audit record
4. Record human outcomes
5. Enforce checkpoints and continuation grants
6. Finalize the audit

## 1. Execute the canonical evaluator

### Locate one active runtime

Require `oacp-cli[crypto]>=0.5.4`. Resolve the interpreter from the active
`oacp` entry point and use that interpreter's installed package for every
intake, admission, outcome, checkpoint, terminal, and validation operation.
A checkout is optional supplemental protocol evidence, not a prerequisite.

```bash
OACP_PYTHON="$(python3 - <<'PYTHON'
from pathlib import Path
import shlex, shutil, subprocess
entry = shutil.which("oacp")
if not entry:
    raise SystemExit("oacp CLI not found")
line = Path(entry).read_text(encoding="utf-8").splitlines()[0]
if not line.startswith("#!"):
    raise SystemExit("cannot resolve the oacp interpreter; hold intake")
parts = shlex.split(line[2:])
if parts and Path(parts[0]).name == "env" and len(parts) == 2:
    interpreter = shutil.which(parts[1])
elif len(parts) == 1:
    interpreter = parts[0]
else:
    raise SystemExit("unsupported oacp launcher; hold intake")
if not interpreter or not Path(interpreter).is_file():
    raise SystemExit("oacp interpreter unavailable")
probe = subprocess.run(
    [interpreter, "-c", "import sys; assert sys.version_info >= (3, 10); import oacp"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
if probe.returncode != 0:
    raise SystemExit("unsupported oacp launcher; expected Python with oacp; hold intake")
print(interpreter)
PYTHON
)" || exit 1
AUTONOMY_SCRIPTS="$("$OACP_PYTHON" - <<'PYTHON'
import oacp
from pathlib import Path
package = Path(oacp.__file__).resolve().parent
source = package.parent / "scripts"
print(source if (source / "autonomy_gate.py").is_file() else package / "_scripts")
PYTHON
)" || exit 1
GATE_SCRIPT="$AUTONOMY_SCRIPTS/autonomy_gate.py"
OUTCOME_CMD=("$OACP_PYTHON" "$AUTONOMY_SCRIPTS/record_autonomy_outcome.py")
FINALIZE_CMD=("$OACP_PYTHON" "$AUTONOMY_SCRIPTS/finalize_autonomy_record.py")
CONFIG_PATH="${INBOX_DIR%/inbox}/config.yaml"
AUDIT_DIR="${INBOX_DIR%/inbox}/audit/autonomy_decisions"
```

Require all three files and their `--help` calls to succeed before any audit
write. Keep these resolved commands for the task; do not mix installed and
checked-out writers during resumption. A missing writer or unsupported launcher
is a capability blocker: retain the message rather than hand-simulating a
compatible record. The bundled snapshot reader independently uses the same
active CLI interpreter and installed package.

Shell variables and arrays may not survive separate tool calls. Retain the
literal resolved interpreter and script paths and reconstruct these command
vectors when needed; never substitute a different writer after a pause.

### Resolve pre-existing state before evaluation

Search `AUDIT_DIR` by parsed content, not filename, for the same `receiver` and
`message_id`:

- adopt an existing paused or otherwise nonterminal record rather than writing
  a duplicate;
- if a peer has already auto-accepted the message, treat the message as already
  claimed/replayed and do not start the work in a second session;
- an audit with terminal completion evidence plus a still-queued original is a
  cleanup inconsistency: verify the reply/artifacts, then ask before archival;
- never infer identity from a filename alone.

The evaluator's replay rule is intentionally strict: a prior
`decision: auto_accepted` yields `message_replayed` and does not write another
audit. Duplicate watcher delivery is therefore a skip/ownership signal, not a
second execution opportunity.

### Resolve receiver configuration

The canonical evaluator preserves conservative defaults:

- a missing config resolves to `always_pause`;
- a valid mapping with no `autonomy` block, including a signing-only config,
  also resolves to `always_pause` and is not malformed;
- malformed autonomy policy produces `decision: paused`,
  `completion_kind: config_malformed`, and
  `reason_codes: [config_malformed]`;
- a valid autonomy block selects `always_pause` or `auto_review` and its own
  thresholds, allowlists, and continuation-grant setting.

The CLI entrypoint requires a config file. When the receiver config is absent,
never create a policy merely to evaluate a message. Use the vetted module form
below with the accepted view and exact raw snapshot. It runs the real evaluator
with an empty policy mapping, explicitly records absent-policy metadata as YAML
null, and uses the canonical identity-locked persistence transaction. This is
an executed conservative pause, not hand evaluation or a fabricated envelope.
Do not pass `None` as `policy_path` to a writer and assume it becomes YAML null:
the writer's fallback stringifies that argument.

```bash
"$OACP_PYTHON" - "$AUTONOMY_SCRIPTS" "$CONFIG_PATH" \
  "$MESSAGE_SNAPSHOT_RAW" "$MESSAGE_VIEW_JSON" "$MSG_FILE" "$AUDIT_DIR" <<'PYTHON'
import hashlib, json, sys
from pathlib import Path
scripts, policy, snapshot, view_path, canonical_path, audit_dir = map(Path, sys.argv[1:])
sys.path.insert(0, str(scripts))
import autonomy_gate as gate
import yaml
from finalize_autonomy_record import validate_audit_record
if policy.exists() or policy.is_symlink():
    raise SystemExit("policy appeared or is symlinked; rerun canonical intake")
view = json.loads(view_path.read_text(encoding="utf-8"))
raw = snapshot.read_bytes()
message = view.get("message")
if (view.get("held") or view.get("error") or view.get("policy_error")
        or view.get("verify_mode") not in ("off", "warn", "enforce")
        or (view.get("verify_mode") == "enforce"
            and (view.get("message_auth") or {}).get("status") != "verified")
        or view.get("validation_errors") or not isinstance(message, dict)
        or hashlib.sha256(raw).hexdigest() != view.get("message_sha256")):
    raise SystemExit("accepted snapshot binding failed; retain the message")
decision = gate.evaluate_autonomy(
    message, {}, receiver="codex", message_raw=raw, audit_dir=audit_dir,
)
if decision.get("decision") != "paused" or decision.get("reason_codes") != ["mode_always_pause"]:
    raise SystemExit("unexpected missing-policy verdict; retain the message")
# These keys describe the absent policy, not invented admission authority.
decision.update(policy_path=None, policy_sha256=None)
result = gate.persist_evaluation(
    audit_dir, decision, config={}, message=message, message_path=canonical_path,
    policy_path=policy, receiver="codex",
)
record = yaml.safe_load(Path(result["audit_path"]).read_text(encoding="utf-8"))
assert record["policy_path"] is None and record["policy_sha256"] is None
assert record["scope_envelope"] is None and record["decision"] == "paused"
assert record["message_sha256"] == view["message_sha256"]
assert record["receiver"] == "codex" and record["message_id"] == message["id"]
assert not validate_audit_record(record)
print(json.dumps({"audit_path": str(result["audit_path"]), "decision": record["decision"]}))
PYTHON
```

Retain the canonical `evaluator.executed: true` provenance and null threshold
caps. If this supported API, locked write, or readback is unavailable or fails,
retain the message and report the blocker; never act without its pause record.
For a config that exists, including signing-only configuration, use the CLI
form below instead. Both paths require explicit human approval before paused
work executes and use the same null-envelope execution-evidence rules.

### Run and persist the decision

Pass the exact `autonomy_decisions` directory, never its parent `audit/`:

Before running the command, set `SERVING_MODEL_ID` to the exact model identifier
from current-session serving metadata when that signal is available. Do not set
it from requested-model configuration, a config alias, or a user preference.

```bash
GATE_JSON="$(mktemp)"
mkdir -p "$AUDIT_DIR"
GATE_RC=0
(
  if [ -n "${SERVING_MODEL_ID:-}" ]; then
    export OACP_RUNTIME_MODEL="$SERVING_MODEL_ID"
  else
    unset OACP_RUNTIME_MODEL
  fi
  "$OACP_PYTHON" "$GATE_SCRIPT" \
    --config "$CONFIG_PATH" \
    --message "$MSG_FILE" \
    --audit-dir "$AUDIT_DIR" \
    --receiver codex \
    --oacp-dir "$OACP_ROOT"
) >"$GATE_JSON" || GATE_RC=$?
```

The subshell confines `OACP_RUNTIME_MODEL` to this invocation. It also removes
any inherited value when serving metadata is unavailable, so the writer records
an explicit unknown instead of accepting stale or requested-model state.
Apply the same rule to `OACP_RUNTIME_EFFORT` when actual serving effort is
observable; unset it when unknown. Terminal runtime flags or environment values
must describe the serving session, never a requested settings value.

Exit `0` means the decision was evaluated, including a fail-closed pause. Exit
`3` is terminal `intake_rejected` under enforce mode: surface the returned
authentication status and quarantine path, do not expect or create an autonomy
audit, and never route the message body. Any other code is an operational
failure and leaves the original inbox file retained.

On success, `--audit-dir` writes one complete lock-serialized YAML record as
well as printing the decision JSON. Require its `message_sha256` to equal the
immutable `ACCEPTED_MESSAGE_SHA256`; a mismatch means the live path
changed between snapshots, so retain it and do not act. Resolve `AUDIT_PATH` by
parsed record identity (`message_id` plus `receiver`) and verify that exactly
one current record was created or adopted. A successful evaluator that writes
no matching record is a runtime contract mismatch; do not synthesize an audit
record by hand.

The gate output includes the canonical:

- `decision`, `mode`, `reason_codes`, `co_occurring_reason_codes`,
  `logged_notes`, and optional `matched_pattern`;
- normalized `task_profile`, `scope_envelope`, `scope_envelope_source`,
  continuation-grant result, `breached`, raw-message hash, canonical policy
  hash, and `policy_auth`;
- `schema_version`, `spec_version`, receiver/thread identity, and `evaluator`;
- admission-time `result`, including the pinned `completion_kind`, human-outcome
  placeholder, checkpoint, and `envelope_enforcement`.

An executed result always outranks a prose interpretation of the same message.

## 2. Interpret the four gates and safe fallback

Use this section to understand evaluator output. Hand-evaluate only when no
canonical evaluator is reachable. If a pinned result cannot be produced, do
not claim `auto_accepted`: retain the message, surface the unavailable
evaluator, and use the human approval path rather than inventing schema values.

### Gate 1 — integrity

The gate performs mechanism-owned intake before Gate 1. `off` skips message
verification; `warn` annotates every outcome but does not reject or grant
authority; `enforce` allows only `signed-verified` and exits `3` before parsing
or evaluation for every other outcome. The gate reads one bounded message
snapshot, verifies and parses those same bytes, and records their full-file hash
as `message_sha256`.

Policy authorization also precedes config parsing. An enrolled policy that is
unsigned, tampered, or unverifiable fails closed; a bad receiver config pauses
with `policy_auth_invalid` before its own `verify_mode` or autonomy fields can
weaken the decision. The emitted `policy_auth` identity must be preserved.

Gate 1 then validates the entire message with the current OACP schema, checks
expiry, and checks receiver audits for replay. Canonical pass codes include
`message_valid`, `message_not_expired`, and `message_hash_recorded`; canonical
failures include `message_invalid`, `message_expired`, and `message_replayed`.

### Gate 2 — declared profile and receiver policy

Task-like messages normally carry a machine-parseable body block:

```yaml
task_profile:
  estimated_minutes: 20
  risk_tier: P3
  expected_files_touched: 3
  destructive_ops: false
  external_side_effects: false
  touches_auth_config_or_secrets: false
  touches_dependencies: false
  public_visibility: false
  target_repo: ""
  creates_or_updates_pr: false
  comments_on_github: false
  commits_changes: false
  merges_pr: false
  files_issues: false
  sends_oacp_reply_only: true
  continuation_grants: {}
```

Types explicitly listed in `allow_without_task_profile` may omit it. Missing,
unparsable, contradictory, over-threshold, or receiver-disallowed declarations
pause with the evaluator's pinned reason. In particular:

- a profileless admitted request still receives the default envelope: 25
  minutes, 2 files, reply-only, all risk/side-effect flags false, empty target
  repo, and no continuation grants; its risk tier mirrors a valid message
  priority or defaults to `P2`;
- every decision records `scope_envelope_source: task_profile`,
  `default_profileless`, or `continuation_grant` for an accepted review
  invocation; a null admitted envelope is invalid and the writer refuses it;
- `target_repo` is empty/omitted or an `owner/repo` slug;
- supplied risk and granular capability values are booleans;
- any PR/comment/commit/merge/issue capability requires
  `external_side_effects: true`;
- `allow_pr_artifacts` applies only to declared private repositories in the
  receiver-controlled allowlist;
- `merges_pr: true` always receives one human admission checkpoint unless a
  valid prior continuation grant already covers it.

The receiver's allowlist, not `public_visibility: false`, establishes the
private-repository class.

### Gate 3 — deterministic hard stops

The executable classifies raw and declaration-aware body text. Never weaken
these non-demotable stops manually:

- destructive tokens such as `rm -rf`, `--force`, `--no-verify`, and
  `--dangerously-skip-permissions`;
- direct-main pushes and other actions the canonical evaluator classifies
  as hard stops; declaration-aware deployment, publication, credential, and
  dependency language follows the executable rather than a blanket list;
- public-repository, pricing/commercial, and memory-SSOT scope;
- sensitive or ambiguous file scope not safely excluded by a complete profile.

Guardrail fences, negation, path-like words, and declared granular capabilities
have precise executable semantics. Use the returned `matched_pattern` and
`logged_notes`; do not guess from substring matches.

### Gate 4 — runtime/workspace

`workspace_check_required` means Codex must verify the live repository,
worktree, conflicting task ownership, and required tools immediately before
execution. If that check fails or cannot be established, pause operationally
and retain the message. Do not invent a new admission reason code.

## 3. Adopt and enrich the audit record

The canonical location is:

```text
agents/codex/audit/autonomy_decisions/<timestamp>_<message-id>.yaml
```

Retain the evaluator-stamped `schema_version` and `spec_version` unchanged.
The persisted record must retain these top-level groups:

- message, receiver, sender, conversation, parent, path, and hash identity;
- decision, mode, policy path/hash/auth identity, reasons, co-occurring reasons,
  notes, thresholds, normalized profile, envelope source, breach list, and
  continuation-grant result;
- runtime identity and the evaluator block (`source`, `content_sha256`,
  best-effort `git_sha`, `executed`);
- the complete `result` mapping.

Copy `evaluator` verbatim. `content_sha256` is the load-bearing identity; never
substitute a remembered commit SHA. In a true no-evaluator fallback, record a
mapping with `executed: false` and no invented hashes.

Preserve the writer-resolved runtime block. Its model comes caller-first, then
from `OACP_RUNTIME_MODEL`; when neither is an actual serving-model signal the
writer records `model: null` plus `model_unknown_reason`. Never backfill from a
requested model or rewrite historical records.

The four pinned `result.completion_kind` values are:

- `auto_accepted`
- `admission_paused`
- `checkpoint_paused`
- `config_malformed`

They describe evaluation shape, not the eventual user decision or task outcome.
Never hand-overwrite `completion_kind`; the canonical checkpoint and terminal
writers own its transitions.

Preserve the evaluator-emitted admission state. Auto-accepted evaluations are
born `final_state: pending` with no top-level completion timestamp; paused
evaluations emit `final_state: paused`. Only terminal finalization writes
`done` after successful completion and records actuals, timestamp, checkpoint,
reply id, and artifacts. Preserve `completion_kind`, including
`admission_paused` after a human-approved admission completes. Legacy records
born `done` without `completed_at_utc` are still unfinalized; do not infer
completion from their run state alone.

### Attach mode-aware message authentication

When `MESSAGE_VIEW_JSON.message_auth` is non-null, attach it only after
`AUDIT_PATH` exists. Verify the private `MESSAGE_SNAPSHOT_RAW` copy, whose bytes
are already bound to both the snapshot-reader hash and gate hash; never reread
the live inbox path for attachment. Reuse the resolved verifier command
(installed `oacp verify`, or the bundled `message_verify.py` resolved from `AUTONOMY_SCRIPTS`):

```bash
ATTACHED_AUTH_JSON="$(mktemp)"
ATTACH_RC=0
oacp verify "$MESSAGE_SNAPSHOT_RAW" --project "$PROJECT" --receiver codex \
  --oacp-dir "$OACP_ROOT" --attach-audit "$AUDIT_PATH" --json \
  >"$ATTACHED_AUTH_JSON" || ATTACH_RC=$?
```

Accept exit `0` or `3`. Compare `status` and `payload_sha256` with the pre-parse
snapshot result; a mismatch is an internal intake inconsistency, so retain the
message. The attachment is the only supported writer for
`result.message_auth`. Never hand-write that block. In `off` mode, skip
attachment. If an adopted audit already contains it, compare and preserve it
rather than overwriting. Do not create a fake autonomy audit solely for
lifecycle traffic; surface that message's warn/enforce annotation without an
attachment.

## 4. Record human outcomes

### Round-one review approval

When asking to approve a round-1 review, offer a bounded
`approved_thread_continuation` grant in the same approval menu. First check
that receiver configuration enables recognition and the canonical outcome
recorder supports `--grant-decision` and `--grant-scope-file`. If either is
unavailable, report the prerequisite and offer one-round approval; do not
change receiver configuration as part of intake.

Display the exact repository/PR, sender, receiver, and verified thread binding,
plus a complete flat scope before asking. Keep the repository/PR identity in
the approval evidence; do not add unsupported keys to the grant scope.
Propose `allowed_types: [review_request, review_addressed]`, the review's
ordinary round cap (two by default, at most three without an explicit
extension), and an explicit UTC expiry within 24 hours of the offer. Show
`max_round` as the cumulative invocation ceiling, including round one, not a
number of additional rounds. Derive `max_actual_minutes` and
`max_actual_files_touched` from the review's finite execution budgets; explain
that these limits apply per invocation. Resolve missing budgets before
offering the grant. List each permitted effect, including
`writes_findings_packet` and `sends_oacp_reply`, and explicitly include
`comments_on_github` or `submits_github_review` only when covered by the
proposed review scope. Leave other effects false. A proposed scope is not
authority until the human selects it.

Offer these choices with the concrete bounds and effects visible:

1. Approve round one and the displayed bounded thread grant (recommended for
   an ordinary review loop).
2. Approve round one only; later rounds require separate approval.
3. Decline the review.

Accept explicit scope modifications. A bare “approve”, “yes”, or ambiguous
answer approves only the current round; it never silently selects the grant.
For the combined choice, write the approved flat scope to a private YAML file
and record `--decision approved --grant-decision approved
--grant-scope-file <scope.yaml>` through `OUTCOME_CMD`. Pass only the scope
mapping, not a `grant` wrapper. This also supports a receiver-proposed grant
when the sender requested none. Use `--grant-decision modified` with the exact
replacement scope for a modified grant, `denied` for a displayed grant the
human declines (including one-round-only approval), and `not_requested` only
when no grant decision was involved. Preserve the human's task decision
separately, including `declined` when the review is declined.

Read back `result.human_outcome` before starting: require the recorded task
decision and `grant.decision` to match the answer, and for a combined approval
require `grant.granted_scope` to match the approved scope. Record the human
authorization's exact pointer and repository/PR binding in the review's
execution evidence. Preserve existing outcomes rather than replacing them to
manufacture a grant. Later rounds still use section 5's canonical grant
resolution, exact-PR checks, and per-round live-head verification; ask again
only when approval is missing, expired, revoked, exceeded, or otherwise does
not cover the invocation or its effects. Each reviewer invocation still ends
after its one terminal response.

### Record the decision

For every paused gate-eligible message, record the explicit human decision
before acting on approval or closing a decline. Use `OUTCOME_CMD` from section 1
and the deciding human's stable, whitespace-free actor handle:

```bash
"${OUTCOME_CMD[@]}" "$AUDIT_PATH" \
  --decision <approved|modified|declined> \
  --actor <human-handle> \
  --grant-decision <approved|modified|denied|not_requested>
```

Use `--grant-scope-file` for a modified grant or an approved malformed request.
The recorder locks and atomically replaces the audit,
computes decision latency, preserves `message_auth`, and refuses an existing
outcome unless `--replace` is explicit. On a checkpoint pause with an existing
admission outcome, it records the new answer in
`result.threshold_checkpoint.reauthorization` and preserves that admission
outcome. Read back the answer from the block the recorder actually updated;
do not reuse the admission timestamp as a new checkpoint answer.

Task approval and grant approval are independent. A current-task approval
covers that task's declared capabilities, but a standing grant exists only
when the audit records a separate approved or modified grant scope.

When the receiver-side human chooses `modified` at admission and the change
adds a current-task capability that is false in the evaluator's immutable
`scope_envelope`, record the human outcome first but do not rewrite that
envelope. Before performing the newly authorized capability, evaluate a
prospective checkpoint with the original envelope and carry the exact human
decision into `actuals.reauthorization.receiver_human`:

```yaml
actuals:
  # Include the prospective measured actuals and side_effects_actual here.
  reauthorization:
    receiver_human:
      decision: modified
      decided_at_utc: <human_outcome.decided_at_utc>
      actor: <human_outcome.actor>
      scope:
        commits_changes: true
```

Use only the task-local scope the human explicitly added, and persist the
checkpoint with `FINALIZE_CMD --checkpoint --actuals` before acting. Proceed only
when its action is `resumed_after_reauthorization` and disposition is
`resumed`. `--grant-scope-file` is not the carrier for this current-task
modification; use it only when the human separately approves or modifies a
standing continuation grant. This preserves the sender-declared envelope
while making the receiver's modified authority executable and auditable.

## 5. Enforce checkpoints and continuation grants

Capture the task start time and baseline file set. Before performing any newly
discovered capability and again before terminal signaling, compare actual work
with the accepted profile or valid granted scope:

- elapsed minutes and distinct files touched stay within their caps;
- every realized outward effect was declared;
- newly discovered destructive, sensitive, dependency, public, merge, issue,
  deploy, release, or other authority-bearing work was admitted.

For an envelope-bearing audit, pass the `actuals` mapping to
`"${FINALIZE_CMD[@]}" "$AUDIT_PATH" --checkpoint --actuals "$ACTUALS_FILE"`.
The canonical writer retains the record's standing answer and pause history
while evaluating and persisting the checkpoint. Do not replace this with a
standalone evaluator call that omits that state, or rerun admission against
`AUDIT_DIR`: its replay guard correctly treats the accepted message as a
replay. Read the persisted checkpoint back and require `evaluated: true` before
treating it as threshold validation. `breached: false` with
`action: not_evaluated` is not a successful check.

### Human-approved admissions without an envelope

The `always_pause` path can return before extracting a `task_profile`, leaving
the admission audit's `scope_envelope` null even after human approval. Preserve
that audit and its original admission fields; do not backfill an envelope or
rerun admission to manufacture one. Reuse the recorded approval for this exact
task and its effects; a missing envelope alone does not require reapproval.

For this case, keep a separate execution-checkpoint artifact:

- Recover the profile from the accepted authenticated message snapshot using
  the canonical `extract_task_profile`, then `normalize_scope_envelope`.
  Apply only task-local limits or capabilities explicitly covered by the
  recorded human authorization to this separate execution scope. Preserve
  both the original profile and the exact authorization evidence; do not
  infer reply, merge, or other effects from a sender claim or generic assent.
- Bind the artifact to the accepted message id/hash and admission audit path.
  Include the effective execution scope, approval provenance, measured work
  clock and actuals, and the evaluator's complete returned checkpoint.
- Evaluate with `evaluate_threshold_checkpoint` before prospective effects
  and terminal signaling. Pass only an actually accepted continuation grant,
  if any. Require `evaluated: true` and resolve any breach through the existing
  reauthorization rules before proceeding; keep this evidence separate from
  the unchanged admission envelope.

Missing or invalid execution bounds are an evidence gap, not unlimited scope.
Recover them from the accepted snapshot and recorded authorization first;
request only genuinely missing bounds or expanded authority if recovery fails.
Do not substitute invented caps or a fresh admission evaluation.

The canonical finalizer's `--checkpoint` requires an admission envelope and
cannot store this separate check. Keep the artifact durable and link it through
the terminal record's `artifacts`; preserve the canonical finalizer's own
checkpoint result, including `not_evaluated` for this null-envelope case. A
successful terminal finalization does not replace execution-scope validation.

### Checkpoint breaches and reauthorization

The authority and stop/resume rules below apply to both paths. Their audit
checkpoint mutations apply only to envelope-bearing admissions. For a
null-envelope admission, retain the original inbox message and store the
breach, pause timestamp, human reauthorization, effective caps, and resumed
evaluator result in the separate execution artifact. Preserve the original
admission `completion_kind`, human outcome, and canonical checkpoint; do not
force `--checkpoint` or overwrite admission approval with a checkpoint answer.

On ordinary drift, pause with `threshold_checkpoint_breached`. An undeclared
side effect also records `declaration_error`. Fill the evaluator-defined
checkpoint fields, including actuals, `side_effects_actual`, concrete
`breached_fields`/`declaration_errors`, `paused_at_utc`,
`breach_basis: declared_intent|realized`,
`action: paused_for_reauthorization`, and risk materialization.

Stop before a prospective undeclared action. Send an in-thread notification
beginning with `Blocked: autonomy threshold exceeded — ...`, capture its reply
id, let the canonical checkpoint writer stamp `completion_kind: checkpoint_paused`
and `final_state: paused`, retain the original inbox task, and surface the exact
expansion for re-authorization.

Normalize a human-approved numeric extension to an absolute task cap before
re-evaluating the checkpoint. An "additional N minutes", "extend by N", or
approved `+N` adds to the current authorized cap, never to the elapsed time at
the moment of approval. Use the latest durable
`threshold_checkpoint.reauthorization.scope.max_actual_minutes` when present,
otherwise an accepted continuation grant's `max_actual_minutes`, otherwise
`scope_envelope.estimated_minutes`. For null-envelope admissions, use the
corresponding latest cap or execution scope from the separate artifact.
For example, a 20-minute envelope plus an additional 10 minutes becomes
`max_actual_minutes: 30`. An explicitly stated
absolute cap takes precedence. Read the computed absolute cap back to the user
before recording it; ask when the wording does not distinguish an increment
from an absolute limit.

Record the human answer through section 4, then present its exact decision,
timestamp, actor, and absolute cap to the checkpoint writer instead of
collapsing it to a scope-less approval. In this example, `recorded_answer`
means the answer read back from the recorder's updated block:

```yaml
actuals:
  # Include the measured actuals, side_effects_actual, and pause timestamp.
  reauthorization:
    receiver_human:
      decision: <recorded_answer.decision>
      decided_at_utc: <recorded_answer.decided_at_utc>
      actor: <recorded_answer.actor>
      scope:
        max_actual_minutes: 30
```

Before resuming, require `reauthorization.presented: true`, the expected
absolute cap in both `requested_scope` and effective `scope`,
`disposition: resumed`, and `action: resumed_after_reauthorization`. Preserve
that evaluated checkpoint through finalization, including when the work was
already complete when approval arrived. Do not prompt again while terminal
actuals remain within the granted cap; growth beyond it is a new breach.

For later checkpoints, re-present the recorded governing answer and its exact
scope without changing its decision timestamp. Validate after each write.
A scope-less answer cannot clear a later pause. A scoped prospective approval
may precede the pause when it is no earlier than work start and newer than the
record's previous governing answers; the current writer applies that scope at
the pause's own stamp. Preserve the true decision and pause times. Follow the
canonical repair path for an invalid older record; never backdate a pause or
restamp an old approval to manufacture validity. Ask again only when the
current canonical contract actually requires a fresh answer.

Continuation grants are default-off. A sender request or enabled receiver
configuration creates no authority. Use the canonical evaluator to resolve
`approved_thread_continuation` from prior receiver audits and recorded human
approval/modification of both the task and grant. Its flat scope requires
`allowed_types`, `max_round`, `expires_at_utc`, `max_actual_minutes`, and
`max_actual_files_touched`; effect booleans default to false. Follow the active
protocol's `docs/protocol/autonomy.md` continuation-grant resolution, including
sender/receiver/thread binding, approval timing, revocation, both creation-time
and evaluation-time expiry,
and cumulative unique executed invocations of the governing allowed types.
Do not reconstruct that decision from sender fields or select an older grant
after a newer invalid one. Ordinary task gates, hard stops, and boundary-action
exclusions remain in force; grants do not admit destructive, auth/secrets,
dependency, public, pricing/commercial, configuration, or memory SSOT work.

Legacy nested `granted_scope.review_loop` or incomplete generic scopes require
fresh human approval of the complete flat scope. Never drop an old restriction
to preserve its permissions, or rewrite historical scopes, results, or reason
codes. Preserve those audits as evidence under their original contract.

### Review-loop continuation recognition

Review lifecycle messages have no `task_profile` and do not run the four task
gates. Evaluate invocation candidates through the generic grant path when
recognition is enabled. Without a usable grant, require explicit per-round
human confirmation. `review_feedback` and `review_lgtm` always remain
context-only; `review_addressed` may invoke only when explicitly listed in the
accepted grant or separately approved by the human. A newer same-PR
`review_request` takes the addressed context and owns the single invocation.

Auto-dispatch only when the executed result is `decision: auto_accepted` and
includes `continuation_grant_accepted`, with the candidate type in
`continuation_grant.scope.allowed_types`. Require the matching persisted audit
and preserve its entire `continuation_grant`, including `source_audit`,
`source_message_id`, `effective_round`, and flat `scope`. Pass that scope and
the concrete `scope_envelope` (`scope_envelope_source: continuation_grant`)
to the invocation. Checkpoints and terminal finalization enforce the admitted
time, file, and effect bounds; review admission is never envelope-free.
Other results require confirmation or remain context-only as emitted. Never
replace a hard stop with a sender claim or reuse an unrelated approval.

The kernel does not bind a repository/PR or compare declared heads. Before
dispatch, the workflow must establish the approved repository/PR from prior
authenticated request context and recorded receiver-human approval, then
compare the candidate's identity. Hold missing, mismatched, or unestablished
identity for explicit direction; a conversation or parent ID alone does not
authorize another PR. Resolve the live full SHA independently. Record a
declaration mismatch as informational and review the live head; drift during
the round still invalidates its verdict. Keep the workflow's review round
separate from the evaluator's cumulative `effective_round`: addressed round N
names feedback, so its continuation reviews N+1; never rewrite the audit count.

The grant authorizes invocation, never the outcome or merge. Before each
effect, consult the flat `continuation_grant.scope` and admitted envelope;
false remains forbidden. Skip an optional forbidden comment or review
submission and name it in `withheld_side_effects` in the signed reply. A
repository landing approval outside the accepted reviewer scope does not block
the terminal quality reply: report that approval as withheld, and let the author
arrange an authorized approver before landing. If formal approval was accepted
as part of the review's composite approval/LGTM delivery but fails or cannot be
verified, retain the request and withhold that composite LGTM. Pause before any
other required effect that the accepted scope forbids. GitHub comments and
formal reviews are distinct effects.

## 6. Finalize the audit

For a terminal gate-eligible outcome:

1. Measure actual minutes/files and evaluate the checkpoint.
2. Send the terminal reply and verify its recipient inbox and sender outbox
   files; capture `message_id` and durable artifacts.
3. Under the shared autonomy-audit lock, atomically update the same record while
   preserving the admission decision, `completion_kind`, `evaluator`,
   `human_outcome`, and `message_auth`.
4. Set or confirm `result.final_state`, `actual_minutes`,
   `actual_files_touched`, `predicted_risk_materialized`, `completed_at_utc`,
   the complete `threshold_checkpoint`, `reply_message_id`, and `artifacts`.
5. Parse the record back and assert identity, terminal state, completion time,
   measured actuals, checkpoint action, and expected reply id.
   For a human-approved null-envelope admission, also read back the linked
   execution-checkpoint artifact from section 5 and require its evaluated,
   resolved result; do not mistake the canonical `not_evaluated` for validation.
6. Archive the original inbox file through `check-inbox` only after every
   assertion passes.

Use `done` only for successful completion and delivery, `error` for terminal
execution failure, `cancelled` when the human or sender stops an admitted
task, including a sender replacement. Use `superseded` only for a never-admitted paused
`review_request` with `--superseded-by-message`, or same-message re-evaluation lineage
with `--superseded-by <evaluation_id>`; a newer message alone cannot inherit
an admitted task's authority.
`paused` and `blocked` are live states: retain the original inbox message
while re-authorization or an external dependency remains unresolved.
A progress reply does not authorize archival.

Outcome recording does not perform these terminal updates. Use `FINALIZE_CMD`
resolved alongside the evaluator in section 1 for checkpoint, terminal, and
`--validate` operations. It owns the shared audit lock and atomic replacement;
do not switch to the installed console during a resumed task or terminalization.
Never update the YAML with textual substitution. If finalization or read-back
validation fails, retain the inbox message for repair.

Before sending Done, prepare one complete actuals mapping, then use that same
file for the dry-run and terminal write. It must contain the true work start,
measured distinct deliverable-file count, and **every performed effect** in
`side_effects_actual`. For example, this format uses synthetic values and
assumes these effects were admitted:

```yaml
work_started_at_utc: "2026-01-01T12:00:00Z"
actual_files_touched: 2
side_effects_actual:
  writes_findings_packet: true
  sends_oacp_reply: true
```

Use the real values for the invocation. Include any applicable checkpoint and
reauthorization data without changing their timestamps or scopes. The file is
the actuals mapping itself, never an outer `actuals:` wrapper. Let the writer
derive elapsed minutes from its work start and pause history.

```bash
"${FINALIZE_CMD[@]}" "$AUDIT_PATH" --final-state done \
  --actuals "$ACTUALS_FILE" --dry-run --json
# After the dry-run passes and terminal reply delivery is verified:
"${FINALIZE_CMD[@]}" "$AUDIT_PATH" --final-state done \
  --actuals "$ACTUALS_FILE" --reply-message-id "$REPLY_MESSAGE_ID" --json
"${FINALIZE_CMD[@]}" "$AUDIT_PATH" --validate --json
```

Do not mix `--actuals` with scalar actuals flags: with `--actuals`, the
finalizer ignores `--actual-minutes`, `--actual-files-touched`, and `--realized`
in favor of the file. A scalar-only invocation without `--actuals` is an
alternative, not an addition. Resolve a dry-run exit `4` through the checkpoint
path before terminal signaling. Pass one `--artifact <ref>` per durable output,
including the separate execution-checkpoint artifact for a null-envelope
admission. Realize replies when covered by the profile or receiver-human
scope; never omit an uncovered performed effect merely to avoid a checkpoint.

### Close a sender-replaced admitted task

1. Verify the sender's cancellation/replacement and stop the old work. Admit
   replacement work separately; the cancellation grants it no authority.
2. While the old audit is live, retain already-realized effects using the
   canonical checkpoint for an envelope-bearing audit, or the separate bound
   execution-checkpoint artifact for a null-envelope admission. Resolve any
   breached execution scope before closure. Do not fabricate an envelope.
3. Cancel using clock/count actuals only. Use a separate cancellation actuals
   file carrying `work_started_at_utc` and `actual_files_touched` when work began;
   it must contain no `side_effects_actual` or reauthorization keys. Include
   actual sender notice time and each existing landed deliverable:

   ```bash
   "${FINALIZE_CMD[@]}" "$AUDIT_PATH" --final-state cancelled \
     --cancelled-by sender --cancelled-at "$CANCELLED_UTC" \
     --reason "replaced by $REPLACEMENT_MESSAGE_ID" \
     --actuals "$CANCELLATION_ACTUALS_FILE" \
     --deliverable-landed "$LANDED_REFERENCE" --json
   "${FINALIZE_CMD[@]}" "$AUDIT_PATH" --validate --json
   ```

   Omit `--deliverable-landed` when nothing landed; repeat it for multiple
   existing outputs. For a never-started admitted task, omit `--actuals` and
   all start/count/deliverable flags so the finalizer records zero actuals.
   Never pass `--realized` to cancellation. For null-envelope work, retain the
   separate effect evidence and link its path among landed-deliverable evidence.
4. Read back `final_state: cancelled`, cancellation time, measured actuals and
   landed evidence before archival. Held, unverified, or still-live messages
   remain queued. A never-admitted paused `review_request` follows the supersession path above.

The shipped enforcement adapter remains Claude PreToolUse-only. Codex has no action-layer adapter and must not claim hook enforcement.
An admission `scope_envelope` still bounds checkpoints; it is distinct from a
compiled runtime envelope. Preserve the canonical `none` enforcement state
and surface the limitation. Do not compile, extend, or clear a runtime
envelope for Codex; `oacp envelope show` is inspection-only.
