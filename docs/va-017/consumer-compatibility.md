# VA-017 Vahalla consumer compatibility

Source inspection: 2026-10-13. This is a source snapshot and synthetic-test contract, not evidence that the new Router is running in staging. No application sources, deployment values or mono gitlinks are changed by this PR.

## Reviewed source snapshots

| Repository | Commit | Relevant source |
| --- | --- | --- |
| vahalla-wealth/vahalla-graph | `ad81e853091e8ac19dc8d24fbb94f0379c1c5317` | [router.yaml](https://github.com/vahalla-wealth/vahalla-graph/blob/ad81e853091e8ac19dc8d24fbb94f0379c1c5317/router.yaml), `supergraph.yaml`, chart Router deployment and config copy |
| vahalla-wealth/vahalla-web | `e08e9a7a93f3d05716fbc588be90b659576b6b0e` | [notification hook](https://github.com/vahalla-wealth/vahalla-web/blob/e08e9a7a93f3d05716fbc588be90b659576b6b0e/src/hooks/useNotificationSubscription.ts), `src/services/graphql.ts`, `src/services/api/taskFiles.ts`, `src/graphql/queries/tasks.ts` |
| vahalla-wealth/vahalla-crm-service | `7b54c510b271d794d4ec99c905b7b587eb38d7db` | `cmd/server/main.go`, `graph/schema.graphqls`, `pkg/common/tracekit/gintrace/middleware_test.go` |
| vahalla-wealth/vahalla-task-service | `454591ee4976c12d9831bfe1d5ca6fa5a84099ea` | `cmd/server/main.go`, `graph/schemas/` |
| vahalla-wealth/vahalla-messaging-service | `8f3bbba90769884f3e7f8a9ca05a274024eb5def` | `cmd/server/main.go`, notification schema/resolvers |

Graph composes nine subgraphs using Federation 2.7.0: Identity, CRM, Task, Customer, Portfolio, Product, Messaging, Platform and Report. Its root Router config and chart copy matched at inspection. The deployed image before adoption remains a separate runtime check; these commits must be refreshed if consumers change before release.

## Feature contract and verification

| Actual usage | Risk to preserve | Verification in this PR | Staging adoption gate |
| --- | --- | --- | --- |
| Web queries/mutations POST JSON to `/query` with bearer authorization; error handlers inspect GraphQL codes | Preserve payloads, authentication headers, intended business errors and HTTP behavior | Existing fork/HTTP/auth suites; packaged authorized and denied operations; security-redaction backport controls | Real test-user read queries and invalid/expired token rejection; confirm expected error handling |
| Task queries resolve assignees, likers and attachment uploaders as federated Identity entities | A parallel-root query alone does not prove entity joins | Packaged synthetic Account entity resolves across two subgraphs; upstream Federation/Rhai/Supergraph tests | Read-only representative Task/Identity and other multi-service queries; recompose all nine actual source schemas |
| Task/CRM upload via multipart `operations`, `map`, file parts; Web sends `apollo-require-preflight` and bearer | File mapping/bytes, authorization, streaming and limits must survive | Packaged file upload, authorization denial, 5-file and 10-MiB boundaries; top-level upstream upload HTTP tests | Synthetic file with designated test entity/storage and cleanup; ingress limits; no real lead imports or business mutations without separate scope |
| Web notification hook uses HTTP `multipart/mixed;subscriptionSpec=1.0`; Router connects to subgraph WebSocket with `graphql_ws` config (wire subprotocol `graphql-transport-ws`) | Do not substitute a client-only WebSocket test for the actual Web transport; preserve token routing and event envelopes | Packaged HTTP-to-WebSocket bridge, event, completion, fresh connection and denied handshake; protocol/subgraph-service unit suites cover lifecycle paths | Test-user notification stream through ingress; abort/reconnect, no stale stream or cross-user events, no business notification broadcasts |
| Authorization, request/correlation IDs, `x-forwarded-for`, `x-real-ip` are forwarded; Go services consume trace context/audit client IP | Security patches must not drop audit context or create unrelated trace IDs | Actual packaged container captures both subgraphs and compares trace identities end-to-end; tests also omit inbound traceparent as Web does | Confirm real proxy chain/trusted-proxy handling and sanitized logs; collector delivery when tracing enabled |
| Prometheus, `/health`, CORS-exposed `x-trace-id`, shutdown and configurable OTLP | Preserve monitoring and termination; avoid exporting synthetic telemetry | Packaged endpoint/shutdown checks; existing telemetry suites; OTLP disabled in isolated test | Workload readiness, exact image/revision, metrics scraping and graceful rollout; live OTLP only when configured |

The upload integration filter selects top-level `integration::file_upload::it_` tests; the massive-file case remains upstream-ignored. Credential-gated GraphOS helpers are not counted as verified behavior. Upstream `ws_passthrough` integration cases marked `ROUTER-1793` are also ignored; no claim is made that those ran. The packaged notification fixture runs without GraphOS credentials and provides a separate actual-image transport check. Real service authorization and business behavior remain staging gates.

## Impact of the current fixes

The follow-up changes affect scan/report validation, test tooling and OCI metadata. They add no new application runtime patch. Existing Router/Rhai redaction backports continue to distinguish accidental internal errors from intended application errors. Earlier source/config inspection found no Rhai scripts in the three consumer chart trees; refresh that evidence before adoption. Other consumers using native-error catch strings must assess the upstream change to typed error objects.

Source summaries require the root Cargo inventory (including the Router package), well-formed finding severities and all six expected Dockerfile/Helm scan targets. The Trivy Cargo synthetic graph root has no package name/version and is handled explicitly; a graph root alone is invalid coverage. Configuration failure counts must agree with findings. Missing or malformed evidence removes a stale summary and fails CI, while valid zero findings remain allowed. This guards expected scan coverage; it does not prove that Trivy analyzes every lockfile entry, feature, dev dependency or application attack path. Findings remain raw and source/config/image totals remain separate.

Both candidate and release builds label the image with this fork's repository URL, exact built source revision and candidate/release version. Original Apollo authorship remains. CI verifies the labels on the actual image; a candidate label is not a published-release identity.

## Consumer warnings and release gates

- `headers.all.request` is auto-upgraded in 2.18.0 and emits a warning. Keep this old-shape fixture as a compatibility control. During Graph adoption, change the owning root/config chart copy to wrap rules under `operations`, then render each relevant environment. Do not fix only the mono root chart mirror.
- `apollo.router.session.count.active` is deprecated in favor of `http.server.active_requests`. The inspected local Observability source had no reference to either spelling; this does not prove absence from live/imported dashboards. Inspect the live dashboard/alert consumers before migration. Do not suppress the Router warning merely to make logs quiet.
- License configuration was absent from inspected consumer config/chart bindings. Check actual running environment/secret injection and supplied limits at adoption without printing keys; source absence alone cannot prove runtime absence.
- Before publication, review exact-head CI and final-image severity comparison. Then approve release separately. After publishing, require actual pushed-digest scans/SBOMs and anonymous native pulls. Preserve baseline digest/config for rollback, then open the Graph adoption PR and perform staging acceptance. SIT/UAT are config handoffs, with deployment/runtime validation owned by their normal deployment teams.
