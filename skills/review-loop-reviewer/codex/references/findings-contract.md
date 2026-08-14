# Reviewer findings and verdict contract

Use this reference only while producing a terminal verdict. Keep detailed
findings in the packet and GitHub comments status-only.

## Prepare the exact head

Use a temporary review directory outside the checkout:

```bash
python3 "$REVIEW_LOOP_REVIEWER_SKILL/scripts/prepare_review.py" \
  --repo owner/base --pr 123 \
  --output-dir "$REVIEW_DIR"
```

Do not pass sender-declared `declared_head` or `requested_head` as
`--expected-head`. The helper resolves the live full head. Reserve that option
for an independently resolved trusted head in focused drift tests.

The JSON result names `base_repo`, `head_repo`, `reviewed_head`, `patch_file`,
and `tree_dir`. Run checks from `tree_dir`. For context-only inspection,
`--dry-run` emits normalized PR metadata and creates no directory.

## Verdict input

Write JSON with this shape:

```json
{
  "packet_id": "20260101_example_codex_r1",
  "source_review_packet": "",
  "reviewer": "codex",
  "round": 1,
  "created_at_utc": "2026-01-01T00:00:00Z",
  "reviewed_head": "0123456789abcdef0123456789abcdef01234567",
  "summary": "One concise evidence-based summary.",
  "findings": [],
  "qa_validation": {
    "commands_run": [
      {"command": "make preflight", "result": "pass", "notes": ""}
    ]
  },
  "nits": [],
  "escalation": null,
  "telemetry": {}
}
```

Each finding follows the active `templates/findings_packet.template.yaml` and
must include `id`, `severity`, `blocking`, `status`, `area`, `file`, `line`,
`repro`, `expected`, `evidence`, and `recommendation`.

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

## Render packet and message body

```bash
python3 "$REVIEW_LOOP_REVIEWER_SKILL/scripts/validate_verdict.py" verdict.json \
  --findings-ref "packets/findings/20260101_example_codex_r1.yaml" \
  --packet "$OACP_HOME/projects/$PROJECT/packets/findings/20260101_example_codex_r1.yaml" \
  --body "$REVIEW_DIR/terminal-body.yaml"
```

The helper refuses inconsistent severity/IDs, infers `review_lgtm` versus
`review_feedback`, and creates new files without overwriting existing evidence.
Its JSON stdout reports verdict, counts, gate evidence, and output paths.

For a pass, run the active runtime's packet gate too:

```bash
python3 "$RUNTIME_SCRIPTS/check_quality_gate.py" "$PACKET_PATH"
```

Then send the type reported by the validator:

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
2. Perform only the authorized GitHub approval/comment effects on the base
   repo; verify a formal approval's state and commit when required.
3. For pass, re-read the head after every GitHub side effect.
4. Send the inbox response with the accepted conversation ID.
5. Read back required task/audit state.
6. Re-read the live inbox path through the verified snapshot boundary.
7. Archive only when its SHA-256 still matches the accepted snapshot.
8. Exit the reviewer invocation.

Any failure retains the request and is reported explicitly. Do not send a
second terminal verdict from the same invocation.
