# Rule checks — /self-improve

Checks for any finding that adds, restates, or changes a rule — in a skill, an
instruction file, or org memory. Step 3 runs the first section while analyzing;
Step 7 runs all of them before the approval ask. A wrong or redundant rule is
executed silently by every later session, so these run before it is proposed.

The **rule sources** — the same set `/wrap-up` step 2b's existing-rule check
reads — are `$OACP_HOME/org-memory/rules.md` and `decisions.md` (headings via
`command grep -n '^### '`, then keywords), today's and yesterday's
`org-memory/events/` (UTC-dated filenames — a peer's same-day event is not
folded into `decisions.md` until synthesis), and the installed skills.

## Before proposing a home for a lesson

- **Count where the lesson already lives.** Hunting for a file to put a lesson in biases toward *adding* a copy — a finding can be genuine and still redundant. Grep the candidate lesson across the rule sources above, the project's runbooks, and the artifact's own header comments. Already recorded in two or more places → the finding is usually "extend the nearest copy" or "nothing to do", reported as such so the next pass does not rediscover it. Put a lesson where the work happens, not in a skill that merely mentions it.
- **Rule vs catalogue.** The anti-duplication test applies to restating a RULE, never to extending a CATALOGUE in its owning skill. Adding a newly observed instance to a list the skill already maintains — a denial shape, a trap, a failure mode — is maintenance, and "already covered in principle" is the wrong reason to skip it: skills stay authoritative only if new instances land in them.
- **A rule that failed with its text already in place is not fixed by more text.** When the grep finds the rule present and the miss happened anyway, propose an executed check — a script in `<skill>/scripts/` that produces the value, a lint the producing step runs, or a hook that gates the tool call — and shrink the prose to a pointer at it. Re-wording a rule the agent read past is the same rule with a later date.
- **A rule about tool or runtime behavior needs a controlled fixture, not a transcript reading.** Build the minimal file or command that isolates the claim and run it before the finding reaches the approval ask. Transcripts show what happened, not why; the reflex explanation is often the wrong mechanism, and these rules land in always-loaded instruction files where a wrong rule is executed silently. The same holds for a proposed config change and for any effect you attribute to an option in the ask — the user approves the effect you described, not the one the machine produces. Drive the tool's real entry point, not an internal helper that skips the live path's pre-processing. Run it where the claim lives — same repo, path class, and interpreter. A fixture that fails to reproduce clears nothing until the exact failing command is re-run: a scratchpad can allow a write (a `.git/config` update, say) that the project repo's sandbox denies.

## Before the approval ask

- **Check whether the rule already exists before proposing it as new.** Grep the target file's headings and the rule sources above — for a skill entry, the skill's own steps first. Read each hit in context:

  ```bash
  command grep -noE '.{0,60}<keyword>.{0,60}' <file>
  ```

  `command` bypasses a `grep` alias (such as ugrep) that rejects the pattern. Never read hits through `| cut -c1-N` — on a long line the match can sit past the cut, and a real hit reads as an unrelated line. Grep the words a rule would be written in, not only the symptom string: a rule about an escape or character trap spells the trap out in words, so a grep for the literal passes clean on it. Prefer refining the existing rule over adding a sibling — a restatement written from fresh session context tends to be narrower and to carry that session's misreadings, and two disagreeing copies leave neither authoritative.
- **Ask whether the target already prescribes the *opposite* of what you did.** A gap and a deviation look identical from inside — the skill and the session disagree, and the reflex is to read the skill as behind. Sometimes it is; sometimes you broke a rule with a stated rationale and are one approval away from ratifying the breach. Read the rationale: if it anticipated your case, the finding is a correction to record, not an edit to make. Widen a rule only when its rationale genuinely does not reach what you hit.
- **Collapse findings against each other.** Enumerating makes each facet feel independent — a verification failure, a coverage failure, and a guard failure are often one lesson at three altitudes. Group by root cause, merge any that would produce sibling rules in the same file (one sharper rule beats three that cross-reference each other, and the reader pays for all three on every load), and say in the report what was merged into what.
- **Scope a stale external fact tree-wide.** When the defect is a fact that changed outside your files — an App permission, an org setting, a vendor default, a file's export status — grep every skills tree, instruction file, and memory dir for restatements while writing the finding, and state the true site count in the ask. A fact-shaped claim spreads by copying, and Step 8's multi-site grep fires only after approval, so the user would approve a two-site fix and get a four-site one. For identity or config facts (bot emails, remote URLs), also check each clone's untracked local config (`git -C <clone> config --local --get <key>`), which no file grep reaches. A judgment-shaped finding is usually genuinely local — the test is whether the claim could have been copied, not how important it is.
