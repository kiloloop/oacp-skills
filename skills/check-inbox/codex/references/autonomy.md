# Receiver autonomy — Codex adapter

Use this adapter for task-like inbox messages and for canonical review-loop
continuation recognition. The active OACP protocol and executable evaluator
are authoritative; this file defines how Codex invokes and preserves them.

## Run the canonical evaluator

Resolve `autonomy_gate.py` from the active installed OACP package's `_scripts`
directory, or from the current OACP source checkout's `scripts/` directory.
Use the interpreter named by the active `oacp` entry point when it differs from
the ambient `python3`, so an isolated tool installation stays self-contained.
Pass
the original top-level inbox path, receiver config, receiver name, OACP root,
and the exact
`audit/autonomy_decisions/` directory. Set `OACP_RUNTIME_MODEL` only from
actual serving-model metadata; leave it unset when that signal is unavailable.

The evaluator reads one bounded message snapshot, verifies that snapshot at
intake, validates the current message schema, evaluates the four gates, and
lock-serializes a schema-version-2 audit. Require the audit's
`message_sha256` to equal the digest from `read_verified_message.py`. A
mismatch means the live source changed between snapshots: retain it and do not
act. Exit `3` is an enforce-mode intake rejection and produces no autonomy
audit. Other nonzero exits are operational failures.

If receiver config is missing, preserve the evaluator's conservative
`always_pause` behavior. Never create a policy file merely to admit a task,
and never hand-simulate reason codes when the canonical evaluator is
available.

## Interpret and preserve the result

The evaluator owns policy authorization, validation, replay detection,
profile normalization, hard-stop classification, continuation matching,
reason precedence, scope envelopes, checkpoints, and provenance. Preserve its
`spec_version`, `policy_auth`, runtime identity, `evaluator`, decision,
reasons, normalized profile, continuation result, and complete `result`
mapping.

The pinned `result.completion_kind` values are:

- `auto_accepted`
- `admission_paused`
- `checkpoint_paused`
- `config_malformed`

Do not replace the evaluator's admission state with a receiver-composed
`pending`. Auto-accepted evaluations currently emit `final_state: done` and
paused evaluations emit `final_state: paused`. Terminal bookkeeping fills
actuals, checkpoint, completion time, reply id, and artifacts. A
human-approved admission pause may move `final_state` to `done` after genuine
completion while retaining `completion_kind: admission_paused`.

Attach `message_auth` only with `oacp verify --attach-audit` against the
private accepted snapshot, never by hand and never from a later live-path
read. Skip attachment in off mode. Compare its status and payload digest with
the reader result before proceeding.

## Human outcomes and checkpoints

Record an explicit human outcome for every paused task-like message before
acting. Current-task approval and a standing continuation grant are separate
decisions. Do not rewrite the immutable admission envelope. If a modified
approval adds a task-local capability, put the exact authorized addition in
`actuals.reauthorization.receiver_human`, evaluate a prospective checkpoint,
and proceed only on `resumed_after_reauthorization`.

Before a newly discovered capability and before terminal signaling, evaluate
actual minutes, distinct files, and every realized outward effect against the
accepted envelope or granted review-loop scope. On expansion, stop first,
write the evaluator-defined paused checkpoint, send an in-thread blocked
notification, and retain the original task for reauthorization.

A review lifecycle message does not run the four task gates. Dispatch a
review request without fresh confirmation only when the executed continuation
result is exactly `review_continuation_accepted`. Carry its accepted
`permitted_side_effects` into the reviewer. The grant authorizes invocation,
not the verdict, GitHub effects, or merge. A declared-head mismatch is
advisory at dispatch; the reviewer binds its work to the live full head.

## Finalize

For a terminal task-like outcome:

1. Evaluate the final threshold checkpoint from measured actuals.
2. Deliver the terminal reply and verify its sender and recipient artifacts.
3. Under the shared audit lock, atomically update the same record while
   preserving admission fields, completion kind, provenance, human outcome,
   and message authentication.
4. Record final state, completion time, actuals, checkpoint, reply id, and
   durable artifacts, then parse the record back and assert them.
5. Archive the original inbox file only after every assertion succeeds.

Use `done` only after successful completion and delivery, `paused` for an open
reauthorization wait, `blocked` for a terminal external blocker,
`superseded` for authoritative replacement, and `error` for terminal
execution failure. A progress reply is not terminal.

The shipped enforcement adapter is not available for Codex. Codex may inspect
state with `oacp envelope show`, but it does not compile, extend, clear, or
claim enforcement. Preserve `result.envelope_enforcement: none`.
