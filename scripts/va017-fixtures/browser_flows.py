"""Synthetic equivalents of Web's upload and notification HTTP transports."""
from email.parser import BytesParser
from email.policy import default
import json
import urllib.error
import urllib.request
import uuid


def request(url, headers=None, body=None):
    try:
        return urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}, data=body), timeout=10)
    except urllib.error.HTTPError as response:
        return response


def upload(count=1, authorized=True, size=16):
    boundary = 'va017-fixture'
    operation = {'query': 'mutation UploadSmoke($files: [Upload!]!) { upload(files: $files) }',
                 'variables': {'files': [None] * count}}
    parts = [('operations', json.dumps(operation).encode(), None),
             ('map', json.dumps({str(i): [f'variables.files.{i}'] for i in range(count)}).encode(), None)]
    parts += [(str(i), b'x' * size, f'synthetic-{i}.txt') for i in range(count)]
    body = b''
    for name, data, filename in parts:
        disposition = f'Content-Disposition: form-data; name="{name}"'
        if filename:
            disposition += f'; filename="{filename}"'
        body += f'--{boundary}\r\n{disposition}\r\n\r\n'.encode() + data + b'\r\n'
    body += f'--{boundary}--\r\n'.encode()
    headers = {'Content-Type': f'multipart/form-data; boundary={boundary}',
               'Accept': 'application/json', 'apollo-require-preflight': 'true'}
    if authorized:
        headers['Authorization'] = 'Bearer synthetic-va017'
    with request('http://router:4000/query', headers, body) as response:
        return json.load(response)


def notification(authorized=True):
    identifier = uuid.uuid4().hex
    headers = {'Content-Type': 'application/json', 'Accept': 'multipart/mixed;subscriptionSpec=1.0',
               'X-Request-ID': identifier}
    if authorized:
        headers['Authorization'] = 'Bearer synthetic-va017'
    body = json.dumps({'query': 'subscription NotificationSmoke { notificationReceived { id message } }'}).encode()
    with request('http://router:4000/query', headers, body) as response:
        content_type = response.headers.get('Content-Type', '')
        if not authorized and 'application/json' in content_type:
            error = json.load(response)
            assert error.get('errors') and not error.get('data'), error
            assert any('401' in e.get('message', '') and
                       e.get('extensions', {}).get('code') == 'SUBREQUEST_HTTP_ERROR'
                       for e in error['errors']), error
            return
        assert response.status == 200 and 'multipart/mixed' in content_type, (response.status, content_type)
        if authorized:
            # Trigger only after Router has opened the stream, avoiding a send-before-subscribe race.
            with request(f'http://mock:8080/emit/{identifier}') as emitted:
                assert json.load(emitted)['emitted']
        message = BytesParser(policy=default).parsebytes(
            f'Content-Type: {content_type}\r\n\r\n'.encode() + response.read())
        payloads = [json.loads(p.get_payload(decode=True)).get('payload') for p in message.iter_parts()]
        payloads = [p for p in payloads if p]
        if authorized:
            assert payloads == [{'data': {'notificationReceived': {'id': 'synthetic-1', 'message': 'test-only'}}}], payloads
        else:
            assert payloads and any(p.get('errors') for p in payloads), payloads
            assert not any(p.get('data') for p in payloads), payloads


if __name__ == '__main__':
    checks = []
    result = upload()
    assert result == {'data': {'upload': 'synthetic-0.txt:16'}}, result
    result = upload(authorized=False)
    assert result.get('errors') and not (result.get('data') or {}).get('upload'), result
    assert all(e.get('extensions', {}).get('code') == 'UNAUTHENTICATED' for e in result['errors']), result
    result = upload(count=6)
    assert any(e.get('extensions', {}).get('code') == 'FILE_UPLOADS_LIMITS_MAX_FILES_EXCEEDED'
               for e in result.get('errors', [])), result
    result = upload(size=10 * 1024 * 1024 + 1)
    assert result.get('errors') and not (result.get('data') or {}).get('upload'), result
    assert any('Exceeded the limit' in e.get('message', '') or
               e.get('extensions', {}).get('code') == 'FILE_UPLOADS_LIMITS_MAX_FILE_SIZE_EXCEEDED'
               for e in result['errors']), result
    checks.append('Web multipart upload: bearer/preflight, file bytes/name, auth denial, 5-file and 10-MiB limits')
    notification()
    notification()  # A new connection after server completion, like the Web reconnect path.
    notification(authorized=False)
    checks.append('Web notification HTTP multipart -> subgraph WebSocket: event, completion, reconnect, auth denial')
    print(json.dumps(checks))
