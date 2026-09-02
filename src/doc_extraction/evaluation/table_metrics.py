"""Cell-level table evaluation, with structure and content scored separately.

Why this exists
---------------
Experiment 010 found a table whose cells contained fabricated strings —
`'NBHộH'`, `'ỆGTói'` — while the document scored **0.875** document-level
`must_contain` recall and raised no warning. The benchmark that discovered the
worst failure in the project could not measure it, because string recall over
a handful of body fragments is blind to what is inside a cell: the strings it
looks for were present elsewhere on the page.

A metric that cannot see a failure cannot verify its fix. This module is the
missing measurement.

The two dimensions
------------------
A table is not correct because text exists in it. Two independent things can
be wrong and they call for different repairs, so they are never summed:

**STRUCTURE** — did we find the right grid? Rows, columns, spans, and whether
a cell exists at each position. A structure failure means the table detector
or the ruling-line analysis is wrong; more OCR will not help.

**CONTENT** — is the text in each cell the right text, and *only* the right
text? A content failure with correct structure is an ownership or recognition
problem, and the grid is fine.

The stamped-table case is precisely a table with **perfect structure and
corrupt content**, which is why a single blended score would have hidden it.

Contamination
-------------
The signal that matters most here, and the one no standard table metric
reports. A cell is *contaminated* when it holds text that belongs to no
expected cell anywhere in the table — foreign material that a consumer cannot
distinguish from a real value. This is tracked separately from a plain
mismatch because the consequences differ: a missing cell is visibly missing,
while a contaminated cell reads as data.

What this deliberately does not do
----------------------------------
No TEDS. TEDS blends structure and content into one tree-edit distance, which
is the exact conflation this module exists to undo, and it requires an HTML
serialization the IR does not produce. Exact and normalized cell matching
answers the question at hand — *did this cell come back right* — and stays
interpretable when it fails.
"""
from __future__ import annotations

import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any

from doc_extraction.schemas.table import Table


def normalize(text: str | None) -> str:
    """NFC-normalize and collapse whitespace.

    Vietnamese is the reason NFC is not optional: `Bộ` composed and `Bộ`
    decomposed are different strings and the same word, and PDF producers
    emit both. Comparing without normalizing would report diacritic-heavy
    Vietnamese cells as wrong when they are right.
    """
    if not text:
        return ""
    return " ".join(unicodedata.normalize("NFC", text).split())


@dataclass
class TableGroundTruth:
    """The grid a table is expected to produce.

    `grid` is row-major, dense: `grid[r][c]` is the text expected at that
    position, `""` for a legitimately empty cell. `spans` optionally records
    `(row, col) -> (row_span, col_span)` for merged cells; positions covered
    by a span other than its origin should be `""` in `grid`.
    """

    grid: list[list[str]]
    spans: dict[tuple[int, int], tuple[int, int]] = field(default_factory=dict)
    label: str = ""

    @property
    def n_rows(self) -> int:
        return len(self.grid)

    @property
    def n_cols(self) -> int:
        return max((len(r) for r in self.grid), default=0)

    def cells(self) -> dict[tuple[int, int], str]:
        return {(r, c): normalize(v)
                for r, row in enumerate(self.grid)
                for c, v in enumerate(row)}

    def vocabulary(self) -> set[str]:
        """Every whitespace-token the table legitimately contains.

        Contamination is defined against this set: a token in a predicted cell
        that appears nowhere in the expected table came from somewhere else.
        """
        vocab: set[str] = set()
        for row in self.grid:
            for value in row:
                vocab.update(normalize(value).split())
        return vocab


@dataclass
class StructureScore:
    """Did we find the right grid?"""

    rows_expected: int = 0
    rows_found: int = 0
    cols_expected: int = 0
    cols_found: int = 0
    shape_exact: bool = False
    cells_expected: int = 0
    cells_found: int = 0
    positions_matched: int = 0        # expected positions that exist in the prediction
    spans_expected: int = 0
    spans_recovered: int = 0
    cells_with_bbox: int = 0

    @property
    def position_recall(self) -> float:
        return self.positions_matched / self.cells_expected if self.cells_expected else 0.0

    @property
    def span_recall(self) -> float:
        if not self.spans_expected:
            return 1.0
        return self.spans_recovered / self.spans_expected

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["position_recall"] = round(self.position_recall, 4)
        d["span_recall"] = round(self.span_recall, 4)
        return d


