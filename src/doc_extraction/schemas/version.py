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
"""

SCHEMA_VERSION = "1.1.0"
