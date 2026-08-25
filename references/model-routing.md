# Model Routing for ChatGPT

This file defines the model-routing policy for Wenshu. ChatGPT Skills do not expose a public standard field that can force per-step model switching, so this is an execution policy: use the named model when the runtime supports routing; otherwise preserve the same capability tier and never claim that a switch occurred.

## Roles

| Model | Role | Main responsibilities |
|---|---|---|
| Luna Max | Default executor | Intent routing, file reading, routine extraction, metadata cleanup, ordinary and moderately complex grounded Q&A, first-pass theory genealogy and argument-chain analysis, script orchestration |
| Sol Medium | Escalation + final reviewer | Resolve only high-ambiguity problems that Luna/scripts cannot settle, and perform the final independent review/acceptance pass |

## Routing rules

1. Luna Max is the default for routine work and the first pass of complex semantic work. Triggering Wenshu alone is never a reason to upgrade.
2. During generation, Sol Medium is an exception path, not a workflow default. Upgrade only the unresolved high-complexity step, then return to Luna Max.
3. Before generation-time escalation to Sol Medium, Luna Max must first attempt the step unless the user explicitly requests Sol Medium or a prior validated stage already established an unresolved conflict.
4. Final acceptance is always a separate Sol Medium review pass. Sol reviews evidence, fact/inference boundaries, workflow compliance, citations, anchors, formats, and unknown markers.
5. If Sol participated in generation earlier, final acceptance must still be a fresh review pass and must not reuse the generation verdict as acceptance evidence.
6. Deterministic Python scripts keep responsibility for mechanical operations; stronger models do not recompute what scripts already determine.

## Workflow allocation

- Intent recognition, evidence-source selection: Luna Max.
- Single-document reading, extraction, summaries: Luna Max.
- Whole-book extraction/splitting: Luna Max + Python scripts; use Sol Medium only when script outputs leave unresolved semantic conflicts.
- Metadata verification: Luna Max; use Sol Medium only when authoritative sources remain materially inconsistent after normal verification.
- GB/T 7714, BibTeX, anchors, YAML/dead-link/snapshot checks: Luna Max + deterministic scripts; Sol Medium is normally unnecessary during generation.
- Ordinary and multi-document grounded Q&A: Luna Max first; Sol Medium only if competing evidence cannot be reconciled reliably.
- Theory genealogy (source/development/debate): Luna Max first. Escalate only when the genealogy spans multiple documents and multiple hops, contains material source conflicts, or relation classification remains unstable.
- Argument chains (claim/data/conclusion/support/rebuttal): Luna Max first. Escalate only when implicit cross-document support/rebuttal relations remain ambiguous after the first pass.
- Final review and acceptance: Sol Medium, in a separate review pass.

## Sol Medium generation-time triggers

Upgrade the current generation step only when at least one high-complexity condition remains unresolved after Luna Max or deterministic processing:

- Two or more authoritative sources materially conflict on a key fact or metadata field and normal verification cannot resolve the conflict.
- A required conclusion depends on a multi-document, multi-hop relation where intermediate links must be semantically adjudicated.
- Support/rebuttal/development/source relations remain genuinely ambiguous after Luna Max has produced and checked a first-pass mapping.
- A deterministic script reports conflicts or low-confidence output that cannot be resolved by straightforward rule-based checks.
- OCR/TOC/page structure has multiple plausible interpretations and choosing the wrong one would materially alter downstream results.
- Competing evidence sets support incompatible conclusions and the task requires adjudicating which evidence chain is stronger.

Do not escalate during generation merely because a file is long, an output is long, many files exist, formatting is complex, the task mentions theory or argumentation, or a script runs for a long time.

## Sol Medium final review contract

The final Sol review returns `PASS` or `NEEDS_FIX` plus an issue list.

Review:
1. evidence completeness;
2. fact vs inference boundaries and hallucination risk;
3. workflow and write-discipline compliance;
4. consistency of citations, anchors, formats, metadata, and unknown markers.

If the result is `NEEDS_FIX`, send the issue list back to the model that generated the affected content (normally Luna Max; Sol only for a genuinely high-complexity fix), then run a fresh Sol review again. The reviewer does not create a third candidate and does not automatically choose among user-owned alternatives.

## 180-minute rule

If a single step exceeds 180 minutes, never switch models silently. Preserve inputs, sources, script state, intermediate artifacts, completed checks, and remaining work; explain the proposed takeover and scope; obtain explicit user approval before switching.

- A Luna Max generation step may propose Sol Medium only for the unresolved complex remainder.
- A Sol Medium generation step may propose returning unresolved routine work to Luna Max after user approval.
- A Sol Medium final-review step remains the required reviewer by default. If it exceeds 180 minutes, ask the user before using any fallback reviewer; a fallback review is not equivalent to Sol acceptance unless the user explicitly accepts that exception.
- A takeover must not expand task scope, write permissions, or data-source scope.

## Execution display

Show a concise `step -> model -> reason` table before execution when a task has 3+ stages, uses 2+ models, includes batch persistent writes, or the user explicitly asks to see routing. Single-step routine tasks may execute without a routing table.