@dataclass
class ContentScore:
    """Is the text right, and only the right text?"""

    cells_compared: int = 0
    exact_matches: int = 0            # normalized string equality
    text_present: int = 0             # expected non-empty, predicted non-empty
    missing_text: int = 0             # expected non-empty, predicted empty
    extra_text: int = 0               # expected empty, predicted non-empty
    contaminated_cells: int = 0       # predicted holds a token from outside the table
    fragmented_cells: int = 0         # predicted holds a piece of a source run
    # Token-level, over all cells: how much of the expected text came back, and
    # how much of what came back was expected.
    tokens_expected: int = 0
    tokens_predicted: int = 0
    tokens_correct: int = 0
    contamination_detail: list[dict[str, Any]] = field(default_factory=list)
    mismatch_detail: list[dict[str, Any]] = field(default_factory=list)

    @property
    def cell_exact_accuracy(self) -> float:
        return self.exact_matches / self.cells_compared if self.cells_compared else 0.0

    @property
    def cell_text_precision(self) -> float:
        return self.tokens_correct / self.tokens_predicted if self.tokens_predicted else 0.0

    @property
    def cell_text_recall(self) -> float:
        return self.tokens_correct / self.tokens_expected if self.tokens_expected else 0.0

    @property
    def cell_text_f1(self) -> float:
        p, r = self.cell_text_precision, self.cell_text_recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def contamination_rate(self) -> float:
        return self.contaminated_cells / self.cells_compared if self.cells_compared else 0.0

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.update(
            cell_exact_accuracy=round(self.cell_exact_accuracy, 4),
            cell_text_precision=round(self.cell_text_precision, 4),
            cell_text_recall=round(self.cell_text_recall, 4),
            cell_text_f1=round(self.cell_text_f1, 4),
            contamination_rate=round(self.contamination_rate, 4),
        )
        return d


@dataclass
class TableScore:
    """Both dimensions, never blended into one number."""

    table_id: str
    structure: StructureScore
    content: ContentScore
    # What the pipeline's own gate said, when one ran. Recorded alongside the
    # truth so gate precision/recall can be computed over a corpus: this is
    # the only way to tell a useful gate from a noisy one.
    gate_trusted: bool | None = None
    gate_severity: str | None = None
    gate_signals: list[str] = field(default_factory=list)

    @property
    def is_corrupt(self) -> bool:
        """Ground truth for gate evaluation: did this table actually come back
        wrong in a way a consumer could not detect?"""
        return self.content.contaminated_cells > 0 or self.content.fragmented_cells > 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "table_id": self.table_id,
            "structure": self.structure.as_dict(),
            "content": self.content.as_dict(),
            "is_corrupt": self.is_corrupt,
            "gate_trusted": self.gate_trusted,
            "gate_severity": self.gate_severity,
            "gate_signals": list(self.gate_signals),
        }


