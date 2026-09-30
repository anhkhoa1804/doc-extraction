# Research strategy audit — 2026-09-15

## Purpose and authority

This is a repository-grounded strategic audit of the doc-extraction research
program through Experiment 042. It is a decision document, not a new
experiment or a rewrite of prior scientific history.

It records three kinds of statements:

- **Verified fact:** observed in current source, committed artifacts, raw
  experiment output, or current VM state.
- **Inference:** a conclusion drawn from those facts. It is not a causal
  claim unless the cited design supports causality.
- **Recommendation:** a proposed action, not a claim about the world.

The repository remains the source of truth if any later source or artifact
contradicts this document.

## Executive decision

### Current research state

The program has established real region-gating, ownership, and evidence
preservation failures. It has also developed unusually strong population
freezing, identity auditing, and counterfactual discipline. However, the
current crop-recovery acceptance rule is weaker than the program's stated
goal of preserving usable evidence. Raw Experiment 040 records show that
three of the four records classified as valid recovery have no populated
table cells after the fixed OCR-fill stage. The fourth has one populated
cell containing text already present in the corresponding baseline region.

### Actual bottleneck

The repository cannot yet reliably distinguish a new table structure from a
net improvement in correctly owned, serialized evidence.

### Biggest scientific risk

Further selector or corpus experiments could optimize a recovery label that
accepts empty structure or duplicated baseline text rather than useful new
evidence.

### Single best next move

Restore a minimal, evidence-centric paired evaluator from the existing
table-content and Layer-2 components, then apply it to the frozen
Experiment 040 development artifacts before authorizing another treatment or
role-specific control study.

### Primary direction

**RESTORE_EVALUATOR_FIRST**

Experiment 042 is useful but secondary. It should not determine the next
research decision until the evidence evaluator can say whether the existing
Experiment 040 outcomes improved usable evidence.

## Repository and checkpoint state

Verified during this audit:

| Item | Value |
| --- | --- |
| Repository | /home/magnusfrog_frogsleap/projects/doc-extraction |
| Origin | git@github.com:anhkhoa1804/doc-extraction.git |
| Branch | fix/table-text-ownership |
| Local HEAD | 0d518cd4ab464691ac8bfd7b6b8e8f2fb6f99ffe |
| Independently queried remote HEAD | 0d518cd4ab464691ac8bfd7b6b8e8f2fb6f99ffe |

The worktree was intentionally not cleaned. Existing non-audit changes and
artifacts were:

- a modified Experiment 039 CPU runner;
- generated Experiment 039 analysis;
- a generated Experiment 042 provenance index;
- transient libGL Debian packages used for the local CPU workaround.

No existing artifact was deleted or altered by this audit.

## Correct unit accounting for Experiment 039

Historical prose contains a denominator ambiguity. The authoritative
Experiment 039 manifest resolves it:

| Unit | Development | Held-out | Total |
| --- | ---: | ---:| ---: |
| Pages | 136 | 133 | 269 |
| GT table annotations | 152 | 117 | 269 |
| Strict-D2 annotation rows | 34 | 11 | 45 |

Thus 34/152 is a GT-table-annotation rate, not a development-page rate.
The coincidence that there are 269 pages and 269 GT table annotations must
not collapse these units.

## Original research thesis and its evolution

The repository README defines the project as extraction infrastructure for
structured enterprise documents. Its central goal is reliable, observable
preservation of evidence from difficult documents. It explicitly prioritizes
making failures visible and routing around them; it is not primarily a
model-training or retrieval product project.

The research question evolved as follows:

    reliable structured evidence from difficult documents
        -> independent OCR and selective recovery
        -> distinguish acquisition from assembly loss
        -> discover serialization, structure, ownership, and order blind spots
        -> characterize role and table-gating failures
        -> establish natural D2 failures and test a narrow intervention

The current question is narrower:

    Can a pre-treatment role signal safely identify a region for explicit
    table treatment?

That question remains legitimate, but it is subordinate to the original
question:

    Did the system preserve more correct, usable evidence?

## Research lineage

The following matrix is a compact reconstruction. It distinguishes each
experiment's measured result from claims it cannot support.

