# Fault-injection validation

Six controlled state mutations were applied to the existing deterministic
`classify_loss_boundary` function. They do not modify production extraction or
re-run documents.

| Injection | Intended | Detected | Correct |
| --- | --- | --- | --- |
| FI-ACQ | acquisition | acquisition | yes |
| FI-OWN | ownership | ownership | yes |
| FI-REC | reconciliation | reconciliation | yes |
| FI-PROJ | canonical projection | canonical projection | yes |
| FI-SER | serialization | serialization | yes |
| FI-NORM | normalization | normalization | yes |

This is functional discrimination (6/6), not causal identification. The
injection supplies the classifier's stage-state inputs directly; a real run
does not independently observe all of those inputs. A missing truth-side token
can arise from acquisition, coordinates, or segmentation, as the no-centre
diagnosis demonstrates. Fault injection therefore does not validate real-world
boundary attribution.
