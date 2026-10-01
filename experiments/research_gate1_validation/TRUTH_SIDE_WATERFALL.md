# Truth-side denominator and waterfall

## Unit and denominator

The unit is one pre-frozen, geometry-linked OmniDocBench `text_block` or
`title` annotation per Experiment 046 case. This produces 24 truth units,
clustered by 24 distinct source groups. It is independent of the ledger
candidate generator, but is not token-level truth and contains no owner label.

`OCR token centre in truth locator` is intentionally not named acquisition:
a truth unit without such a centre is **not proven unacquired**. It may instead
be affected by coarse OCR spans, annotation segmentation, or locator geometry.

## Measured waterfall

| Truth-side state | Truth units | Rate of 24 |
| --- | ---: | ---: |
| truth exists | 24 | 100.0% |
| OCR token centre in locator | 17 | 70.8% |
| exact truth text acquired | 9 | 37.5% |
| exact text + uniquely accepted ownership | 8 | 33.3% |
| exact text represented canonically | 9 | 37.5% |
| exact text represented in Markdown | 9 | 37.5% |
| exact text with provenance to acquisition | 9 | 37.5% |

The rows are not a single irreversible chain after ownership: one exact-text
unit was canonically represented despite ambiguous ledger ownership. Treating
the table as a conventional funnel would hide that conflict.

## Complementary states

* 7/24 units had no OCR-token centre in their locator: 5 challenge and 2
  controls. This differs from the prompt's historical `8/21` claim; the
  immutable 046-v2 artifact is authoritative for this analysis.
* 8/24 had a token centre but no normalized-exact truth text.
* 1/24 had exact text but ownership ambiguity.
* All 9 exact-text units were already represented canonically and serialized;
  none is a canonical-projection or serialization loss under the frozen rule.

This demonstrates that candidate-centric counts alone understate the 15/24
truth units that did not yield exact acquired text. It does **not** establish
which real pipeline stage caused those 15 misses.
