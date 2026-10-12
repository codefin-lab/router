# VA-017 packaged-container contract test

`router.yaml` is a verbatim non-secret snapshot of `vahalla-wealth/vahalla-graph/charts/graph/files/router.yaml` at `ad81e853091e8ac19dc8d24fbb94f0379c1c5317`. The application root config and chart copy matched when captured. Refresh deliberately when the consumer configuration changes.

The schema routes only to two synthetic HTTP subgraphs on an internal Docker network. No business requests or credentials are used. Runtime telemetry export is disabled. The synthetic client runs inside that network; no host ports are published. Fixtures are copied into temporary containers, without host filesystem mounts. The temporary network and containers are removed on success or failure.

This tests startup, health, multi-subgraph queries, header propagation, denied subgraph responses, metrics and graceful shutdown. It does not establish live staging, WebSocket subscriptions, uploads or OTLP collector acceptance. Those remain staging rollout checks. The Python mock image is test tooling, not part of the delivered Router image.
