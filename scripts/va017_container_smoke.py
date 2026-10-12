"""Exercise the delivered image in an internal network with synthetic subgraphs."""
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid


def docker(*args, check=True, timeout=90):
    return subprocess.run(['docker', *args], check=check, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)


def main():
    image, output = sys.argv[1:]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'container-smoke.json').unlink(missing_ok=True)
    fixtures = Path(__file__).resolve().parent / 'va017-fixtures'
    suffix = uuid.uuid4().hex[:12]
    network, router, mock = [f'va017-{kind}-{suffix}' for kind in ('net', 'router', 'mock')]
    mock_image = 'python:3.13-alpine@sha256:2d9aefe2fef018a7eb2c13064c89c71929800fd2e5dccdbf52ea5da5bb8d929a'
    checks = []
    # Pull test tooling before creating the network. Runtime workloads have no external egress.
    if docker('image', 'inspect', mock_image, check=False).returncode:
        docker('pull', mock_image, timeout=180)
    docker('image', 'inspect', image)
    try:
        docker('network', 'create', '--internal', network)
        docker('create', '--pull=never', '--name', mock, '--network', network, '--network-alias', 'mock',
               mock_image, 'python', '/fixtures/mock.py')
        docker('create', '--pull=never', '--name', router, '--network', network, '--network-alias', 'router',
               '-e', 'APOLLO_TELEMETRY_DISABLED=true', '-e', 'ROUTER_TRACING_ENABLED=false',
               '-e', 'ROUTER_TRACING_SAMPLER=always_on', '-e', 'RUST_LOG=info',
               image, '--config', '/fixtures/router.yaml', '--supergraph', '/fixtures/supergraph.graphql')
        for name in (mock, router):
            docker('cp', str(fixtures), f'{name}:/fixtures')
            docker('start', name)
        def request(path, headers=None, data=None, port=4000):
            # Run the client inside the isolated network; no host ports or outbound routes.
            client = """import json,sys,urllib.request
url,headers,data=sys.argv[1:]
request=urllib.request.Request(url,headers=json.loads(headers),data=data.encode() if data else None)
with urllib.request.urlopen(request,timeout=5) as response:
 print(json.dumps({'status':response.status,'headers':dict(response.headers),'body':response.read().decode()}))
"""
            response = docker('exec', mock, 'python', '-c', client,
                              f'http://router:{port}{path}', json.dumps(headers or {}), data or '', timeout=15)
            return json.loads(response.stdout)

        for _ in range(60):
            try:
                assert request('/health')['status'] == 200
                break
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                if docker('inspect', router, '--format', '{{.State.Running}}').stdout.strip() != 'true':
                    raise RuntimeError('Router exited before readiness')
                time.sleep(1)
        else:
            raise RuntimeError('Router readiness timeout')
        checks.append('consumer config/schema startup and health')

        def query(authorized):
            headers = {'Content-Type': 'application/json', 'X-Request-ID': 'va017-test',
                       'X-Correlation-ID': 'va017-correlation',
                       'traceparent': '00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01'}
            if authorized:
                headers['Authorization'] = 'Bearer synthetic-va017'
            response = request('/query', headers, json.dumps({'query': 'query VA017Smoke { left right }'}))
            assert response['status'] == 200
            assert {k.lower(): v for k, v in response['headers'].items()}.get('x-trace-id'), 'missing response trace ID'
            return json.loads(response['body'])

        result = query(True)
        assert result.get('data') == {'left': 'left-ok', 'right': 'right-ok'} and not result.get('errors'), result
        checks.append('two-subgraph query; authorization/request/correlation/trace headers; response trace ID')
        result = query(False)
        assert result.get('errors') and all(
            e.get('extensions', {}).get('code') == 'UNAUTHENTICATED' for e in result['errors']), result
        assert not any((result.get('data') or {}).values()), result
        checks.append('subgraph access denial remains an error without successful data')
        assert '# TYPE' in request('/metrics', port=9090)['body']
        checks.append('Prometheus endpoint')
        docker('stop', '--time', '15', router, timeout=25)
        assert docker('inspect', router, '--format', '{{.State.ExitCode}}').stdout.strip() == '0'
        checks.append('graceful SIGTERM shutdown')
        (output / 'container-smoke.json').write_text(json.dumps({
            'image': image, 'status': 'passed', 'checks': checks,
            'limits': 'Synthetic HTTP subgraphs; not live staging, WebSocket or upload end-to-end acceptance.'}, indent=2) + '\n')
        print('\n'.join(checks))
    finally:
        for name in (router, mock):
            log = docker('logs', name, check=False).stdout
            (output / f'{"router" if name == router else "mock"}-smoke.log').write_text(log)
            docker('rm', '-f', name, check=False)
        docker('network', 'rm', network, check=False)


if __name__ == '__main__':
    main()
