# 039 acquisition checkpoint

**Checkpoint:** frozen corpus acquired; production baseline not started.

Acquisition completed before the VM shutdown handoff.  The official
DocLayNet 1.0.0 validation annotation member was reused from the verified 038
download, while 039 page images were downloaded using the bounded Range
acquisition script.  The 28 GiB source archive was not retained.

| Quantity | Value |
|---|---:|
| selected records | 269 |
| table pages | 174 |
| non-table control pages | 95 |
| source-document groups | 33 |
| development groups | 17 |
| held-out groups | 16 |
| local image files | 269 |
| result directory size | 92 MB |

The frozen manifest SHA-256 is:

```
55fe36b5f39e1e87437f81ed2cc2d120e5c7d747b1f3109318b06d530b50f8e5
```

The annotation-member SHA-256 is:

```
eacd2ba2a32e6c2ebe2dc5ea1545f405d8461c46bba53e0c35d9c54fba0bcef6
```

The offline audit reports zero missing images, zero image-hash mismatches,
zero source-link mismatches, and zero identity overlap with 035, 036, 037, or
038.  Atomic image writes and deterministic selection are implemented by
`acquire_doclaynet.py`.

No production baseline, D2 analysis, selector, forced-crop counterfactual, or
held-out evaluation exists for 039.  The CPU VM should resume by rerunning the
acquisition script only if the manifest audit identifies missing files; once
the manifest is verified, it should run the unchanged baseline and then apply
the preregistered adequacy criterion without changing the population.
