# VA-017 release checkpoints

Target: `ghcr.io/codefin-lab/router:v2.18.0-open-r1`. GHCR was selected by the owner on 2026-10-12. PR #3 remains a draft; merge, tag creation, publication and consumer rollout require the release checkpoint approval.

## Registry and public access

Anonymous GHCR token exchange and tags listing succeeded on 2026-10-12 for `codefin-lab/router` (existing `v2.14.0-open`, `latest`, `buildcache`). An anonymous full arm64 pull of `ghcr.io/codefin-lab/router:v2.14.0-open` also succeeded (returned digest `sha256:d9c796f2e49157f7d4ba7204250e3594e74ee29b8141cb16c9d21f909d3e62ac`). This proves public pull of the existing image, not availability of the future release. The current CLI token cannot read the package-management API (missing `read:packages` scope); no visibility setting was changed.

The release workflow builds natively for amd64 and arm64, scans the pushed platform digests, retains SBOM and raw reports, and assembles only those digests into the version index. Fresh native runners then pull that exact index with an empty Docker credential configuration, check architecture and execute `--version`. Both anonymous-pull jobs must pass before consumer promotion. There is no login step or package permission in those jobs. A failure blocks release acceptance; do not solve it by adding consumer credentials. Check package visibility and access instead. No `latest` tag is updated.

GitHub documents anonymous access for public container packages: https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility

## Review gates

1. PR source tests and both candidate image scans pass at the reviewed commit. Factory-level HTTP-header tests cover baggage enabled/disabled, 8192/8193 bytes, 64/65 members and preservation of trace context.
2. Resolve upstream backport decisions below and review compatibility with actual consumer configuration. SIT/UAT changes are configuration preparation only; runtime testing is staging-only.
3. Before approving publication, include the previous image versus candidate Critical/High/Medium/Low/Unknown comparison in PR #3, with immutable identities, scanner/database timestamps and coverage limits. Existing Docker Hub baseline has only an arm64 runnable manifest; do not invent an amd64 comparison. Image scanning covers Debian packages; source dependency scanning remains required for Rust.
4. After approved publication, review scans of the actual pushed digests, anonymous pull results for both architectures and the final index digest. Update the PR evidence before consumer promotion. Report-only scan success is not acceptance of remaining findings.
5. Open consumer changes separately, validate staging and retain rollback digests. Do not claim SIT/UAT runtime acceptance.

## Upstream review: additional fixes after 2.18.0

The latest stable release observed was 2.18.0; 3.0.0-preview.0 is a prerelease. A stable-version check alone is insufficient: upstream development includes these relevant merged fixes, and two relevant error-disclosure fixes were selected for focused backport with their upstream tests.

| Upstream patch | Impact and recommendation | Checkpoint |
| --- | --- | --- |
| https://github.com/apollographql/router/pull/10048 (merged 2026-10-07, `0b05a321d84f3ae9866a44a4cb2ac89822ae4e9f`) | Redacts internal Supergraph errors while preserving HTTP 500 and INTERNAL_SERVER_ERROR; logs details server-side. Focused backport includes the upstream production change and regression fixture/test. | Backported; validation must cover client redaction, status/code, operator logs and telemetry before acceptance. |
| https://github.com/apollographql/router/pull/10004 (merged 2026-10-08, `753be3054869aebc909f173ac207508441250d50`) | Redacts Rhai engine/function details. Changes caught function errors from strings to objects and removes wrappers from intentionally thrown messages. | Backported with upstream regression tests. No Rhai configuration or .rhai files were found in the three consumer chart trees; the live staging router ConfigMap also has no Rhai configuration. Catch-object compatibility change remains documented for other image consumers. |

These are information-disclosure fixes, not evidence that a specific scanner count will decrease. Do not assign CVEs or severity scores without an advisory. Do not import the whole development branch: it includes unrelated and potentially breaking work. Recheck stable releases, advisories and dependency fixes at the final release checkpoint.

## Application compatibility verification

Source review covered `vahalla-wealth/vahalla-graph/charts`, `vahalla-cwms/cwms-graph/charts`, and `vahalla-cwms/cwms-deployment-uat/charts/graph`. A read-only check of staging `graph-router-config` found neither a Rhai configuration block nor a license configuration block. This is configuration evidence, not proof of the candidate running in staging.

