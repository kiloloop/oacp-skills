# Apply-time edit mechanics — /self-improve

Failure modes for the apply step (Step 8). Read before any insertion, scripted
assert-replace batch, or edit to an executable.

## Anchoring

- **Don't anchor an insertion on a neighboring entry's header fragment** — it fuses/swallows entries. Anchor on the preceding entry's tail and re-include it (or re-include the full header in the replacement text). Tripwire: `git diff --stat` right after skill edits — unexpected deletions on a pure insertion = swallowed text.
- **For scripted multi-file assert-replace batches**, verify each full anchor string beforehand — a paraphrased lead-in fails the assert mid-batch, splitting it into applied/unapplied halves. Or structure the batch to collect all failures before writing anything.
- **A multi-word search against a hard-wrapped file returns empty for the wrong reason** — prose wrapped at ~80 columns splits a phrase across a newline, so neither `grep` nor a `.find()` on the raw text matches it. The empty result reads as "that text isn't there", which kills a valid finding or produces a duplicate rule beside the one you missed. Search a short fragment that cannot span a wrap, or normalize whitespace first; never conclude absence from one multi-word probe.
- **A rule about an escape sequence cannot quote the sequence** — the Edit/Write call that lands the rule can decode backslash-u escapes, so the file gets the raw code point (e.g. a NUL) instead of the six characters, corrupting the very file the rule protects. Spell it in words ("backslash-u-four-hex-digits") or write a placeholder and swap it with a Python bytes `.replace()`; verify with `grep -c` or `od -c`.

## Sandbox-denied paths

Claude Code's sandbox can deny **Bash** writes to its own configuration paths — project and user `.claude/skills/`, `.claude/hooks/`, settings files, the auto-memory dirs under `projects/` — even inside an otherwise allowlisted tree, resolving symlinks to their targets. A scripted write there fails `Operation not permitted` at open, with nothing written; the Edit and Write tools are not affected. Apply edits there with per-file Read+Edit rather than a scripted batch. Don't bundle edits with other commands (a fixture run, a cleanup) in one sandbox-exempt call: the permission gate can deny the bundle whole, and a declined command is not retried as a near-variant.

## Executable edits

An edit to a script, hook, or guard is not applied until you **run** it, on both the path you fixed and the path that already worked. A self-improve edit ships to every future session unreviewed, while the original at least worked:

- Prefer a fix that adds no new syscall or dependency the environment may deny (capture `2>&1` into a variable rather than adding a temp file), then re-run the success path to prove you did not trade one break for another.
- For a lint, hook, or guard that matches commands or text, your fixtures test only the cases you thought of. Also replay old vs new over the session transcripts (`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/projects/**/*.jsonl`, pairing each Bash `tool_use` with its `tool_result`) and count the new hits before committing — a pattern that passes every fixture can still match hundreds of unrelated commands.

## Staging beside a peer's uncommitted hunk

When an approved edit lands in a file another session has dirty, stage only your own change: `git diff -U0 -- <file>`, keep the hunk that contains a string unique to your edit, write it to a scratchpad patch, and `git apply --cached --unidiff-zero <patch>`; the peer's hunk stays in the working tree. Select the hunk by that string, never by hunk count or position — the peer can commit between your check and your stage, and a count-based filter then fails on a file that now holds only your hunk. After the commit, `git status` must show the peer's files still dirty and yours gone.
