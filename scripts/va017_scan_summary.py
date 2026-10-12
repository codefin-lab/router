"""Summarize unfiltered Trivy image reports; never infer remediation from missing data."""
import collections
import json
import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
severities = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN']
lines = ['# Candidate image scan', '', f"Architecture: {os.environ.get('SCAN_ARCH', 'unknown')}", '',
         'Report only; publication requires separate review. Counts are finding occurrences, not unique CVEs.', '',
         '| Image | Critical | High | Medium | Low | Unknown |', '| --- | ---: | ---: | ---: | ---: | ---: |']
reports = {}
coverage = {}
for label in ['baseline', 'candidate']:
    path = root / f'{label}.json'
    if not path.exists():
        if label == 'candidate':
            raise SystemExit('Missing candidate scan; cannot report success')
        continue
    data = json.loads(path.read_text())
    if 'Results' not in data or 'Metadata' not in data:
        raise SystemExit(f'Incomplete {label} scan')
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
