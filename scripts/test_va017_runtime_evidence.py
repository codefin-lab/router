import copy
import unittest

from va017_runtime_evidence import validate_image, validate_trace


TRACE = '4bf92f3577b34da6a3ce929d0e0e4736'
PARENT = f'00-{TRACE}-00f067aa0ba902b7-01'
OBSERVATIONS = [
    {'path': '/left', 'headers': {'traceparent': f'00-{TRACE}-1111111111111111-01'}},
    {'path': '/right', 'headers': {'traceparent': f'00-{TRACE}-2222222222222222-01'}},
]


class RuntimeEvidenceTests(unittest.TestCase):
    def test_oci_identity_matches_fork_exact_source_and_version(self):
        labels = {
            'org.opencontainers.image.source': 'https://github.com/codefin-lab/router',
            'org.opencontainers.image.revision': 'a' * 40,
            'org.opencontainers.image.version': 'v2.18.0-open-r1',
            'org.opencontainers.image.authors': 'Apollo Graph, Inc. https://github.com/apollographql/router',
        }
        validate_image([{'Config': {'Labels': labels}}], 'a' * 40, 'v2.18.0-open-r1')
        for key in labels:
            wrong = {**labels, key: 'incorrect'}
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_image([{'Config': {'Labels': wrong}}], 'a' * 40, 'v2.18.0-open-r1')
        with self.assertRaises(ValueError):
            validate_image([{'Config': {'Labels': None}}], 'a' * 40, 'v2.18.0-open-r1')

    def test_inbound_parent_continues_with_new_subgraph_span_ids(self):
        self.assertEqual(validate_trace({'X-Trace-ID': TRACE}, OBSERVATIONS, PARENT), TRACE)

    def test_web_request_without_parent_mints_one_shared_trace(self):
        self.assertEqual(validate_trace({'x-trace-id': TRACE}, OBSERVATIONS), TRACE)

    def test_unrelated_response_trace_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_trace({'x-trace-id': 'a' * 32}, OBSERVATIONS, PARENT)

    def test_unrelated_trace_on_either_subgraph_is_rejected(self):
        for index in range(2):
            observations = copy.deepcopy(OBSERVATIONS)
            observations[index]['headers']['traceparent'] = '00-' + 'a' * 32 + '-1111111111111111-01'
            for incoming in [None, PARENT]:
                with self.subTest(index=index, incoming=incoming), self.assertRaises(ValueError):
                    validate_trace({'x-trace-id': TRACE}, observations, incoming)

    def test_missing_subgraph_or_invalid_w3c_identity_is_rejected(self):
        for observations in [[], OBSERVATIONS[:1], [OBSERVATIONS[0], OBSERVATIONS[0]]]:
            with self.subTest(observations=observations), self.assertRaises(ValueError):
                validate_trace({'x-trace-id': TRACE}, observations, PARENT)
        for value in ['', 'present-but-invalid', '00-' + '0' * 32 + '-1111111111111111-01',
                      f'00-{TRACE}-0000000000000000-01', f'00-{TRACE}-invalid-01']:
            observations = copy.deepcopy(OBSERVATIONS)
            observations[1]['headers']['traceparent'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_trace({'x-trace-id': TRACE}, observations, PARENT)

    def test_zero_or_missing_response_id_is_rejected(self):
        for headers in [{}, {'x-trace-id': '0' * 32}]:
            with self.subTest(headers=headers), self.assertRaises(ValueError):
                validate_trace(headers, OBSERVATIONS)


if __name__ == '__main__':
    unittest.main()
