# Web Acquisition Service

This is an independent, security-first acquisition component. It discovers
URLs under an explicit crawl policy, fetches permitted responses, and stores
immutable content-addressed artifacts with acquisition provenance. It does not
parse PDFs or Office files, perform OCR, build knowledge graphs, embed text,
or implement KP/CDOI semantics.

```text
seed URL -> policy -> frontier -> fetch -> immutable artifact -> provenance
                                                     |
                                                     +-> optional doc-extraction public API seam
```

## Run locally

```bash
uv run crawler crawl https://example.com --max-depth 1 --max-pages 20 \
  --output state/artifacts --database state/metadata.sqlite
```

`crawler serve` exposes a process-local operator API. It requires a
`WEB_ACQUISITION_API_TOKEN` of at least 32 ASCII characters. The API enqueues
jobs; it does not run a crawl in an HTTP request.

## Policy and artifacts

`CrawlPolicy` is frozen into every `CrawlJob`. It limits scope, depth, pages,
response and total bytes, redirects, retries, concurrency, headers, HTML
parsing, and discovery fan-out. Default scope is the seed origin. Robots
compliance is a separate policy concern and never overrides network security.

Bodies are streamed into a private pending directory, SHA-256 hashed, and
published as immutable `sha256:<digest>` artifacts only after completion. The
SQLite metadata store records the job, discovered resource, parent resource,
depth, discovery method, fetch attempts, final URL, and artifact identity.

## Security model

All seed and discovered URLs are untrusted. The fetch path rejects private,
loopback, link-local, multicast, unspecified, reserved, translated, and tunnel
IP ranges; validates every DNS answer; dials a validated literal IP; validates
the connected peer; and repeats policy and egress checks for every redirect.
TLS certificate and hostname validation cannot be disabled in the production
fetcher. URL query values and runtime credentials are not persisted. Cookie and
Authorization headers are exact-HTTPS-origin scoped and job-local.

## Current limitations

This MVP intentionally has:

* SQLite only; no PostgreSQL adapter;
* process-local jobs; no durable resume or distributed worker queue;
* HTTP fetch only; no browser rendering or JavaScript execution;
* no browser authentication flow or persistent cookie jar;
* no `ExtractionPackage v1` implementation.

The optional `integration.py` seam materializes a verified artifact and calls
the documented `doc_extraction.cli.process_file` public API. It is not an
`ExtractionPackage` adapter. KP/CDOI integration remains blocked until the
contract owner supplies an authoritative, versioned external contract.
