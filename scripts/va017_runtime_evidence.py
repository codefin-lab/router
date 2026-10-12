"""Validate evidence collected from the actual packaged Router."""
import json
from pathlib import Path
import re
import sys


def require(condition, message):
    if not condition:
        raise ValueError(message)


def trace_id(traceparent):
    match = re.fullmatch(r'00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})', traceparent or '')
    require(match is not None, 'malformed W3C traceparent')
    require(int(match[1], 16) != 0 and int(match[2], 16) != 0, 'zero W3C trace or span ID')
    return match[1]


def validate_trace(response_headers, observations, incoming=None):
    headers = {k.lower(): v for k, v in response_headers.items()}
    response_id = headers.get('x-trace-id', '')
    require(re.fullmatch('[0-9a-f]{32}', response_id) is not None and int(response_id, 16) != 0,
            'missing or invalid response trace ID')
    require(len(observations) == 2 and {o['path'] for o in observations} == {'/left', '/right'},
            'missing or duplicate subgraph observations')
    expected = trace_id(incoming) if incoming is not None else response_id
    require(response_id == expected, 'client response trace ID changed')
    for observation in observations:
        require(trace_id(observation['headers'].get('traceparent')) == expected,
                f'{observation["path"]}: subgraph trace ID changed')
    # Span IDs legitimately differ at each hop; compare only the trace identity.
    return expected


def validate_image(inspection, revision, version):
    require(re.fullmatch('[0-9a-f]{40}', revision) is not None, 'invalid source revision')
    require(isinstance(inspection, list) and len(inspection) == 1, 'expected one inspected image')
    labels = inspection[0].get('Config', {}).get('Labels') or {}
    for key, expected in {
        'source': 'https://github.com/codefin-lab/router',
        'revision': revision,
        'version': version,
    }.items():
        require(labels.get(f'org.opencontainers.image.{key}') == expected, f'wrong OCI {key}')
    require('Apollo Graph' in labels.get('org.opencontainers.image.authors', ''),
            'missing upstream attribution')


if __name__ == '__main__':
    path, revision, version = sys.argv[1:]
    validate_image(json.loads(Path(path).read_text()), revision, version)
