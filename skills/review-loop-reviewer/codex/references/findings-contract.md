# Reviewer findings and verdict contract

Use this reference only while producing a terminal verdict. Keep detailed
findings in the packet and GitHub comments status-only.

## Prepare the exact head

Use a temporary review directory outside every checkout. Set `REPO_ROOT` to
the local checkout containing the fetched exact head; `--repo-root` allows
running the helper from the scratch directory:

```bash
python3 "$REVIEW_LOOP_REVIEWER_SKILL/scripts/prepare_review.py" \
  --repo owner/base --pr 123 --repo-root "$REPO_ROOT" \
  --output-dir "$REVIEW_DIR"
```

The JSON result names `base_repo`, `head_repo`, `reviewed_head`, `patch_file`,
and `tree_dir`. Run source-only checks from `tree_dir`. The helper materializes
a tree without a `.git` directory, so keep the review directory outside
every checkout; otherwise Git-aware tooling can walk upward and use unrelated
ancestor metadata.

If a required check reads Git metadata, use a separate clean detached worktree
at the exact full `reviewed_head`, verify `git rev-parse HEAD` equals that SHA
immediately before and after the checks, and record those probes with the other
validation evidence. If the exact metadata-preserving checkout is unavailable,
the check is not passed; never substitute another commit or treat the archive
tree as Git-backed.

The exact commit must be present locally. Fetch the full base/fork head using
the consuming repository's authorized Git identity before retrying an unavailable
commit; retry with the same output directory after that failure. Without
`--repo-root`, the current directory must be inside that checkout.
The helper never substitutes a GitHub archive, which may omit or rewrite
committed files through export attributes. Gitlinks (mode `160000`) are rejected
explicitly; use a separately verified recursive checkout at the recorded commits
when submodule content is needed, without calling this helper's output complete.

For context-only inspection, `--dry-run` emits normalized PR metadata and
creates no directory.
The helper's live full `reviewed_head` is authoritative. Compare any sender
`declared_head` or `requested_head` to that value after preparation; never pass
sender-declared context to `--expected-head`.

## Verdict input

Write JSON with this shape:

```json
{
  "packet_id": "20260807_example_codex_r1",
  "source_review_packet": "",
  "reviewer": "codex",
  "round": 1,
  "created_at_utc": "2026-08-07T20:00:00Z",
  "reviewed_head": "0123456789abcdef0123456789abcdef01234567",
  "summary": "One concise evidence-based summary.",
  "findings": [],
  "qa_validation": {
    "commands_run": [
      {"command": "make preflight", "result": "pass", "notes": ""}
    ]
  },
  "nits": [],
  "withheld_side_effects": [],
  "escalation": null,
  "telemetry": {}
}
```

Each finding follows the active `templates/findings_packet.template.yaml` and
must include `id`, `severity`, `blocking`, `status`, `area`, `file`, `line`,
`repro`, `expected`, `evidence`, and `recommendation`.

## Systemic finding closure

Treat a blocking finding as systemic when it concerns an identity, authority,
durable-evidence, concurrency, or multi-record transaction invariant. Before
closing it, map the applicable rows below and capture each result in the
finding's expected/evidence text or as explicit subcase findings. No extra
packet field is required.

| Row | Questions to close |
|---|---|
| Strict input | Do valid, malformed, duplicate-key, missing, and ambiguous inputs fail or proceed without normalizing evidence? |
| Identity and links | Are receiver, message/thread, predecessor, successor, uniqueness, and back-references all bound? |
| Transaction state | Are every read/write participant and the commit/rollback boundary explicit? |
| Failure classes | Do validation errors, filesystem errors, partial writes, and retry/adoption preserve the pre-call invariant? |
| Concurrency and locks | Are all conforming writers serialized under stable locks acquired in deterministic order and held for the full mutation/restore span? |
| Read-back | Does success prove the committed state and failure prove byte-preserving restoration or an explicit retained error? |

On re-review, replay the original repro and every previously recorded blocking
row, then probe adjacent rows made reachable by the new design. A targeted fix
passing its old repro does not close the parent while another applicable row is
unverified. Keep the parent ID stable; use suffixes such as `F-006a` and
`F-006b` for distinct subcases instead of silently changing what “fixed” means.
If the same parent gains a new blocking subcase after two addressed rounds,
retain the blocker and request a bounded architecture checkpoint before
another narrow patch round; use existing protocol question/escalation paths,
not a new message type or escalation code.