| Experiment | Question and corpus | Intervention / evaluator | Main result | What it proves | Main limitation |
| --- | --- | --- | --- | --- | --- |
| 023 | Does independent OCR improve evidence? Generated enterprise corpus, 49 documents / 112 pages | Six OCR paths through production; string and order metrics | Tesseract performed strongly; naive fusion did not dominate | Independent OCR choice can matter | Sparse expected strings and serializer-dependent measures |
| 024 | Can residual OCR loss be recovered? Seven failures and 42 controls | OCR and recovery interventions | Some raw OCR gains disappeared end to end | Recognition success is insufficient | Assembly and output ownership were not fully measured |
| 025 | Is layout coverage the residual bottleneck? SCAN-49 | Gap-region intervention and token coverage accounting | Coverage increased; final text was byte-identical on all 49 documents | Layout coverage repair had no downstream benefit here | Ownership and table-gating failures became more important |
| 026 | Should table-cell list order be changed? 94 tables | Offline canonical cell ordering | Row/column metadata was already correct | Prior order defect mainly affected evaluation flattening | Production change not justified |
| 027 | Does evaluator serialization distort results? 37 historical arms | Frozen serializer compared with canonical order | Exact recall did not change; order judgments did | One flat string conflated distinct properties | Layered evaluation required |
| 028 | Can independent output dimensions be measured? SCAN-49 | Layer-2 structural, order, and ownership views | Invalid structures and hidden order defects found | Layer 1 had material blind spots | Per-cell truth unavailable in this corpus |
| 029 | Do failures generalize and have identifiable mechanisms? Historical replay | Source / IR forensic attribution | 102 invalid table instances attributed to synthesis / containment interaction | Specific structural mechanism identified | Semantic ownership remains incomplete |
| 030 | Are stamp and containment explanations supported? Historical paired cases | Falsification and geometric analysis | H1 partly supported; H2 supported | Some causal subclaims narrowed | Stamp alone did not explain the population |
| 031 | Can picture-gated table evidence be recovered? Small historical candidate population | Offline reconstruction and controls | Narrow recovery possible; false-positive exposure exists | Exact table label gate matters | Small, family-specific population |
| 032 | Is role ambiguity a general architectural mechanism? Historical corpus and controls | Role-contract audit and probes | Route mapping inconsistencies and missing role provenance | Role semantics are under-specified | Broad role-routing solution not validated |
| 033 | Can geometry reject prose safely? Historical cases and adversarial controls | Shape-rule comparisons | Some rules improved; multi-column prose remains unresolved | Geometry alone is insufficient | Candidate rules partly shaped by known failures |
| 034a | Does external benchmarking validate the system? OmniDocBench, 1,651 pages | Official evaluator | External text/order signal; benchmark blind to ownership | Benchmark offers independent output checks | Missing replay inputs, evaluator race, ownership invisibility |
| 035 | Does natural D2 exist externally? 665 GT tables | Frozen GT-to-region/IR matching | 34/665 strict D2 | Region/ownership gating loss exists | Not proof that a page-wide specialist was absent |
| 036 | Can known D2 crops produce valid structures? 34 targets, 145 controls | Exact crop counterfactual | 17/34 recovery and 104/145 control FP under its definitions | Forced crops can sometimes produce valid grids | Not a safety or end-to-end evidence estimate |
| 037 | Does synthetic development activate a selector study? | Unchanged baseline | No natural activation | Synthetic corpus cannot support the study | Closed |
| 038 | Does independent real data provide natural diversity? 149 pages | Baseline and D2 matching | Development D2 concentrated in two groups | Natural activation exists | Inadequate development diversity |
| 039 | Does a larger independent corpus repair diversity? 269 pages | Baseline and forensic matching | 34 development D2 annotations, 28 unique regions | Adequacy gate passed | Does not validate a selector or outcome metric |
| 040 | Are exact baseline regions recoverable? 28 D2 regions, 766 controls | Fixed crop, merge, structural and overlap checks | Four protocol-valid recoveries; broad treatment unsafe | Outcome heterogeneity and control risk are real | Evidence gain is not adequately measured |
| 041 | Can same-role controls identify safety? Frozen 039 development layouts | Role identity census | 15 document_index candidates, all D2; zero controls | Same-role safety unidentifiable there | No treatment or provenance replay occurred |
| 042 | Can disjoint sources supply controls and invocation provenance? 279 pages / 40 groups | Acquisition, source scout, observational baseline | Acquisition passed; partial production role/provenance data | Better identity discipline and observed invocation modes | Full index incomplete; no natural document_index yet observed |

