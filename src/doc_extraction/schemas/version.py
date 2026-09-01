"""Canonical IR schema version.

Bump this whenever the serialized shape of `Document`/`Page`/`Element`/
`Table` changes in a way that a consumer could notice. Every serialized
`Document` carries it as `schema_version`, so a result file found on disk
months later can be interpreted (or rejected) without guessing which
revision of the code produced it.

History
-------
1.0.0
    Initial IR: Document/Page/Element/Table, `page_number` always an int.
1.1.0
    * `Element.page_number` and `Table.page_number` became nullable — None
      means "this source format has no rendered pagination", replacing the
      previous behaviour of fabricating page 1 for DOCX.
    * Added `Document.schema_version`.
    * Added `Page.coordinate_origin` and documented the top-left, y-down
      convention as binding on all backends.
    * Added `Page.source` provenance (route + backend that produced it).
1.2.0
    * Added `RunMetadata.device_decision` — nullable. When `config.device`
      was `"auto"`, records the GPU state observed at selection time and the
      rule that fired (see utils/resources.py); None for an explicit
      `cpu`/`cuda`, which is not probed.

      Additive and backward-compatible: a 1.1.0 consumer that ignores
      unknown keys reads a 1.2.0 document unchanged, and every 1.1.0 field
      keeps its meaning. A 1.2.0 consumer reading a 1.1.0 document sees the
      field absent, which is indistinguishable from "device was explicit" —
      so treat a *missing* field as "unknown provenance", not as "explicit".
"""

SCHEMA_VERSION = "1.2.0"
