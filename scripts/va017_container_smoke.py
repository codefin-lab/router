"""Exercise the delivered image in an internal network with synthetic subgraphs."""
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

from va017_runtime_evidence import validate_trace


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
    traces = []
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
        def request(path, headers=None, data=None, port=4000, host='router'):
            # Run the client inside the isolated network; no host ports or outbound routes.
            client = """import json,sys,urllib.request
url,headers,data=sys.argv[1:]
request=urllib.request.Request(url,headers=json.loads(headers),data=data.encode() if data else None)
with urllib.request.urlopen(request,timeout=5) as response:
 print(json.dumps({'status':response.status,'headers':dict(response.headers),'body':response.read().decode()}))
"""
            response = docker('exec', mock, 'python', '-c', client,
                              f'http://{host}:{port}{path}', json.dumps(headers or {}), data or '', timeout=15)
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

        def query(authorized, parent=True, entity=False):
            request_id = 'va017-' + uuid.uuid4().hex
            headers = {'Content-Type': 'application/json', 'X-Request-ID': request_id,
                       'X-Correlation-ID': 'va017-correlation',
                       'X-Forwarded-For': '192.0.2.10, 192.0.2.20', 'X-Real-IP': '192.0.2.10',
                       'Origin': 'https://synthetic.invalid'}
            if parent:
                headers['traceparent'] = '00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01'
            if authorized:
                headers['Authorization'] = 'Bearer synthetic-va017'
            operation = 'query VA017Entity { account { id label } }' if entity else 'query VA017Smoke { left right }'
            response = request('/query', headers, json.dumps({'query': operation}))
            assert response['status'] == 200
            observations = json.loads(request(f'/observations/{request_id}', host='mock', port=8080)['body'])
            identifier = validate_trace(response['headers'], observations, headers.get('traceparent'))
            for observation in observations:
                for key in ('Authorization', 'X-Request-ID', 'X-Correlation-ID', 'X-Forwarded-For', 'X-Real-IP'):
                    assert observation['headers'].get(key.lower()) == headers.get(key), f'{key} changed'
            response_headers = {k.lower(): v for k, v in response['headers'].items()}
            assert 'x-trace-id' in response_headers.get('access-control-expose-headers', '').lower()
            traces.append({'incoming': headers.get('traceparent'), 'response_trace_id': identifier,
                           'subgraphs': [{'path': o['path'], 'traceparent': o['headers']['traceparent']}
                                         for o in observations]})
            return json.loads(response['body'])

        result = query(True)
        assert result.get('data') == {'left': 'left-ok', 'right': 'right-ok'} and not result.get('errors'), result
        checks.append('two-subgraph query; auth/correlation/audit headers; exact W3C trace continuity and CORS exposure')
        result = query(True, parent=False)
        assert result.get('data') == {'left': 'left-ok', 'right': 'right-ok'} and not result.get('errors'), result
        checks.append('Web request without traceparent: one generated trace across both subgraphs and response')
        result = query(True, entity=True)
        assert result.get('data') == {'account': {'id': 'synthetic-1', 'label': 'account-ok'}} and not result.get('errors'), result
        checks.append('federated entity lookup with auth, audit headers and trace continuity')
        result = query(False)
        assert result.get('errors') and all(
            e.get('extensions', {}).get('code') == 'UNAUTHENTICATED' for e in result['errors']), result
        assert not any((result.get('data') or {}).values()), result
        checks.append('subgraph access denial remains an error without successful data')
        browser_checks = docker('exec', mock, 'python', '/fixtures/browser_flows.py', check=False, timeout=90)
        (output / 'browser-flows.log').write_text(browser_checks.stdout)
        browser_checks.check_returncode()
        checks.extend(json.loads(browser_checks.stdout))
        assert '# TYPE' in request('/metrics', port=9090)['body']
        checks.append('Prometheus endpoint')
        docker('stop', '--time', '15', router, timeout=25)
        assert docker('inspect', router, '--format', '{{.State.ExitCode}}').stdout.strip() == '0'
        checks.append('graceful SIGTERM shutdown')
        (output / 'container-smoke.json').write_text(json.dumps({
            'image': image, 'status': 'passed', 'checks': checks, 'traces': traces,
            'limits': 'Synthetic subgraphs and browser transports; not live Vahalla staging, real JWT/RBAC, ingress, OTLP or business-data acceptance.'}, indent=2) + '\n')
        print('\n'.join(checks))
    finally:
        for name in (router, mock):
            log = docker('logs', name, check=False).stdout
            (output / f'{"router" if name == router else "mock"}-smoke.log').write_text(log)
            docker('rm', '-f', name, check=False)
        docker('network', 'rm', network, check=False)


if __name__ == '__main__':
    main()