### Earliest visible version of the current bottleneck

Experiment 024 showed that a raw OCR improvement could vanish after
production assembly. Experiments 026 through 028 then showed that output
serialization and evaluators could report a different property than the
production representation. The current bottleneck was therefore visible
before the D2 program began.

## Experiment 034a and OmniDocBench forensic audit

### Historical result

The retained Experiment 034a official metrics report:

| Metric | Historical full result |
| --- | ---: |
| Text edit distance | 0.5837 |
| Formula edit distance | 0.9756 |
| Table TEDS | 0.3224 |
| Structure-only TEDS | 0.5247 |
| Table edit distance | 0.7018 |
| Reading-order edit distance | 0.5967 |

Edit distance is lower-is-better; TEDS is higher-is-better. The benchmark
Overall score was not computed because formula CDM required an unverified
toolchain.

The retained evaluator debug output records 94 failed TEDS samples among 665
intended samples, with the upstream error:

    AssertionError: can only join a started process

This limits table-score coverage. It is an upstream evaluator failure, not
an evidence of a production extraction failure.

### Current availability

| Component | Current status | Notes |
| --- | --- | --- |
| Historical metric artifacts | AVAILABLE_NOW | Full metrics, config, run metadata, and reports are retained |
| Project adapter and launcher | AVAILABLE_NOW | src/doc_extraction/evaluation/omnidocbench.py and experiment scripts remain |
| Full raw benchmark images | MISSING | Dataset directory absent locally |
| Full benchmark GT JSON | MISSING | OmniDocBench.json absent locally |
| Official evaluator checkout | MISSING | .external/OmniDocBench absent locally |
| Dedicated evaluator environment | MISSING | Historical setup is documented but not installed |
| Historical full predictions | MISSING | Full prediction directory absent locally |
| Evaluator source history | RECOVERABLE_FROM_GIT | Project adapter history exists; external evaluator must be reacquired |
| Full historical replay | PARTIALLY_RECOVERABLE | Requires data, evaluator, environment, and regenerated predictions |

### Scientific role

OmniDocBench should be retained as a **secondary benchmark**. It is valuable
for externally defined text, formula, table, and reading-order behavior.
It should not be the sole evaluator because it cannot directly express:

- region label correctness;
- source-to-table or source-to-cell ownership;
- duplicate evidence;
- role-routing decisions;
- whether a table object is attached to the IR element that serializes it;
- internal provenance;
- stamp/occlusion as the production corpus defines it.

The correct response to the 034a benchmark blind spots is to augment
benchmark evaluation, not abandon it.

## Existing evaluator architecture

The repository contains several useful evaluator components. It does not yet
contain one coherent end-to-end evidence evaluator.

| Component | Measured property | Limitation |
| --- | --- | --- |
| Production-corpus scorer | Expected strings, character similarity, order proxy | Sparse truth; flattened serializer behavior |
| evaluation/table_metrics.py | Grid positions, spans, cell content, lexical contamination | Requires appropriate table truth |
| 028 Layer 2 | Structure, canonical order, Page.reading_order, token ownership summaries | Tied to missing historical SCAN-49 raw IR |
| 029 replay | Mechanism attribution and evaluator counterexamples | Forensic research scripts, not a general interface |
| 035–040 analyses | GT geometry, strict D2, crop outcome, overlap checks | Weak content and serialized-evidence accounting |
| Production verification | Suspicious text and inherited table-quality signals | Self-check, not independent correctness truth |

The historical Layer-2 and table-content components are better aligned than
OmniDocBench alone with ownership and evidence questions. They still need
work before use as a permanent research contract:

