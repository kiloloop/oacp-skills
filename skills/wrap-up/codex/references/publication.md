# Wrap-up events and publication

Load only the section required by the current wrap-up step.

## Org-memory events

Load this reference only after a successful debrief suggests a significant
cross-project outcome.

Write an event for a merged PR, release or deployment, architecture decision,
or new standing rule another project or runtime needs. Write zero for routine
fixes, tests, documentation cleanup, inbox processing, self-improve findings,
or read-only work.

Skip when `$OACP_ROOT/org-memory/events/` is absent. Deduplicate against both
tracked and untracked event files before writing. An equivalent local event
already counts.

Use lowercase alphanumeric-and-hyphen slugs of 1–64 characters, beginning and
ending with an alphanumeric character. Convert dots to hyphens.

```bash
oacp write-event --agent codex --project "$PROJECT" \
  --type <decision|event|rule> --slug <short-slug> \
  --body "<one-line description>" --oacp-dir "$OACP_ROOT"
```

Use `--source-ref`, `--related`, or `--body-file` when they materially
improve traceability. Keep a session batch to 3–5 events and report written,
deduplicated, skipped, or routine status.

## Publication

Load this reference only when a full wrap-up has memory or repository changes
to publish. The nearest `AGENTS.md` owns identity, authentication, branch, and
remote policy.

### OACP memory

Resolve `OACP_ROOT` from `OACP_HOME` or the active environment. If its
`.oacp-memory-repo` marker is absent, report sync disabled. Run exactly one
publication command after debrief, event writing, and approved self-improve
edits:

```bash
oacp memory push --oacp-dir "$OACP_ROOT"
```

Skip for dry-run, `no-push`, `local-only`, narrower scope, or unavailable
required authentication. Record memory HEAD before and after. Never replace
the CLI with manual Git, force push, or ad hoc repair.

### Repository commits

Treat every repository independently:

1. Confirm root, branch, status, and unrelated pre-existing changes.
2. Stage only paths created by wrap-up or explicitly approved by self-improve.
3. Exclude credentials, private keys, `.env`, unapproved local settings,
   generated caches, and live runtime state.
4. Run proportional project-native validation.
5. Use the repository's required commit convention.

A live lock or local permissions file is runtime state, not commit material.
Keep changes from different repositories in different commits.

### Repository pushes

Inspect remotes before network operations and keep them token-free. Use only
the identity allowed by repository guidance. When the branch exists on origin:

```bash
git pull --rebase --autostash origin "$CURRENT_BRANCH"
```

On a rebase conflict, abort and skip that repository's push. If autostash
restoration conflicts, Git preserves the stash; stop and report it. Never force
push, silently change identity, or publish a branch the user kept local.

Report repo, branch, commit SHA, validation, and credential-redacted remote.
One repository's conflict or authentication failure does not authorize changes
in another.
