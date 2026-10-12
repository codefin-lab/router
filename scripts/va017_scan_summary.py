"""Summarize unfiltered Trivy image reports; never infer remediation from missing data."""
import collections
import json
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
architecture = os.environ.get('SCAN_ARCH')
if architecture not in ('arm64', 'amd64'):
    raise SystemExit('SCAN_ARCH must be arm64 or amd64')
# Do not leave an earlier successful summary behind after a failed rerun.
(root / 'summary.md').unlink(missing_ok=True)
severities = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN']
lines = ['# Candidate image scan', '', f"Architecture: {os.environ.get('SCAN_ARCH', 'unknown')}", '',
         'Report only; publication requires separate review. Counts are finding occurrences, not unique CVEs.', '',
         '| Image | Critical | High | Medium | Low | Unknown |', '| --- | ---: | ---: | ---: | ---: | ---: |']
reports = {}
coverage = {}
for label in ['baseline', 'candidate']:
    path = root / f'{label}.json'
    if not path.exists():
        if label == 'candidate' or architecture == 'arm64':
            raise SystemExit(f'Missing {label} scan for {architecture}; cannot report success')
        continue
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get('ArtifactType') != 'container_image':
        raise SystemExit(f'Invalid {label} container image report')
    metadata = data.get('Metadata')
    results = data.get('Results')
    if (not isinstance(metadata, dict) or not isinstance(metadata.get('OS'), dict)
            or metadata['OS'].get('Family') != 'debian'
            or not isinstance(results, list) or not results
            or not all(isinstance(result, dict) for result in results)):
        raise SystemExit(f'Incomplete {label} Debian scan coverage')
    os_results = [r for r in results if r.get('Class') == 'os-pkgs' and r.get('Type') == 'debian']
    if not os_results or any(
        not isinstance(r.get('Packages'), list) or not r['Packages'] or any(
            not isinstance(p, dict) or not p.get('Name') or not p.get('Version')
            for p in r['Packages']) for r in os_results):
        raise SystemExit(f'Missing {label} Debian package inventory')
    for result in results:
        vulnerabilities = result.get('Vulnerabilities')
        if vulnerabilities is not None and (not isinstance(vulnerabilities, list) or any(
            not isinstance(v, dict) or not v.get('VulnerabilityID')
            or v.get('Severity', 'UNKNOWN') not in severities for v in vulnerabilities)):
            raise SystemExit(f'Invalid {label} vulnerability records')
    findings = [(result.get('Target', ''), v) for result in data['Results'] for v in (result.get('Vulnerabilities') or [])]
    reports[label] = findings
    coverage[label] = sorted({result.get('Type', 'unknown') for result in data['Results']})
    counts = collections.Counter(v.get('Severity', 'UNKNOWN') for _, v in findings)
    lines.append('| ' + label + ' | ' + ' | '.join(str(counts[s]) for s in severities) + ' |')
if 'baseline' not in reports:
    lines += ['', 'No baseline scan for this architecture; do not interpret absence as zero vulnerabilities.']
lines += ['', '## Scanner coverage', '']
for label, types in coverage.items():
    lines.append(f"- {label}: {', '.join(types) or 'no targets detected'}")
lines += ['', 'Image results alone do not establish Rust dependency coverage. Review the source Cargo.lock scan separately; absence of Rust findings here does not mean zero Rust vulnerabilities.']
lines += ['', '## Candidate Critical / High findings', '', '| Severity | CVE | Package | Installed | Fixed | Reference |', '| --- | --- | --- | --- | --- | --- |']
def cell(value):
    return str(value or '—').replace('|', '\\|').replace('\n', ' ')
for _, v in reports['candidate']:
    if v.get('Severity') in ['CRITICAL', 'HIGH']:
        lines.append('| ' + ' | '.join(cell(v.get(k)) for k in ['Severity', 'VulnerabilityID', 'PkgName', 'InstalledVersion', 'FixedVersion', 'PrimaryURL']) + ' |')
text = '\n'.join(lines) + '\n'
(root / 'summary.md').write_text(text)
if os.environ.get('GITHUB_STEP_SUMMARY'):
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as f:
        f.write(text)
print(text)
