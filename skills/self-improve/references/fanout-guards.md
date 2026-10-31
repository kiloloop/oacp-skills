# Fan-out subagent guards — /self-improve

Guards for the parallel-analysis fan-out (full reviews without a same-day
pass). Read before spawning subagents.

## Briefing

- **One shared brief block**: compose the session context + suppression list ONCE and paste it verbatim into every subagent prompt — per-agent prompt drift converts known-fixed issues back into phantom findings the main session then has to re-refute. No "send your findings back" suffix is needed: the subagent's final message is its report.
- **Memory-agent briefs must state the link convention**: if memory files cross-reference with `[[name]]` wiki-links, links resolve by the target file's frontmatter `name:` slug (verify with `grep '^name:'`), not the filename stem. Verify broken-link findings against BOTH resolutions before presenting — mixed conventions exist in older memory directories.
- **Disjoint file sets still share contracts**: when parallel agents each own a file set, the brief names who reads and writes every section another skill or agent touches (a table one file holds and a scheduled skill appends to; a heading other files cite by name). Otherwise one agent retires a section a second still writes to, and nothing flags it until verification.
- **A deliverable must survive the hand-back**: any output a later step or session acts on — rewrite texts, a plan, a findings list — is briefed as the agent's full final message, since Claude Code can refuse report-file writes from subagents. When the brief also names a file path, spell it per agent, literally — a `<your-name>` template in a shared brief is substituted inconsistently. When a hand-back arrives truncated, recover it from the agent's transcript (the last assistant `text` block in `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/projects/<slug>/<session>/subagents/`) and write the file yourself; asking for a resend truncates again. A *named* agent's hand-back can arrive through a teammate idle notification cut at about 3,500 characters, so brief named agents for at most 3,000 characters or plan the transcript recovery from the start.

## Collecting

- **Empty-result agents**: an agent that finishes with an empty or content-free report has not reported "no issues". Check any file its brief named, then message it once for the final list (or "No issues found"); don't poll.
- **Discard session-state findings**: if a subagent reports the current session's model, effort, or permissions, discard it — subagents run their own configuration and cannot observe the parent session.

## Verifying before presenting

- **Spot-verify file-content claims**: grep the cited file for the quoted defect — subagents misattribute text across files and may have read pre-edit state (findings on files this session edited deserve extra suspicion). Use fixed-string matching (`grep -F`); quotes with backticks, em-dashes, or regex metacharacters false-negative under pattern matching, and line-wrapped sources miss on the joined form — a grep miss on a punctuated or wrapped quote means Read the file before declaring the finding phantom. If a just-written file's on-disk content genuinely differs from what the session wrote, don't stop at "agent misread" — check for a mutating tool in the write path (e.g., a YAML round-trip normalizer) and root-cause the pattern.
- **Verify rule *interpretation*, not just content quotes**: a [CONFLICT] finding can quote real text yet over-stretch the rule's meaning — check the rule's provenance/trigger context before presenting, and present over-readings as "verified phantom" with reasoning rather than silently dropping them.
- **Verify the facts inside an agent's replacement text, not only its verdict**: a correct STALE/CONFLICT verdict can arrive with replacement text that restates a different stale claim, since the agent drafts it from the same files it is auditing. Before adopting a proposed rewrite verbatim, check each factual sentence against current evidence, this session's own observations first.
- **Convert timezones before accepting timestamp-inconsistency findings**: file-metadata timestamps are typically UTC while narrative dates in memory bodies follow the author's local timezone — a post-midnight local session stamps the next UTC day, so "modified predates its own content" claims must be re-derived in one timezone before presenting.
