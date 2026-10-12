# VA-017 Router 2.18.0 upgrade candidate

## Source identity

- Fork main before this change: `7abd7efa7152a312bc0deaf6f425d50015d987bd`.
- Imported fork baseline: upstream `7df4f9fd860ed8a3616f2bc828520586ae5f2909` (2026-05-09).
- Target: upstream v2.18.0, `7e2f87b5d07fbd129ee39120ce0b076a505940eb`.
- Candidate release name: `v2.18.0-open-r1`. No tag or image has been published.

The imported fork matches 4,014 upstream entries by path, mode and object ID;
only eight paths differ. Its version string says 2.14.0 but its source snapshot
is newer than the official v2.14.0 release tag. Apply the upstream delta from the
identified baseline, not from the version string alone.

## Merge and warning cleanup

The upstream source delta is applied with a three-way merge. Upstream workflow
changes are excluded: their release, auto-tag, repository-maintenance and image
cleanup automations are not appropriate to activate in this fork. Existing fork
workflows retain their history and reviewed Node 24 checkout action.

- Keep upstream 2.18.0 reload/retry state machine. Do not copy the old lifecycle
  file over the new implementation.
- Keep the fork's empty configuration/schema restriction lists and passthrough
  middleware. Existing NOTICE and README scope statements remain.
- Call upstream's new report enforcement API from lifecycle. This makes the
  report helpers active code again; deleting those methods merely to silence
  2.14 warnings would be incorrect.
- Remove unused HTTP middleware imports, unused expired-license constant,
  unused snapshot import and the unconstructed `SchemaRestriction::Spec`
  variant plus its unreachable match arm. Other variants and telemetry's
  short-message constant still have separate uses or upstream rationale.
- Move the preview rejection test to Connect v0.5. Preserve upstream acceptance
  of Connect v0.4.
- Align Rust toolchain, CI and source-build Dockerfile at 1.97.1.
- Pin fork CI/release runners to Ubuntu 24.04, the previously observed runner
  version, instead of implicitly adopting Ubuntu 26 through ubuntu-latest.

### Explicit behavior difference for review

Upstream's new `effective_license_unrestricted` preserves limits carried by an
active license. The old fork lifecycle forced `limits: None` for every license.
This candidate retains upstream's behavior and its parameterized tests. This is
not a claim of exact equivalence for deployments providing a limited license.
Before merge/adoption, establish whether the consumer supplies a license with
limits; inspect presence/metadata without printing license keys. An unlicensed
state still yields Licensed with no limits when no restricted features are
reported. No additional limits bypass is introduced in this upgrade.

## Validation and scanner boundaries

CI runs the four fork regressions, report/lifecycle/HTTP suites, preview-feature,
authentication, authorization, subscription and upload suites. Test discovery
must find each selected suite; an empty filter must not count as a pass.

`security-source.yml` pins Trivy 0.75.0 and action SHAs. It retains raw dependency
and infrastructure findings (including unfixed severities), source SBOM, scanner
and vulnerability database metadata, source commit, and a summary for 90 days.
Findings are report-only at this checkpoint; scanner execution errors still fail
the workflow. A green source-report job is not a release-security approval.

The configuration report includes upstream examples as well as delivered
configuration. Its counts must remain separate from the original container SCA
findings. A source SBOM is not a final-image SBOM.

Remaining release gates:

1. Successful candidate build/tests and review of the behavior difference above.
2. Build amd64/arm64 candidates, scan actual delivered digests and preserve SBOMs.
3. Compare old and new images using one scanner database snapshot; triage each
   residual finding with evidence and approved exceptions where needed.
4. Reconcile consumer `codefin/router` versus publisher `ghcr.io/codefin-lab/router`.
5. Review and approve promotion before release tags, consumer changes or staging
   rollout. SIT/UAT remain configuration handoffs for deployment owners.

This candidate must not be merged or tagged as a release until the relevant
checkpoint review is complete. Existing tag-triggered release is not invoked
by this PR.

## Local validation update

On macOS ARM64 with Rust 1.97.1, all 347 selected tests passed: license 36,
lifecycle 66, HTTP 6, preview gate 5, authentication 106, authorization 89,
subscription 12 and uploads 27. The four VA-017 regressions are included in
these counts. The permanent-rejection retry test uses the active preview gate
rather than the removed fork license restriction trigger; it passed.

The original Docker Hub index resolves to
`sha256:25e8351b8697ebdf674701b442a1a484f6e39d4f6ec0f13885ed84e9c6e08dd6`.
Its sole runnable image is arm64 manifest
`sha256:9a79fca41eae439c82e8feaa9a91639a9f8001a647e8516bb42409505eff4d71`;
the other manifest is an attestation. No amd64 baseline is claimed.
Candidate image scanning retains archives for 14 days and reports for 90 days.
All Trivy invocations share one explicit cache directory; baseline scanning
uses `--skip-db-update` to compare against the candidate's vulnerability DB.

