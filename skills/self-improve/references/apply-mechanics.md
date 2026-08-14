# Apply-time edit mechanics — /self-improve

Edit-anchoring failure modes for the apply step (Step 7). These are
runtime-agnostic anchoring rules; read before any insertion or scripted
assert-replace batch.

- **Don't anchor an insertion on a neighboring entry's header fragment** — it fuses/swallows entries. Anchor on the preceding entry's tail and re-include it (or re-include the full header in the replacement text). Tripwire: `git diff --stat` right after skill edits — unexpected deletions on a pure insertion = swallowed text.
- **For scripted multi-file assert-replace batches**, verify each full anchor string beforehand — a paraphrased lead-in fails the assert mid-batch, splitting it into applied/unapplied halves. Or structure the batch to collect all failures before writing anything.