## Severity and gate rules

| Severity | `blocking` | Outcome |
|---|---|---|
| P0 | `true` | Feedback until resolved |
| P1 | `true` | Feedback until resolved |
| P2 | Reviewer judgment | Feedback when material; otherwise LGTM nit |
| P3 | `false` | LGTM nit |

Statuses `fixed` and `wont_fix` are resolved for packet counting. Any unresolved
non-blocking P2/P3 finding must have a nit whose `source` names that finding ID.

Every nit requires:

- `nit_id`, unique within the PR
- `tier`, `P2` or `P3`
- one-line `summary`
- `owner` (default to the PR author)
- concrete `next_action`
- optional `tracking_ref`, `source`, and `expires_at_utc`

A gate passes only when there are no unresolved P0/blocking findings, at least
one validation command is recorded, every recorded command passes, all
deferred findings map to nits, and no escalation is present.

## Approval delivery matrix

| Accepted approval scope | Outcome at the reviewed head | Terminal behavior |
|---|---|---|
| Absent or false | Quality gate passes; approval still required by repository policy | Send LGTM with `submits_github_review` in `withheld_side_effects`; separately authorized eligible approval remains a landing gate. |
| True | Eligible exact-head approval is submitted or read back | Send the paired LGTM after proof and a fresh head guard. |
| True | Self-review, submission failure, or missing approval proof | Retain the request and report the composite delivery failure; send no LGTM. |
| Unestablished authority or head drift | Any quality result | Hold delivery; recover scope or require a fresh review as applicable. |

`withheld_side_effects` is a list of known effect names, emitted on both terminal
body types (`[]` when none were withheld). It records requested effects excluded
by accepted scope; it does not turn an unsuccessful accepted approval into a
successful round. Optional GitHub comments are separately authorized, and no
comment substitutes for a required approval. `merge_ready: true` remains a quality
verdict; it does not establish a repository's independent landing approvals.

## Render packet and message body

```bash
python3 "$REVIEW_LOOP_REVIEWER_SKILL/scripts/validate_verdict.py" verdict.json \
  --findings-ref "packets/findings/20260807_example_codex_r1.yaml" \
  --packet "$OACP_HOME/projects/$PROJECT/packets/findings/20260807_example_codex_r1.yaml" \
  --body "$REVIEW_DIR/terminal-body.yaml"
```

The helper refuses inconsistent severity/IDs, infers `review_lgtm` versus
`review_feedback`, and creates new files without overwriting existing evidence.
Its JSON stdout reports verdict, counts, gate evidence, and output paths. A
passing body is only a candidate until any in-scope GitHub approval is submitted
and verified at the same exact head.

The skill's validator includes the findings gate: only `fixed` and `wont_fix`
resolve findings; every other status remains unresolved. No unresolved P0 or
blocking finding may pass.

Send the type reported by the validator:

```bash
oacp send "$PROJECT" --from codex --to "$AUTHOR" \
  --type "$MESSAGE_TYPE" --subject "$SUBJECT" \
  --body-file "$BODY_PATH" --related-pr "$PR_NUMBER" \
  --conversation-id "$CONVERSATION_ID" \
  --in-reply-to "$REQUEST_ID" --priority P1 --oacp-dir "$OACP_HOME"
```

Follow local signing policy; never downgrade enforce mode or infer authority
from unsigned/warn annotations.

## Terminal ordering

1. Re-read base-repo `headRefOid`; require `reviewed_head` equality.
2. For a pass with formal approval in scope, reuse an existing exact-head
   approval by the active reviewer or submit GitHub APPROVE on the base repo;
   read it back and require the same identity, state `APPROVED`, and `commit_id`
   exactly equal to `reviewed_head`.
3. Re-read the head after every GitHub side effect.
4. Send the inbox response after any approval accepted in scope is proved;
   otherwise send the quality verdict with its withheld-effect list.
5. Read back required task/audit state.
6. Re-read the live inbox path through the verified snapshot boundary.
7. Move the exact accepted file into sibling `inbox/archive/` through
   `check-inbox` only after its SHA-256 still matches and no-clobber guards pass.
8. Exit the reviewer invocation.

Any delivery failure retains the request and is reported explicitly. An accepted
GitHub approval failure withholds LGTM; a comment is not a substitute. Do not send a
second terminal verdict from the same invocation. Never delete, recreate,
copy-unlink, or overwrite accepted inbox evidence.
