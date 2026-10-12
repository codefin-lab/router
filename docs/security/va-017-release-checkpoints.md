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

The latest stable release observed was 2.18.0; 3.0.0-preview.0 is a prerelease. A stable-version check alone is insufficient: upstream development includes these relevant merged fixes, and the vulnerable error formatting still exists in this candidate.

| Upstream patch | Impact and recommendation | Checkpoint |
| --- | --- | --- |
| https://github.com/apollographql/router/pull/10048 (merged 2026-10-07, `0b05a321d84f3ae9866a44a4cb2ac89822ae4e9f`) | Redacts internal Supergraph errors while preserving HTTP 500 and INTERNAL_SERVER_ERROR; logs details server-side. Small production change plus regression fixture/test. Recommend evaluating a focused backport. | Not backported or claimed fixed yet; test client redaction, status/code, operator logs and telemetry. |
| https://github.com/apollographql/router/pull/10004 (merged 2026-10-08, `753be3054869aebc909f173ac207508441250d50`) | Redacts Rhai engine/function details. Changes caught function errors from strings to objects and removes wrappers from intentionally thrown messages. | Inspect consumer Rhai scripts and catch logic before backport; upstream includes extensive tests. Not backported or claimed fixed yet. |

These are information-disclosure fixes, not evidence that a specific scanner count will decrease. Do not assign CVEs or severity scores without an advisory. Do not import the whole development branch: it includes unrelated and potentially breaking work. Recheck stable releases, advisories and dependency fixes at the final release checkpoint.
