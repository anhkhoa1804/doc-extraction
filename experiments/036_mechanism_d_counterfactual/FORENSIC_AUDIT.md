# Experiment 036 — Post-Execution Forensic Audit

## Method

`forensic_audit.py` is a fresh-process, independent aggregation path. It does not import `analyze.py` and recomputes the frozen structural-validity, ownership, IoU, conflict, and recovery rules directly from the 34 treatment and 145 control raw JSON records. It validates each raw case's manifest payload, source-image hash, source layout/document hashes, target bbox, and source-page run. It also recreates the strict D2 identity set directly from frozen 035 matching records and recreates each control's largest non-table crop from its frozen Phase 13 layout result.

The resulting tracked [forensic_audit.json](forensic_audit.json) includes every D2 case-level row and all agreement flags. Raw outputs remain intentionally ignored.

## Population and raw-record integrity

- Strict D2 reconstructed from 035: 34; 036 treatment manifest: 34; raw treatment records: 34.
- The treatment identity set, `(image, gt_table_anno_id)`, exactly equals frozen 035 D2. GT bbox links, source image hashes, source layout hashes, source documents, and exact layout-region crop boxes all agree.
- Frozen Phase 13 frame: 150 pages. It partitions exactly into 145 controls and 5 explicit `no_non_table_layout_region` exclusions, with no duplicate image identity.
- Each control's recorded box is independently reproduced by the preregistered largest-area non-table selection rule; no result field participates in selection.
- Every raw record has status `success`; no duplicate output identity or missing expected record exists. Resume writes only missing/non-success case IDs. Historical shell interruptions yielded no partial JSON case record.

## Independent recomputation

| Quantity | Independent raw result | Agreement |
| --- | ---: | --- |
| Treatment invocation / detector / valid structure / ownership | 34 / 14 / 31 / 31 of 34 | yes |
| Treatment valid recovery / conflict | 17 / 8 of 34 | yes |
| Control invocation / detector / valid structure / ownership | 145 / 38 / 104 / 104 of 145 | yes |
| Control forced-crop false positive / conflict | 104 / 3 of 145 | yes |
| Case-wall runtime | 179 records; 2,875.5174 s | corrected; see below |

Treatment intersections: detector-and-structure = 14; detector-and-recovery = 7; recovery-and-conflict = 0; recovery-without-detector = 10; structure-without-detector = 17. Thus all eight conflicts are non-recoveries under the frozen definition, not cases counted in both marginals.

Control description: of 104 control forced-crop false positives, 23 also have crop-detector evidence and 81 are structure-only. Three false positives overlap an existing production table. The most common roles are picture (51), text (29), list_item (10), formula (8), section_header (3), and document_index (3). This is descriptive only: `104/145` is the preregistered eligible-control-crop rate, not a corpus-wide or whole-system false-positive rate.

## Discrepancy and repair

The original tracked `summary.json` and `RESULTS.md` reported 2,876.291 seconds. A clean raw aggregation after the final resumed controls were present gives 2,875.5174 seconds. This is a stale compact runtime aggregate caused by summarization before the final resumed records had settled, not a model, population, or outcome discrepancy. `summary.json` and `RESULTS.md` are corrected in this checkpoint. All count-based scientific conclusions are unchanged.

## Backend/helper audit

The helper reuses the production `TableTransformerBackend` instance, its lazy loader, exact Microsoft model IDs, processors, thresholds (detection 0.7; structure 0.6), `eval()` state, `torch.no_grad()`, and Transformers postprocessing. Its forced-crop path is exactly the existing production labelled-region behavior: crop supplied bbox, then structure recognition. Its detector call is additive experimental observation on that same crop. It translates detector-local coordinates once by the crop origin; forced structure already receives page-pixel bbox coordinates.

It does not touch layout labels, production table gating, ownership/merge code, source images, or production output directories. It does not mutate model parameters or shared inference state: the only shared action is the normal lazy model cache, and all forwards are `eval()`/`no_grad()`. A production call after a helper call therefore sees the same loaded model instance it would otherwise have loaded. The public method is explicitly named and documented as counterfactual, and has no duplicate model-loading implementation.

The semantic limitation is intentional and now explicit: isolated ownership is necessarily close to tautological once a valid forced table retains the same supplied crop bbox. It is a counterfactual owner-assignment check, not proof that a production policy should assign ownership.

## Model-loading audit

Fresh offline loads of both cached checkpoints report `model_type=table-transformer`, architecture `TableTransformerForObjectDetection`, zero missing keys, and zero mismatched keys. Detection has the expected two labels (`table`, `table rotated`); structure has the expected six structural labels including row and column. Parameter payloads are 115,197,724 and 115,314,476 bytes respectively (about 220 MiB combined before framework/runtime workspace), so an L4 would have ample weight-memory headroom if its driver becomes usable; no GPU inference claim is made here.

Each load has exactly three unexpected `BatchNorm.num_batches_tracked` buffers in ResNet downsample blocks. These are non-learnable running-count buffers; with no missing/mismatched parameters and matching task configurations, this is a benign compatibility warning from the current Transformers loader, not evidence of a wrong checkpoint or architecture. The audit records exact key names rather than suppressing the warning.

## Definition and boundary audit

The frozen definition is faithfully implemented: structure requires a nonempty positive grid and escape fraction `< 0.2`; isolated ownership is owner IoU `> 0.1`; GT relevance is IoU `>= 0.3`; a conflict is production-table IoU `> 0.1`; valid recovery requires all preceding conditions and no conflict. New tests cover the exact 20% cell-escape boundary, `>= 0.3` recovery threshold, and `> 0.1` conflict boundary. There are no multi-target treatment cases in this frozen manifest, but both runner and aggregator preserve target-level handling.

## Device and provenance

Current `nvidia-smi` still cannot communicate with the NVIDIA driver. The CUDA-enabled environment reports zero usable devices; the CPU environment reports `torch 2.13.0+cpu`. No L4 smoke was run because no usable GPU exists. Raw arm metadata confirms CPU device, exact model IDs, and library versions. Future runner writes are now atomic, preserve initial immutable run metadata, reject model/device-mismatched resume attempts, and record every resume attempt separately.

## Verdict

**036_CONFIRMED_WITH_LIMITATIONS.** All scientific primary quantities, populations, crops, source identities, thresholds, model identities, and intersections independently reproduce. Limitations remain the preregistered eligible-control-crop scope, counterfactual (not end-to-end) ownership, CPU-only performance evidence, and the corrected stale runtime aggregate.
