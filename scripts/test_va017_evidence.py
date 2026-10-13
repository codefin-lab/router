import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

import va017_release_guard as guard

REPORT = {'ArtifactType': 'container_image', 'Metadata': {'OS': {'Family': 'debian'}},
          'Results': [{'Class': 'os-pkgs', 'Type': 'debian', 'Target': 'Debian 12',
                       'Packages': [{'Name': 'libc6', 'Version': '2.36'}]}]}


class ScanEvidenceTests(unittest.TestCase):
    def summarize(self, report, arch='amd64', baseline=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'candidate.json').write_text(json.dumps(report))
            (root / 'summary.md').write_text('stale success')
            if baseline:
                (root / 'baseline.json').write_text(json.dumps(REPORT))
            env = {**os.environ, 'SCAN_ARCH': arch}
            env.pop('GITHUB_STEP_SUMMARY', None)
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('va017_scan_summary.py')), directory],
                                    env=env, capture_output=True, text=True)
            summary = (root / 'summary.md').read_text() if (root / 'summary.md').exists() else ''
            return result.returncode, summary

    def test_complete_clean_inventory_is_legitimate_zero(self):
        code, summary = self.summarize(REPORT)
        self.assertEqual(code, 0)
        self.assertIn('| candidate | 0 | 0 | 0 | 0 | 0 |', summary)
        self.assertIn('No baseline scan for this architecture', summary)

    def test_arm64_requires_baseline(self):
        self.assertEqual(self.summarize(REPORT, 'arm64')[1], '')
        self.assertNotEqual(self.summarize(REPORT, 'arm64')[0], 0)
        self.assertEqual(self.summarize(REPORT, 'arm64', baseline=True)[0], 0)

    def test_missing_or_wrong_coverage_fails_without_stale_summary(self):
        malformed = [{}, {'Results': [], 'Metadata': {}},
                     {**REPORT, 'Results': []}, {**REPORT, 'Results': None},
                     {**REPORT, 'Metadata': {'OS': {'Family': 'alpine'}}}]
        for packages in (None, [], [{}], [{'Name': 'libc6'}]):
            report = copy.deepcopy(REPORT)
            report['Results'][0]['Packages'] = packages
            malformed.append(report)
        for report in malformed:
            with self.subTest(report=report):
                code, summary = self.summarize(report)
                self.assertNotEqual(code, 0)
                self.assertEqual(summary, '')

    def test_findings_are_not_suppressed(self):
        report = copy.deepcopy(REPORT)
        report['Results'][0]['Vulnerabilities'] = [
            {'VulnerabilityID': f'TEST-{severity}', 'Severity': severity, 'PkgName': 'libc6'}
            for severity in ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN')]
        code, summary = self.summarize(report)
        self.assertEqual(code, 0)
        self.assertIn('| candidate | 1 | 1 | 1 | 1 | 1 |', summary)

    def test_invalid_severity_fails(self):
        report = copy.deepcopy(REPORT)
        report['Results'][0]['Vulnerabilities'] = [{'VulnerabilityID': 'TEST', 'Severity': 'typo'}]
        self.assertNotEqual(self.summarize(report)[0], 0)


class ReleaseGuardTests(unittest.TestCase):
    def http_error(self, status, body):
        return urllib.error.HTTPError('https://ghcr.io/test', status, 'test', {}, io.BytesIO(json.dumps(body).encode()))

    def test_only_manifest_unknown_is_absent(self):
        with patch.object(guard.urllib.request, 'urlopen', side_effect=self.http_error(
                404, {'errors': [{'code': 'MANIFEST_UNKNOWN'}]})):
            guard.require_absent('v2.18.0-open-r1', 'synthetic')

    def test_existing_manifest_blocks_overwrite(self):
        with patch.object(guard.urllib.request, 'urlopen'):
            with self.assertRaisesRegex(RuntimeError, 'overwrite'):
                guard.require_absent('v2.18.0-open-r1', 'synthetic')

    def test_registry_failures_are_not_absence(self):
        for status, code in [(401, 'UNAUTHORIZED'), (403, 'DENIED'), (429, 'TOOMANYREQUESTS'),
                             (500, 'UNKNOWN'), (404, 'NAME_UNKNOWN')]:
            with self.subTest(status=status), patch.object(guard.urllib.request, 'urlopen',
                    side_effect=self.http_error(status, {'errors': [{'code': code}]})):
                with self.assertRaises(RuntimeError):
                    guard.require_absent('v2.18.0-open-r1', 'synthetic')

    def test_all_names_checked_before_publication(self):
        for extra, expected in [([], 3), (['--index-only'], 1)]:
            with patch.object(sys, 'argv', ['guard', 'v2.18.0-open-r1', *extra]), patch.dict(os.environ, {'GITHUB_RUN_ATTEMPT': '1'}), patch.object(guard.urllib.request, 'urlopen') as network, patch.object(guard, 'require_absent') as absent:
                network.return_value.__enter__.return_value.read.return_value = b'{"token":"synthetic"}'
                guard.main()
                self.assertEqual(absent.call_count, expected)
                self.assertEqual(absent.call_args_list[0].args[0], 'v2.18.0-open-r1')

    def test_unexpected_release_version_is_rejected(self):
        with patch.object(sys, 'argv', ['guard', 'v2.19.0-open-r1']), patch.object(guard.urllib.request, 'urlopen') as network:
            with self.assertRaises(SystemExit):
                guard.main()
            network.assert_not_called()

    def test_rerun_rejected_before_network(self):
        with patch.object(sys, 'argv', ['guard', 'v2.18.0-open-r1']), patch.dict(os.environ, {'GITHUB_RUN_ATTEMPT': '2'}), patch.object(guard.urllib.request, 'urlopen') as network:
            with self.assertRaises(SystemExit):
                guard.main()
            network.assert_not_called()


if __name__ == '__main__':
    unittest.main()
