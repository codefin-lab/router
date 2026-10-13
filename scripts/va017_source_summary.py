"""Summarize source reports separately from delivered-image findings."""
import collections
import json
import os
from pathlib import Path
import sys


SEVERITIES = ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN')
REQUIRED_CONFIG = {
    'dockerfiles/Dockerfile.router': 'dockerfile',
    'dockerfiles/diy/dockerfiles/Dockerfile.repo': 'dockerfile',
    **{f'helm/chart/router/templates/{name}.yaml': 'helm'
       for name in ('configmap', 'deployment', 'service', 'serviceaccount')},
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_results(path):
    report = json.loads(path.read_text())
    require(isinstance(report, dict) and report.get('ArtifactType') == 'repository',
            f'{path.name}: expected repository report')
    results = report.get('Results')
    require(isinstance(results, list) and results and all(isinstance(r, dict) for r in results),
            f'{path.name}: missing or malformed Results')
    targets = [r.get('Target') for r in results]
    require(all(isinstance(t, str) and t for t in targets) and len(targets) == len(set(targets)),
            f'{path.name}: missing or duplicate targets')
    return results


def findings(result, field):
    entries = result.get(field)
    if entries is None:
        return []
    require(isinstance(entries, list), f'{result["Target"]}: malformed {field}')
    for entry in entries:
        require(isinstance(entry, dict) and entry.get('Severity') in SEVERITIES,
                f'{result["Target"]}: missing/unknown finding severity')
        keys = ('VulnerabilityID', 'PkgName') if field == 'Vulnerabilities' else ('ID',)
        require(all(isinstance(entry.get(k), str) and entry[k] for k in keys),
                f'{result["Target"]}: incomplete finding identity')
        if field == 'Misconfigurations':
            require(entry.get('Status') == 'FAIL', f'{result["Target"]}: unexpected check status')
    return entries


def dependency_counts(results):
    cargo = [r for r in results if r['Target'] == 'Cargo.lock'
             and r.get('Class') == 'lang-pkgs' and r.get('Type') == 'cargo']
    require(len(cargo) == 1, 'Missing root Cargo.lock coverage')
    counts = collections.Counter()
    for result in results:
        require(result.get('Class') == 'lang-pkgs', f'{result["Target"]}: wrong dependency class')
        packages = result.get('Packages')
        require(isinstance(packages, list) and packages, f'{result["Target"]}: missing package inventory')
        named = []
        for package in packages:
            require(isinstance(package, dict), f'{result["Target"]}: malformed package')
            # Trivy emits a Cargo dependency-graph root without Name/Version.
            if result.get('Type') == 'cargo' and package.get('Relationship') == 'root':
                require(bool(package.get('ID')) and package.get('AnalyzedBy') == 'cargo'
                        and isinstance(package.get('DependsOn'), list) and package['DependsOn']
                        and all(isinstance(d, str) and d for d in package['DependsOn']),
                        'Malformed Cargo graph root')
            else:
                require(all(isinstance(package.get(k), str) and package[k] for k in ('Name', 'Version')),
                        f'{result["Target"]}: incomplete package identity')
                named.append(package['Name'])
        require(named, f'{result["Target"]}: no named packages')
        if result is cargo[0]:
            require('apollo-router' in named, 'Root Cargo inventory does not include apollo-router')
        counts.update(e['Severity'] for e in findings(result, 'Vulnerabilities'))
    return counts


def configuration_counts(results):
    by_target = {r['Target']: r for r in results}
    for target, kind in REQUIRED_CONFIG.items():
        require(target in by_target and by_target[target].get('Type') == kind,
                f'Missing configuration coverage: {target}')
    counts = collections.Counter()
    for result in results:
        require(result.get('Class') == 'config', f'{result["Target"]}: wrong configuration class')
        summary = result.get('MisconfSummary')
        require(isinstance(summary, dict) and 'Successes' in summary and 'Failures' in summary
                and all(type(n) is int and n >= 0 for n in summary.values()) and sum(summary.values()) > 0,
                f'{result["Target"]}: missing/malformed check coverage')
        entries = findings(result, 'Misconfigurations')
        require(summary['Failures'] == len(entries), f'{result["Target"]}: failed findings are incomplete')
        counts.update(e['Severity'] for e in entries)
    return counts


def main():
    root = Path(sys.argv[1])
    (root / 'summary.md').unlink(missing_ok=True)
    # Validate every report before writing any successful summary.
    reports = [
        ('dependencies.json', dependency_counts(read_results(root / 'dependencies.json'))),
        ('configuration.json', configuration_counts(read_results(root / 'configuration.json'))),
    ]
    lines = ['## Source security report', '',
             'Report only: this does not approve an image release or close VA-017.', '',
             '| Report | Critical | High | Medium | Low | Unknown |',
             '| --- | ---: | ---: | ---: | ---: | ---: |']
    for filename, counts in reports:
        lines.append('| ' + filename + ' | ' + ' | '.join(str(counts[s]) for s in
                     SEVERITIES) + ' |')
    summary = '\n'.join(lines) + '\n'
    (root / 'summary.md').write_text(summary)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as output:
            output.write(summary)
    print(summary)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit(f'Invalid source evidence: {error}')
