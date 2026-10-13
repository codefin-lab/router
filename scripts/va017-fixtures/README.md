# VA-017 packaged-container contract test

`router.yaml` is a verbatim non-secret snapshot of `vahalla-wealth/vahalla-graph/charts/graph/files/router.yaml` at `ad81e853091e8ac19dc8d24fbb94f0379c1c5317`. The application root config and chart copy matched when captured. Refresh deliberately when the consumer configuration changes.

The schema routes only to two synthetic subgraphs on an internal Docker network. No business requests or credentials are used. Runtime telemetry export is disabled. The synthetic client runs inside that network; no host ports are published. Fixtures are copied into temporary containers, without host filesystem mounts. The temporary network and containers are removed on success or failure. The mock accepts only the bounded HTTP and WebSocket exchanges used in this test; it is not a general GraphQL/WebSocket server.

The tests exercise these source-derived Vahalla contracts:

- Startup/health with the captured configuration; parallel root queries and an entity lookup spanning both subgraphs.
- Authorization, request/correlation IDs and audit IP headers reach both subgraphs; access denial remains an error without successful data.
- The incoming W3C **trace ID** equals both subgraph trace IDs and response `x-trace-id`. Span IDs may legitimately change. A Web-like request without traceparent must produce one valid shared trace. The response exposes the trace header through CORS.
- Web-style multipart upload with bearer authorization and `apollo-require-preflight`, preserving filename/content. Missing authorization, six files and a file one byte larger than 10 MiB are rejected.
- Web-style HTTP `multipart/mixed;subscriptionSpec=1.0` notification stream bridged to a `graphql-transport-ws` subgraph (`graphql_ws` in Router config): event payload, server completion, new connection and denied subgraph handshake. Emit only after the HTTP stream opens to avoid a subscription-attachment race.
- Prometheus endpoint and graceful SIGTERM.

`container-smoke.json` retains the passed checks and trace continuity observations; `browser-flows.log` retains browser-transport failures. Separate negative unit tests reject unrelated, invalid, missing or zero trace identities and missing subgraph observations. OCI label validation checks the fork URL, exact built source SHA and version, retaining Apollo authorship.

This does not establish real JWT/RBAC, Web UI state, ingress proxy buffering/timeouts, live cancellation/reconnect behavior under load, OTLP collector delivery or business-data acceptance. Those remain staging rollout checks. The Python mock image is test tooling, not part of the delivered Router image. See the [consumer source assessment](../../docs/va-017/consumer-compatibility.md) for evidence and ownership.