The focused backports retain successful GraphQL processing, explicit application error bodies/status codes and the Supergraph response path used by plugins/telemetry. Raw internal errors are replaced with generic client messages, with diagnostics logged server-side. Rhai intentional string throws lose the engine wrapper; caught native-function errors become typed objects. Consumers that enable Rhai must review string comparisons/methods in catch blocks.

CI now includes the complete Rhai and Supergraph library suites, the upstream planner-error HTTP regression, Rhai error-redaction HTTP tests, cancellation/batching compatibility tests and a successful Federation 2 query control. Existing fork/license/state-machine/authentication/authorization/subscription/upload/DNS/HTTP/telemetry checks remain enabled. The upstream regression tests use local fixtures and mocks; they do not invoke business mutations on staging.

## Public Router advisories at the v2.18.0 baseline

The five Apollo Router advisories published 2026-07-21 identify patched Router versions at or before 2.16.1; v2.18.0 is later than those fixed versions. This is release-range evidence, not a substitute for the final source/image scans or application configuration review.

| Advisory | Published severity | Upstream patched version | v2.18.0 relation |
| --- | --- | --- | --- |
| [GHSA-6p7q-4gq4-4vf7](https://github.com/apollographql/router/security/advisories/GHSA-6p7q-4gq4-4vf7) | Moderate | 2.16.1+ | Included by version range |
| [GHSA-8j6q-96xg-96rr](https://github.com/apollographql/router/security/advisories/GHSA-8j6q-96xg-96rr) | Moderate | 2.16.1 | Included by version range |
| [GHSA-69r6-7hv4-h9f2](https://github.com/apollographql/router/security/advisories/GHSA-69r6-7hv4-h9f2) | Moderate | 2.16.1 | Included by version range |
| [GHSA-m5q4-q9rr-m3vr](https://github.com/apollographql/router/security/advisories/GHSA-m5q4-q9rr-m3vr) | High | 2.16.1 | Included by version range |
| [GHSA-gr6h-4wpf-xp52](https://github.com/apollographql/router/security/advisories/GHSA-gr6h-4wpf-xp52) | High | 2.16.1+ | Included by version range |

No newer public advisory was returned by the upstream repository advisory list on 2026-10-12. The two post-2.18.0 upstream fixes backported above are security-relevant information-disclosure changes without a matching new GHSA/CVE in that list. They may not change dependency-scanner severity counts; record them as source behavior remediations and avoid claiming a numerical severity reduction from them.

## Release recovery and candidate functional checks (2026-10-13)

- Serialize all releases in this repository. Before publication require all version/platform tags to return GHCR `MANIFEST_UNKNOWN`; authorization, rate-limit, network and other registry failures stop publication. Check the final version again before assembly.
- Never rerun publication jobs: matrix builds and final assembly reject `GITHUB_RUN_ATTEMPT > 1`. Preserve partial platform tags and evidence, fix the cause, and obtain release approval for a new revision tag (`r2`, etc.). Do not delete/repoint an existing release tag. A failed public-pull job can be rerun alone against the same assembled digest after investigating access/connectivity; it must not rebuild or replace the published image.
- These controls protect this workflow; GHCR writers outside it must follow the same policy. Consumers must retain immutable digests rather than depend on tag immutability alone.
- Candidate and published platform images run the isolated packaged-container contract test described in `scripts/va017-fixtures/README.md`. Config parsing, readiness, two-subgraph queries, synthetic auth/header propagation, denial behavior, metrics and SIGTERM are checked. Source suites retain subscription/upload coverage; their application end-to-end verification remains staging-only.
- Scan summaries fail if expected Debian OS/package coverage is absent or malformed, or if the arm64 baseline is missing. Complete package coverage with genuinely no findings is still valid. Negative tests protect this distinction; no CVEs are suppressed.

### Consumer configuration warning discovered by the packaged test

The captured Graph configuration starts successfully on 2.18.0 and passes header propagation, but emits an automatic configuration-upgrade warning: `headers.all.request` now wraps its rules under `operations`. Update the owning Graph config and chart copy in the consumer adoption PR and verify rendered staging/SIT/UAT configuration. Keep the old-shape fixture here as an explicit backward-compatibility control. This warning is not a failed query and is not fixed by changing only the base image.
