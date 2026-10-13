"""Read-only GHCR preflight. Only a confirmed missing manifest permits publication."""
import json
import os
import re
import sys
import urllib.error
import urllib.request

REPOSITORY = 'codefin-lab/router'
ACCEPT = ', '.join([
    'application/vnd.oci.image.index.v1+json',
    'application/vnd.oci.image.manifest.v1+json',
    'application/vnd.docker.distribution.manifest.list.v2+json',
    'application/vnd.docker.distribution.manifest.v2+json',
])


def require_absent(tag, token):
    request = urllib.request.Request(
        f'https://ghcr.io/v2/{REPOSITORY}/manifests/{tag}',
        headers={'Authorization': f'Bearer {token}', 'Accept': ACCEPT})
    try:
        with urllib.request.urlopen(request, timeout=30):
            raise RuntimeError(f'Refusing to overwrite existing image tag: {tag}')
    except urllib.error.HTTPError as error:
        try:
            if error.code == 404:
                body = json.loads(error.read())
                errors = body.get('errors', [])
                if errors and all(e.get('code') == 'MANIFEST_UNKNOWN' for e in errors):
                    return
            raise RuntimeError(f'Cannot establish tag absence: {tag} (HTTP {error.code})') from error
        finally:
            error.close()


def main():
    tag = sys.argv[1]
    if not re.fullmatch(r'v2\.18\.0-open-r[1-9][0-9]*', tag):
        raise SystemExit('Expected v2.18.0-open-rN; this workflow is specific to Router 2.18.0')
    if os.environ.get('GITHUB_RUN_ATTEMPT') != '1':
        raise SystemExit('Release reruns are disabled. Preserve partial evidence and use a new revision tag.')
    with urllib.request.urlopen(
            f'https://ghcr.io/token?service=ghcr.io&scope=repository:{REPOSITORY}:pull',
            timeout=30) as response:
        token = json.load(response)['token']
    # Check every public release name before any platform is published.
    suffixes = ('',) if sys.argv[2:] == ['--index-only'] else ('', '-amd64', '-arm64')
    for suffix in suffixes:
        require_absent(tag + suffix, token)
    print(f'All release tags are absent: {tag}')


if __name__ == '__main__':
    main()