def score_table(
    predicted: Table,
    truth: TableGroundTruth,
    source_runs: list[str] | None = None,
) -> TableScore:
    """Score one predicted table against its expected grid.

    `source_runs` are the raw text runs available on the page. When supplied,
    a cell whose text contains a token belonging to no complete run is counted
    as *fragmented* — the signature of coordinate-based text gathering cutting
    a run in half. Without them that check is skipped rather than guessed at.
    """
    pred_cells = {(c.row, c.col): normalize(c.text) for c in predicted.cells}
    pred_boxes = {(c.row, c.col): c.bbox for c in predicted.cells}
    true_cells = truth.cells()
    vocab = truth.vocabulary()

    # --- structure --------------------------------------------------------
    spans_expected = len(truth.spans)
    spans_recovered = 0
    for (r, c), (rs, cs) in truth.spans.items():
        cell = next((x for x in predicted.cells if x.row == r and x.col == c), None)
        if cell is not None and cell.row_span == rs and cell.col_span == cs:
            spans_recovered += 1

    structure = StructureScore(
        rows_expected=truth.n_rows,
        rows_found=predicted.n_rows,
        cols_expected=truth.n_cols,
        cols_found=predicted.n_cols,
        shape_exact=(predicted.n_rows == truth.n_rows and predicted.n_cols == truth.n_cols),
        cells_expected=len(true_cells),
        cells_found=len(pred_cells),
        positions_matched=len(set(true_cells) & set(pred_cells)),
        spans_expected=spans_expected,
        spans_recovered=spans_recovered,
        cells_with_bbox=sum(1 for b in pred_boxes.values() if b is not None),
    )

    # --- content ----------------------------------------------------------
    content = ContentScore()
    for pos in sorted(set(true_cells) | set(pred_cells)):
        want = true_cells.get(pos, "")
        got = pred_cells.get(pos, "")
        content.cells_compared += 1

        want_tokens = want.split()
        got_tokens = got.split()
        content.tokens_expected += len(want_tokens)
        content.tokens_predicted += len(got_tokens)

        # Multiset intersection: a token repeated twice in the prediction but
        # once in the truth counts once, so duplication is penalized.
        remaining = list(want_tokens)
        for tok in got_tokens:
            if tok in remaining:
                remaining.remove(tok)
                content.tokens_correct += 1

        if want == got:
            content.exact_matches += 1
        elif want and got:
            content.mismatch_detail.append(
                {"cell": f"r{pos[0]}c{pos[1]}", "expected": want, "got": got})

        if want and got:
            content.text_present += 1
        elif want and not got:
            content.missing_text += 1
            content.mismatch_detail.append(
                {"cell": f"r{pos[0]}c{pos[1]}", "expected": want, "got": ""})
        elif got and not want:
            content.extra_text += 1

        # Contamination: a token from outside the table's own vocabulary.
        foreign = [t for t in got_tokens if t not in vocab]
        if foreign:
            content.contaminated_cells += 1
            content.contamination_detail.append(
                {"cell": f"r{pos[0]}c{pos[1]}", "text": got, "foreign_tokens": foreign})

        # Fragmentation: a token that is not part of any whole source run.
        if source_runs and got:
            runs_n = [normalize(r) for r in source_runs]
            for tok in got_tokens:
                if len(tok) >= 2 and not any(tok in r for r in runs_n):
                    content.fragmented_cells += 1
                    break

    return TableScore(table_id=predicted.id, structure=structure, content=content)


@dataclass
class CorpusTableReport:
    """Aggregate over many tables, plus gate precision/recall.

    The gate numbers are the point of aggregating at all. A gate that flags
    every table has perfect recall and is useless; one that flags nothing has
    perfect precision and is useless. Only the pair says whether it works.
    """

    scores: list[TableScore] = field(default_factory=list)

    def add(self, score: TableScore) -> None:
        self.scores.append(score)

    def summary(self) -> dict[str, Any]:
        n = len(self.scores)
        if not n:
            return {"tables": 0}

        def mean(f) -> float:
            return round(sum(f(s) for s in self.scores) / n, 4)

        corrupt = [s for s in self.scores if s.is_corrupt]
        judged = [s for s in self.scores if s.gate_trusted is not None]
        flagged = [s for s in judged if not s.gate_trusted]
        tp = sum(1 for s in flagged if s.is_corrupt)
        fp = len(flagged) - tp
        fn = sum(1 for s in judged if s.gate_trusted and s.is_corrupt)

        gate: dict[str, Any] = {
            "tables_judged": len(judged),
            "flagged": len(flagged),
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
        }
        if judged:
            gate["precision"] = round(tp / len(flagged), 4) if flagged else None
            gate["recall"] = round(tp / (tp + fn), 4) if (tp + fn) else None
            gate["false_alarm_rate"] = round(
                fp / max(1, len(judged) - len(corrupt)), 4)

        return {
            "tables": n,
            "structure": {
                "shape_exact": sum(1 for s in self.scores if s.structure.shape_exact),
                "mean_position_recall": mean(lambda s: s.structure.position_recall),
                "mean_span_recall": mean(lambda s: s.structure.span_recall),
            },
            "content": {
                "mean_cell_exact_accuracy": mean(lambda s: s.content.cell_exact_accuracy),
                "mean_cell_text_precision": mean(lambda s: s.content.cell_text_precision),
                "mean_cell_text_recall": mean(lambda s: s.content.cell_text_recall),
                "mean_cell_text_f1": mean(lambda s: s.content.cell_text_f1),
                "mean_contamination_rate": mean(lambda s: s.content.contamination_rate),
                "tables_with_contamination": len(
                    [s for s in self.scores if s.content.contaminated_cells]),
                "tables_with_fragmentation": len(
                    [s for s in self.scores if s.content.fragmented_cells]),
            },
            "corrupt_tables": len(corrupt),
            "gate": gate,
        }