## Initial Linux/image checkpoint (2026-10-12)

Head `4a43ecac586d8b6fb2633b5539ac89398c64287d` passed Linux build and
347 selected tests in [CI 38247866991](https://github.com/codefin-lab/router/actions/runs/38247866991).
The PR merge test commit is `c6eb6a2140932c660c5afbb5eadba93ab0805899`;
image artifacts record that exact source commit, image ID and archive checksum.
[Image scan 38247867063](https://github.com/codefin-lab/router/actions/runs/38247867063)
built and smoke-tested 2.18.0 on both native architectures:

| Image | Critical | High | Medium | Low | Unknown |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original arm64 | 6 | 66 | 145 | 109 | 8 |
| Initial candidate arm64 | 4 | 56 | 110 | 81 | 4 |
| Initial candidate amd64 (no old baseline) | 4 | 56 | 110 | 81 | 4 |

These are raw finding occurrences. Trivy detected only Debian targets in these
image reports, so this does not prove Rust libraries free from vulnerabilities.
The separate source scan reports C0/H4/M3/L3 dependencies and C0/H9/M4/L13
configuration findings. Rust dependency triage remains a release gate.

### Critical triage and immediate patch

Three Critical findings on installed `perl-base 5.36.0-7+deb12u3` have the
Bookworm security fix `5.36.0-7+deb12u4`:
- [CVE-2026-13221](https://security-tracker.debian.org/tracker/CVE-2026-13221)
- [CVE-2026-42496](https://security-tracker.debian.org/tracker/CVE-2026-42496)
- [CVE-2026-8376](https://security-tracker.debian.org/tracker/CVE-2026-8376)

The final image now explicitly upgrades perl-base through Debian's configured
repositories and fails the build below that security version. This permits a
newer security revision instead of requiring a retired exact package version.
A fresh build, version smoke test and scan must prove the reduction; these
initial counts are not the patched result. No Debian release mixing is used.

The fourth finding, [CVE-2023-45853](https://security-tracker.debian.org/tracker/CVE-2023-45853),
is reported on `zlib1g`. Debian marks Bookworm source zlib ignored because
contrib/minizip is not built in the affected binary packages. This supports
package-scoped not-affected review, not a global ignore for this CVE. Retain raw
findings and package inventory; separately consider bundled MiniZip copies.
No scanner suppression or accepted exception has been added.

### Compiler warning remediation

`proc-macro-error2 2.0.1` warns about private proc_macro re-export on Rust 1.97.1.
[RUSTSEC-2026-0173](https://rustsec.org/advisories/RUSTSEC-2026-0173) identifies
this crate as unmaintained with no patched release. The dependency path is oci-client -> oci-spec -> getset. The published
[getset 0.1.7](https://github.com/jbaublitz/getset/releases/tag/v0.1.7) removes
proc-macro-error2; a targeted lockfile update removes both proc-macro-error2
and proc-macro-error-attr2 without changing other dependencies. CI must confirm
compatibility and the absence of the warning. No lint suppression is used.

## Rust security patch checkpoint

Targeted Cargo.lock updates stay within the existing compatible release lines:

| Package | Before | Candidate |
| --- | --- | --- |
| hickory-resolver / net / proto | 0.26.1 | 0.26.3 |
| quinn-proto | 0.11.12 | 0.11.19 |
| quinn-udp | 0.5.13 | 0.5.16 |
| cmov | 0.5.3 | 0.5.4 |
| rand | 0.8.5 / 0.9.2 | 0.8.6 / 0.9.3 |

[Hickory 0.26.3](https://github.com/hickory-dns/hickory-dns/releases/tag/v0.26.3)
includes fixes for regressions in the minimum security release 0.26.2.
[Quinn 0.11.19](https://github.com/quinn-rs/quinn/releases/tag/quinn-proto-0.11.19)
also fixes subsequent stream-limit and Retry-token advisories. Supporting resolver
patches and rand_pcg are resolved by Cargo; no broad update was run.
CI additionally exercises DNS connector error mapping, HTTP client behavior and
telemetry reload configuration. A new source scan and both native image builds
must confirm this candidate; previous scan counts are not current acceptance.

OpenTelemetry SDK 0.31 has a Medium W3C baggage finding whose reported fix is
0.32.1. The Router uses a coupled 0.31 SDK/exporter ecosystem; do not replace
only the SDK with an incompatible 0.32 type graph. Baggage propagation is wired
in reload/tracing.rs when enabled. This remains unresolved pending coordinated
migration or a reviewed backport; do not claim non-applicability without consumer
configuration evidence. Legacy rand 0.7 also remains pending parent dependency
migration; no compatible 0.7 security patch is reported. No exception is approved.