- The 028 driver depends on absent Experiment 025 raw coverage artifacts.
- Per-cell text was deliberately classified UNMEASURABLE in SCAN-49.
- Ownership summaries are not a complete source-span ownership graph.
- No unified baseline-versus-treatment serialization comparison exists.
- No retrieval evaluator was found; building a full RAG system is not needed
  for this repository's current scope.

## Critical audit of Experiment 040

### Verified outcome counts

The compact Experiment 040 result file and 794 raw result files reproduce:

| Outcome | Count |
| --- | ---: |
| D2 region units | 28 |
| Controls | 766 |
| Valid recovery under frozen 040 rule | 4 |
| Structural invalidity among D2 units | 4 |
| Cross-table contamination among D2 units | 24 |
| Control no effect | 394 |
| Control false positive | 342 |
| Control contamination | 8 |
| Control duplication damage | 2 |
| Operational failure | 20 |

All 794 units map to development pages in the authoritative 039 manifest.
The recorded intervention modes are LABELLED_CROP for 774 attempted units and
NOT_INVOKED for the 20 unsupported-small-crop cases. No treatment output was
written into the canonical 039 baseline tree.

### Evidence content of the four valid recoveries

Direct inspection of the raw forced-crop tables after OCR text fill gives:

| Unit | Raw role | Cell count | Nonempty cells | Observation |
| --- | --- | ---: | ---:| --- |
| d2-453-2 | document_index | 60 | 0 | Empty structure |
| d2-474-2 | document_index | 16 | 0 | Empty structure |
| d2-2819-6 | list_item | 18 | 0 | Empty structure; baseline region has 136 characters |
| d2-4195-1 | code | 66 | 1 | One cell contains 891 characters already found in baseline region |

**Verified fact:** all four pass the frozen Experiment 040 definition.

**Inference:** these records do not establish four improvements in usable
text evidence. They may retain structural value, but the existing result
does not measure that value at cell, ownership, or consumer level.

### What the serialization check measures

Experiment 040 serialization_delta checks whether pre-existing elements
change or disappear and whether reading order changes after removing the
synthetic element from comparison.

It does not directly compare:

- baseline and treatment Markdown or equivalent canonical serialized evidence;
- source-text multiplicity before and after;
- text duplicated between an original region and a synthetic table;
- correct cell-level text placement;
- whether a table's new structure makes a fact more usable.

The ownership criterion identifies a unique candidate table for the synthetic
region under a conservative overlap rule. It does not establish globally
exclusive ownership of every source token or text span.

### Interpreting control false positives

The broad intervention remains scientifically rejected. But the meaning of
the 342 control false positives needs precision:

| Control false-positive detail | Count |
| --- | ---: |
| Classified false positive | 342 |
| Has any nonempty table cell | 71 |
| Has no populated table cell | 271 |

The 040 control definition correctly treats an unsupported, structurally
plausible table as a false positive. The count alone does not quantify
harmful textual misinformation or duplicated serialized text. Similarly, the
published 372/766 harmful-or-conflict composite includes 20 operational
failures. The directly semantic/structural adverse-outcome total excluding
operational failures is 352/766.

This is a clarification of the measure, not a relaxation of the conclusion:
broad non-table treatment is not supported.

## Role ontology and adapter audit

### Production role path

The current scanned-page path is:

    source page
        -> Docling conversion
        -> DoclingBackend.analyze / recognize
        -> Region.label and OCR tokens
        -> exact table-label crop gate
        -> TableTransformer / merge
        -> Page elements and tables
        -> Document serialization through element.table_id

The gate in src/doc_extraction/pipelines/base.py is exact:

    region.label.lower() == "table"

DoclingBackend emits lowercased labels directly from Docling. Its local
normalized role is lowercasing, not a semantic ontology. Layout confidence is
currently None in this path.

### document_index is not merely ordinary text under another name

Installed Docling code declares:

    TABLE_LABELS = [TABLE, DOCUMENT_INDEX]

and its TableItem model permits both labels while carrying structured table
data. The project adapter is narrower:

- DoclingBackend recognizes table-cell tokens only when label is exactly
  table.
- The whole-document path converts a structured Table only when label is
  exactly table.
- document_index maps to ElementType.OTHER in the local map.

