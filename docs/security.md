# Security model

## Trust boundaries

- Repository URLs, refs, source files, tool descriptions, and scanner output are untrusted.
- Only HTTPS repositories on the configured host allowlist are accepted.
- Embedded credentials, nonstandard ports, private DNS results, symbolic links, excessive file
  counts, and excessive unpacked size are rejected.
- Repository code is inspected but never imported or executed.
- Secret findings redact matched credential values.

## Runtime controls

The API and worker use read-only filesystems, dropped Linux capabilities, no-new-privileges, and
temporary filesystems. The worker also has CPU, memory, PID, task, clone, Semgrep, and file-size
limits. Production deployments should put the API behind a TLS reverse proxy and restrict port
8000 to that proxy.

## Decision safety

Confirmed critical findings and likely or confirmed tool poisoning are rejected. Medium or higher
findings require human review. Scanner failure also requires human review. Only completed coverage
without blocking evidence can pass.

