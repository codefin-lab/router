import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


DEPENDENCIES = {'ArtifactType': 'repository', 'Results': [{
    'Target': 'Cargo.lock', 'Class': 'lang-pkgs', 'Type': 'cargo',
    'Packages': [
        {'ID': 'synthetic-root', 'Relationship': 'root', 'AnalyzedBy': 'cargo',
         'DependsOn': ['apollo-router@2.18.0']},
        {'Name': 'apollo-router', 'Version': '2.18.0', 'Relationship': 'workspace'},
        {'Name': 'opentelemetry_sdk', 'Version': '0.31.0', 'Relationship': 'direct'},
    ],
}]}
CONFIGURATION = {'ArtifactType': 'repository', 'Results': [
    {'Target': target, 'Class': 'config', 'Type': kind,
     'MisconfSummary': {'Successes': 1, 'Failures': 0}}
    for target, kind in [
        ('dockerfiles/Dockerfile.router', 'dockerfile'),
        ('dockerfiles/diy/dockerfiles/Dockerfile.repo', 'dockerfile'),
        ('helm/chart/router/templates/configmap.yaml', 'helm'),
        ('helm/chart/router/templates/deployment.yaml', 'helm'),
        ('helm/chart/router/templates/service.yaml', 'helm'),
        ('helm/chart/router/templates/serviceaccount.yaml', 'helm'),
    ]
]}


class SourceEvidenceTests(unittest.TestCase):
    def summarize(self, dependencies=DEPENDENCIES, configuration=CONFIGURATION):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, report in [('dependencies', dependencies), ('configuration', configuration)]:
                if report is not None:
                    (root / f'{name}.json').write_text(json.dumps(report))
            (root / 'summary.md').write_text('stale success')
            env = dict(os.environ)
            env.pop('GITHUB_STEP_SUMMARY', None)
            result = subprocess.run([sys.executable, str(Path(__file__).with_name(
                'va017_source_summary.py')), directory], env=env, capture_output=True, text=True)
            summary = (root / 'summary.md').read_text() if (root / 'summary.md').exists() else ''
            return result.returncode, summary

    def assert_rejected(self, **reports):
        code, summary = self.summarize(**reports)
        self.assertNotEqual(code, 0)
        self.assertEqual(summary, '')

    def test_real_inventory_without_findings_is_valid_zero(self):
        code, summary = self.summarize()
        self.assertEqual(code, 0)
        self.assertIn('| dependencies.json | 0 | 0 | 0 | 0 | 0 |', summary)
        self.assertIn('| configuration.json | 0 | 0 | 0 | 0 | 0 |', summary)

    def test_missing_empty_or_wrong_reports_remove_stale_success(self):
        for name in ['dependencies', 'configuration']:
            for report in [None, {}, [], {'Results': None},
                           {'ArtifactType': 'repository', 'Results': []},
                           {'ArtifactType': 'container_image', 'Results': [{}]}]:
                with self.subTest(name=name, report=report):
                    self.assert_rejected(**{name: report})

    def test_cargo_root_and_named_inventory_are_required(self):
        for packages in [[], None, [{}], [{'Name': 'apollo-router'}],
                         [DEPENDENCIES['Results'][0]['Packages'][0]]]:
            report = copy.deepcopy(DEPENDENCIES)
            report['Results'][0]['Packages'] = packages
            with self.subTest(packages=packages):
                self.assert_rejected(dependencies=report)
        for field, value in [('Target', 'example/Cargo.lock'), ('Type', 'npm'),
                             ('Class', 'config')]:
            report = copy.deepcopy(DEPENDENCIES)
            report['Results'][0][field] = value
            with self.subTest(field=field):
                self.assert_rejected(dependencies=report)

    def test_each_required_config_target_must_be_scanned(self):
        for index in range(len(CONFIGURATION['Results'])):
            report = copy.deepcopy(CONFIGURATION)
            del report['Results'][index]
            with self.subTest(index=index):
                self.assert_rejected(configuration=report)

    def test_invalid_check_summary_or_missing_failed_findings_is_rejected(self):
        for summary in [None, {}, {'Successes': 0, 'Failures': 0},
                        {'Successes': -1, 'Failures': 0},
                        {'Successes': '1', 'Failures': 0},
                        {'Successes': True, 'Failures': 0},
                        {'Successes': 1, 'Failures': 1}]:
            report = copy.deepcopy(CONFIGURATION)
            report['Results'][0]['MisconfSummary'] = summary
            with self.subTest(summary=summary):
                self.assert_rejected(configuration=report)

    def test_every_raw_severity_is_counted_separately(self):
        deps, config = copy.deepcopy(DEPENDENCIES), copy.deepcopy(CONFIGURATION)
        for field, report in [('Vulnerabilities', deps), ('Misconfigurations', config)]:
            report['Results'][0][field] = [
                {'Severity': severity, 'VulnerabilityID': f'CVE-TEST-{severity}',
                 'PkgName': 'opentelemetry_sdk', 'ID': f'TEST-{severity}', 'Status': 'FAIL'}
                for severity in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN']]
        config['Results'][0]['MisconfSummary']['Failures'] = 5
        code, summary = self.summarize(deps, config)
        self.assertEqual(code, 0)
        for name in ['dependencies', 'configuration']:
            self.assertIn(f'| {name}.json | 1 | 1 | 1 | 1 | 1 |', summary)

    def test_bad_finding_cannot_disappear_from_counts(self):
        for field, name, fixture in [('Vulnerabilities', 'dependencies', DEPENDENCIES),
                                     ('Misconfigurations', 'configuration', CONFIGURATION)]:
            for findings in [{}, ['invalid'], [{'Severity': 'typo'}],
                             [{'Severity': 'HIGH'}]]:
                report = copy.deepcopy(fixture)
                report['Results'][0][field] = findings
                with self.subTest(name=name, findings=findings):
                    self.assert_rejected(**{name: report})


if __name__ == '__main__':
    unittest.main()