**Inference:** a document_index TableItem can lose its structured-cell path
in this adapter. This is a concrete and more informative hypothesis than
generic "wrong role -> missing specialist".

**Unresolved:** historical raw Docling objects were not retained with enough
information to prove that this happened in every Experiment 040 case. It must
be tested prospectively with an upstream-to-IR trace.

### Role-related technical risks already established

- Region labels are ephemeral in the final Element representation.
- Candidate roles are not persisted.
- Routing decisions are mostly implicit control flow.
- Two label-to-element maps historically disagreed, including a verified
  checkbox vocabulary mismatch in Experiment 032.
- The project uses a stricter gate than the installed Docling table-label
  grouping.

## D2 and page-wide provenance

Strict D2 remains useful evidence of region/crop gating or ownership loss. It
does not demonstrate that TableTransformer was absent from the page.

Experiment 042 existing observational output confirms that the production
pipeline often invokes page-wide detection:

| Output population | PAGE_WIDE | LABELLED_CROP | BOTH | NONE |
| --- | ---: | ---: | ---: | ---: |
| Frozen 40-page pilot | 34 | 6 | 0 | 0 |
| 67 completed all-cohort entries | 64 | 3 | 0 | 0 |
| Union of persisted pages | 91 | 9 | 0 | 0 |

The union contains 100 distinct pages from all 40 source groups. It has zero
observed document_index regions. It is an availability census, not a random
prevalence study.

**Inference:** D2 can represent an ownership or serialization failure even
when page-wide specialist processing occurred. Therefore a D2 recovery
experiment must separately measure specialist awareness, table object
creation, ownership, table content, and final serialized evidence.

## Experiment 041 and 042

### Experiment 041

Experiment 041 correctly blocked before execution:

- Frozen 039 development layouts contained 15 document_index regions.
- The 15 identities were all frozen D2 identities.
- Eligible same-role controls were 0.
- No baseline provenance replay, treatment, or role-normalization
  counterfactual was executed.
- Heldout access was false.

This means 2/15 document_index recovery in Experiment 040 is neither a
false-positive estimate nor a safe production selector.

### Experiment 042

Experiment 042 has strong acquisition discipline:

| Property | Result |
| --- | --- |
| Frozen pages | 279 |
| Source-document groups | 40 |
| Categories | 5 |
| Recomputed population hash | Exact match |
| Acquired images | 279 / 279 |
| Missing images | 0 |
| Image-hash mismatches | 0 |
| Prior 035–041 overlap | 0 |
| 039 heldout overlap | 0 |
| Treatment | Not executed |
| Heldout access | False |

The full provenance index has status BASELINE_PROVENANCE_RUNNING but the
process is absent. It contains 67 complete and 212 pending entries, no
recorded operational failures, and was last updated on 2026-09-11. The
status is therefore stale.

At the observed 20.34 seconds per completed page, the remaining work is about
4,312 seconds, or 72 minutes, before startup and environment-repair effects.
Completion is technically feasible but should be conditional on a question
that the evidence evaluator cannot answer from existing data.

## CPU and environment audit

Current VM:

| Item | Current state |
| --- | --- |
| CPU | Intel Xeon @ 2.80 GHz; 16 logical CPUs / 8 cores |
| Memory | 62 GiB total, about 61 GiB available at audit |
| Disk | 223 GiB free |
| Python | 3.12.14 |
| Torch | 2.14.0+cpu |
| Torchvision | 0.29.0+cpu |
| Docling | 2.126.0 |
| EasyOCR | 1.7.2 |
| CUDA | unavailable |
| TableTransformer cache | present |
| OmniDocBench evaluator package | absent |

The environment has a practical issue: cv2 / EasyOCR currently fails to
import because libGL.so.1 is unavailable. The previous Experiment 042 run
used temporary extracted library files through LD_LIBRARY_PATH. That temporary
directory no longer exists.

The CPU VM is not the principal scientific blocker.

