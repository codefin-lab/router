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
