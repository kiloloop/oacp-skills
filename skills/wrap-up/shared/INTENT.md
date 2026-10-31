# wrap-up — Shared Intent

## Contract

Finish a session with bounded cleanup, durable reporting, a delta-first guidance
audit, and authorized publication. A clean tree is evidence to inspect, not a
reason to discard someone else's work or claim unfinished work is complete.

## Sequence

1. Preview branches, worktrees and inbox status without writes. Remove only
   verified, disposable session-owned artifacts. Preserve persistent, peer-owned,
   dirty or post-merge-diverged work and needed ignored files.
2. Invoke the installed debrief workflow; report a missing writer or publication
   failure explicitly and continue independent work. Do not improvise a fallback
   store or rewrite a landed record.
3. Capture significant shared outcomes with `agent-memory event write` when
   authorized; routine narrative stays in the debrief. Honor project opt-outs.
4. Run the required self-improve skill against the session delta. Reuse matching
   approval, request genuinely new scope, and avoid reopening settled findings.
5. Stage explicit approved files in each owning repository. Review the staged
   diff and keep unrelated or sensitive files out.
6. Publish authorized memory with `agent-memory push --home <resolved-home>
   --agent <registered-agent>` when configured. Inspect the whole pending memory
   diff before the tool commits its allowlist; do not claim it can select files.
7. Integrate upstream and push each authorized repository under its own policy.
   Stop on conflicts, unexplained changes or failed checks.
8. Report completed steps, skips, failures and unresolved work. Independent
   memory and repository publication failures do not erase one another.

## Boundaries

- Branch deletion requires ancestry proof or the exact local tip matching a
  merged PR head for a squash merge. A merged PR alone cannot authorize deleting
  later unpublished commits. Optional cleanup helpers remain advisory.
- Inbox reporting never consumes pending messages. Terminal processing and
  no-clobber archival belong to the inbox workflow.
- Codex dry-run performs read-only previews and proposals: no cleanup,
  debrief/event writes, edits, commits, memory publication or pushes. The current
  Claude slice retains its local-stage dry-run semantics: cleanup, debrief and
  self-improve may run (including approved local edits), while commits and
  pushes are skipped and event writing uses its dry-run option. Unifying these
  semantics requires a separately scoped Claude-slice change.
- The active runtime supplies its permission, delegation and scheduler mechanics;
  this contract does not prescribe a runtime-specific sandbox bypass.
- Self-improve is a hard dependency. Debrief and memory integrations must report
  capability gaps and their consequence; no silent fallback to retired commands.

## Inputs and outputs

Resolve the workspace and memory home explicitly. `OACP_HOME` defaults to the
configured OACP home; when memory tooling chooses another home, consistently use
that resolved home for event writing, inspection and publication.

Report cleanup evidence, debrief path/status, event count, self-improve outcomes,
repository commit/push results, memory publication result and remaining blockers.