| Work | Resource classification |
| --- | --- |
| Re-score frozen results and inspect IR | CPU-cheap |
| Build/add evaluator controls | CPU-cheap |
| Adapter contract tests | CPU-cheap |
| Small unchanged replay | CPU-feasible after libGL repair |
| Remaining 042 pages | CPU-feasible; about 72 minutes under prior conditions |
| Full benchmark/model comparison | CPU-expensive; GPU acceleration useful |
| Reacquire benchmark data/evaluator | Network and environment dependent |

No immediate scientific task requires a GPU. A GPU first becomes justified for
a frozen corpus-scale comparison after a candidate repair and evaluator have
both been validated.

## Technical debt that matters to science

### Must fix before the next mechanism claim

- Add a paired evidence contract that distinguishes empty structure,
  redistributed text, new evidence, duplicate evidence, and damage.
- Compare actual production serialization before and after intervention.
- Preserve upstream item type, raw label, structured table data, and the
  adapter's preservation decision.
- Make every report state whether its denominator is pages, annotations,
  regions, tables, or source groups.
- Record explicit completion / failure state durably so a stale RUNNING flag
  cannot be mistaken for an active experiment.

### Fix eventually

- Consolidate duplicated experiment helpers for hashes, atomic writes and
  manifests.
- Restore the pinned OmniDocBench environment and address evaluator
  coverage/reporting.
- Resolve known route-specific label-map differences with narrow regression
  tests.
- Retain enough source inputs and paired outputs to replay major reports.

### Do not prioritize now

- Cosmetic experiment-directory refactoring.
- GPU throughput optimization.
- Cleanup of transient packages solely for a clean tree.

## Current research maturity

| Dimension | Score, 0–5 | Reason |
| --- | ---: | --- |
| Corpus reproducibility | 4 | Recent populations are frozen and audited; older raw assets are incomplete |
| Population identity | 4 | Strong hashes and group exclusions; some historical source equivalence remains uncertain |
| Treatment reproducibility | 3 | Exact crop and raw output preservation are strong; paired evidence comparison is incomplete |
| Provenance | 3 | Good local telemetry; insufficient upstream structured-content trace |
| Benchmark evaluation | 2 | Code and metrics survive, current replay inputs/environment do not |
| Evidence-centric evaluation | 2 | Useful components exist but are fragmented |
| End-to-end evidence evaluation | 1 | No coherent fact-level paired gain/damage measure |
| Causal identification | 2 | Conditional crop experiment is useful; mechanism/outcome still conflated |
| Heldout protection | 4 | Explicit development guards and identities exist |
| Compute portability | 3 | CPU path works, but depends on an ephemeral libGL workaround |
| Production observability | 3 | Table invocation modes visible; adapter losses insufficiently visible |
| Experiment archival | 2 | Compact results retained; important historical raw inputs missing |

## Competing directions

High cost and high confounding risk are unfavorable in this table.

| Direction | Scientific importance | Information gain | Compute cost | Engineering cost | Confounding risk | Reproducibility | Strong-evidence potential | Dead-end risk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Continue 042 control discovery | Medium | Medium | Medium | Low | High | High | Medium | High |
| Finish 042 then role normalization | High | Medium | Medium | Medium | High | High | Medium | Medium–High |
| Restore old benchmark stack wholesale | Medium | Medium | Medium | High | Medium | Medium | Medium | Medium |
| Build minimal unified evidence evaluator | Very High | Very High | Low | Medium | Low | High | Very High | Low |
| Change production ownership / roles immediately | High | Medium | Low | High | High | Medium | Medium | High |
| Acquire another targeted corpus | Medium | Medium | High | High | High | Medium | Medium | High |
| Stop all D2 research | Low | Low | Very Low | Very Low | Medium | Not applicable | Low | High opportunity cost |
| Audit upstream-to-IR content preservation | Very High | Very High | Low | Medium | Low | High | High | Low |

### Ranking

1. Minimal evidence evaluator and retrospective Experiment 040 audit.
2. Upstream Docling-to-IR content-preservation falsification.
3. Conditional completion of Experiment 042.
4. Restore OmniDocBench as a secondary benchmark.
5. New independent corpus only if a specified population gap remains.

Direction 1 dominates direction 2 because an adapter repair should not be
evaluated by a metric that can already classify empty tables as recovery.

## Recommended evaluation architecture

