# VA-017 fork regression coverage

This first test change runs against the current 2.14.0-derived fork. It does not
upgrade or release an image and does not certify all differences as intentional.

## Baseline

- Fork main: `3be1fd5a3a97efa22cc16ef7c1dc46963deb6bc5`.
- Existing `v2.14.0-open` tag: `3994da74d7e988f6c3e98b72b3e447b42a11a326`.
- The thread-stack-size change was reverted. Do not resurrect it during upgrade.
- Comparing the tree to the official v2.14.0 tag yields 270 changed files. The
  fork was imported as one initial commit, so this difference is not a reliable
  inventory of custom patches. Identify the matching upstream snapshot before
  porting changes to 2.18.0.

## Tests added

| Test | Regression caught |
| --- | --- |
| `va017_middleware_preserves_request_and_downstream_error_response` | Middleware consumes or changes the GraphQL body, drops authorization/correlation headers or query parameters, or replaces downstream 401/403/502 responses. Exercises the actual middleware with a local handler and a licensed state. |
| `va017_invalid_schema_never_starts_a_server` | Modified startup stops rejecting malformed schema before opening a server. |
| `va017_invalid_schema_reload_preserves_running_server_and_can_recover` | Invalid reload terminates the state machine, replaces the server, or prevents a subsequent valid reload. Real schema parsing; mocked router/server factories enforce lifecycle call counts. |
| `va017_preview_feature_gate_is_still_enforced_before_startup` | Changes around license handling accidentally bypass the independent preview-feature gate. |

These tests do not authorize or establish compliance of the fork's license-gating
changes. They preserve adjacent HTTP and lifecycle contracts. Existing license
report tests must still run; failures must be triaged, not deleted or rebaselined
merely to turn CI green.

The Connect v0.4 fixture is intentionally a 2.14-era preview feature. In 2.18,
replace it with an upstream-supported feature that is still gated (for example
Connect v0.5 after verifying its fixture); do not retain an obsolete rejection.

## CI

Use `--locked` for builds and tests. Run license, state-machine and HTTP factory
suites separately (Cargo accepts a single positional test filter). Discover the
`va017` tests before executing them and reject a count below four, so a rename
cannot silently produce a successful run with zero regression tests.

## Verification — 2026-10-12

Local macOS ARM64, Rust/Cargo 1.95.0, locked dependencies. The existing `stable`
toolchain resolves to exactly 1.95.0 on this machine. Official protoc 36.2 was
downloaded into a temporary directory and checked against its published SHA-256.

| Command suffix after `cargo +stable test --locked -p apollo-router --lib` | Result |
| --- | --- |
| `va017` | 4 passed |
| `license_enforcement` | 24 passed |
| `state_machine` | 52 passed |
| `axum_http_server_factory` | 6 passed |

The four new tests are included in the three surrounding suites: 82 distinct
tests passed, not 86. The first sandboxed run passed three new tests and denied
the mock server's localhost bind; rerunning with local socket access passed all
four. No staging endpoint or business data was used. Existing unused-import and
dead-code compiler warnings remain; they were not suppressed.

Changed Rust files pass `rustfmt --check`; the diff passes `git diff --check`;
the workflow parses as YAML. The old two-filter CI command was also reproduced
as a Cargo argument error. These are local results, not a GitHub Actions run,
full repository suite, Linux build, image scan, or staging acceptance.

## Remaining coverage before release

- Establish custom patch inventory against the matching upstream snapshot.
- Exercise real HTTP authentication rejection via the complete router stack;
  the middleware test preserves downstream rejection but does not validate JWTs.
- Synthetic WebSocket subscription connect/disconnect/cleanup and token routing.
- Mock-subgraph multipart upload, size limits, timeout and cancellation.
- Federated query and error propagation with a sanitized representative schema.
- OTLP trace/header propagation, metrics and graceful shutdown.
- Image tests on both amd64/arm64, digest-bound scans, SBOM and release policy.
- Negative controls: deliberately remove header/body forwarding, replace error
  status, bypass preview checks, or terminate on invalid reload; the relevant
  tests must fail. Perform these only in a disposable copy and retain logs.

Staging runtime acceptance remains a later checkpoint; SIT/UAT are configuration
handoffs for their deployment owners. Unit tests alone are not deployment proof.