The minimum durable architecture is:

    production extraction with preserved intermediate evidence
        -> versioned evidence packet
        -> standard benchmark evaluator
        -> evidence-centric evaluator
        -> paired causal experiment evaluator

The standard benchmark evaluator remains responsible for external text,
formula, table, and reading-order measures. The evidence evaluator must add:

- source-item, token, region, table, cell, element, and serialized-span
  identities;
- baseline/treatment comparison through the actual serializer;
- separate content, structure, ownership, duplicate, damage, and cost views;
- explicit UNMEASURABLE values where truth is absent;
- adversarial controls for empty tables, copied prose, duplicated ownership,
  wrong-cell placement, and unattached table objects;
- error/missing-data accounting rather than survivor-only aggregates.

## Next three steps

### Step 1 — CPU only: paired evidence evaluator

**Objective:** audit frozen Experiment 040 records using a minimal
evidence-centric comparator built from existing table-content and Layer-2
components.

**Expected information gain:** establish whether each protocol recovery adds
correct text evidence, only structure, copied content, duplicate content, or
an unmeasurable change.

**Prerequisite:** freeze an additive evaluation contract and preserve original
Experiment 040 outcome labels.

**Success criterion:** every audited record has a clear evidence-state
verdict, traceable denominator, and adversarial evaluator controls.

**Stop condition:** paired baseline/treatment evidence cannot be reconstructed
faithfully. Report this limitation instead of inferring success.

### Step 2 — next research experiment: upstream preservation falsification

**Objective:** test whether Docling already contains structured table evidence
that this adapter discards for document_index and related cases.

**Expected information gain:** distinguish recognition loss, adapter loss,
ownership loss, and serialization loss.

**Prerequisite:** Step 1 comparator; frozen development cases/controls;
versioned upstream-object snapshots with model/environment identity.

**Success criterion:** a reproducible source-item -> adapter -> IR ->
serialization trace demonstrates preservation or loss in both positive and
negative cases.

**Stop condition:** source evidence is absent, the effect is a role rename
without content implications, or a candidate repair duplicates/misattributes
evidence.

### Step 3 — first justified GPU experiment

**Objective:** compare a frozen extraction/adapter variant with baseline on an
independent corpus using both benchmark and evidence evaluators.

**Expected information gain:** test generalization without sacrificing output
quality or evidence integrity.

**Prerequisite:** validated metrics, a reproducible CPU result, restored
benchmark runtime/data, and a frozen candidate.

**Success criterion:** complete paired coverage, explicit evidence
improvement, bounded damage, and measured cost.

**Stop condition:** evaluator failures, environment drift, untraceable
outputs, or gains confined to a proxy.

## Activities to abandon or pause

Abandon:

- universal non-table forced-crop treatment;
- treating strict D2 as evidence that no page-wide specialist ran;
- treating structure-plus-IoU acceptance as proof of usable evidence;
- using unchanged old elements as proof of no evidence duplication;
- treating every overlap rejection as semantic contamination;
- selector training on the current small, retrospectively characterized
  population;
- geometry-only and OCR-sparsity-only selector directions.

Pause:

- role-specific corpus expansion until the evidence and adapter questions are
  measured;
- new crop experiments selected from observed successful cases;
- benchmark restoration as a substitute for ownership/evidence evaluation;
- continuation of a large baseline solely because pages are already acquired.

## Final decision

**RESTORE_EVALUATOR_FIRST**

Experiment 042 has strengthened source identity and invocation provenance
practice. It has not yet supplied natural document_index controls, and the
current recovered-output evidence shows that the preceding crop study did not
demonstrate usable textual evidence gain.

The next scientific question is therefore:

    Does the adapter preserve structured upstream evidence, and can a
    prospective change improve correct serialized evidence without adding
    empty, copied, or duplicate output?

Answer that before further investment in same-role control acquisition,
selector design, role normalization, treatment, or heldout evaluation.

## Audit boundaries

This audit made no production extraction change, no role-map change, no
heldout access, no new corpus acquisition, no new treatment invocation, and
no rewrite of prior experiments. It used manifest split metadata and prior
published aggregate artifacts only for provenance reconciliation.
