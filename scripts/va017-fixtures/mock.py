"""Synthetic subgraphs only. Never accepts or stores real credentials or business data."""
import base64
from email.parser import BytesParser
from email.policy import default
import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import struct
import threading


OBSERVATIONS = {}
LOCK = threading.Lock()
EMIT = {}
READY = threading.Condition(LOCK)


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def do_GET(self):
        if self.path == '/query' and self.headers.get('Upgrade', '').lower() == 'websocket':
            self.websocket()
            return
        if self.path.startswith('/emit/'):
            identifier = self.path.removeprefix('/emit/')
            with READY:
                READY.wait_for(lambda: identifier in EMIT, timeout=5)
                event = EMIT.get(identifier)
            if event:
                event.set()
            self.respond({'emitted': event is not None})
            return
        if self.path.startswith('/observations/'):
            with LOCK:
                observations = OBSERVATIONS.pop(self.path.removeprefix('/observations/'), [])
            self.respond(observations)
            return
        self.respond({'ready': True})

    def read_body(self):
        if self.headers.get('Transfer-Encoding', '').lower() == 'chunked':
            chunks = []
            size = 0
            while True:
                line = self.rfile.readline()
                if not line:
                    raise ConnectionError('Router stopped forwarding the upload')
                length = int(line.split(b';')[0].strip(), 16)
                if not length:
                    assert self.rfile.readline() == b'\r\n'
                    return b''.join(chunks)
                size += length
                assert size <= 16 * 1024 * 1024
                chunks.append(self.rfile.read(length))
                assert self.rfile.read(2) == b'\r\n'
        length = int(self.headers['Content-Length'])
        assert length <= 16 * 1024 * 1024
        return self.rfile.read(length)

    def do_POST(self):
        try:
            raw = self.read_body()
        except ConnectionError:
            self.close_connection = True
            return
        if self.headers.get('Content-Type', '').startswith('multipart/form-data'):
            self.upload(raw)
            return
        body = json.loads(raw)
        field = self.path.strip('/')
        assert field in ('left', 'right')
        with LOCK:
            OBSERVATIONS.setdefault(self.headers.get('X-Request-ID'), []).append({
                'path': self.path, 'headers': {k.lower(): v for k, v in self.headers.items()}})
        if self.headers.get('Authorization') != 'Bearer synthetic-va017':
            result = {'data': {field: None}, 'errors': [{
                'message': 'synthetic access denied', 'path': [field],
                'extensions': {'code': 'UNAUTHENTICATED'}}]}
        elif field == 'right' and '_entities' in body['query']:
            assert body['variables']['representations'] == [{'__typename': 'Account', 'id': 'synthetic-1'}]
            result = {'data': {'_entities': [{'__typename': 'Account', 'id': 'synthetic-1', 'label': 'account-ok'}]}}
        elif field == 'left' and 'account' in body['query']:
            result = {'data': {'account': {'__typename': 'Account', 'id': 'synthetic-1'}}}
        else:
            assert field in body['query']
            result = {'data': {field: f'{field}-ok'}}
        self.respond(result)

    def upload(self, raw):
        if self.headers.get('Authorization') != 'Bearer synthetic-va017':
            self.respond({'data': {'upload': None}, 'errors': [{'message': 'synthetic access denied',
                          'path': ['upload'], 'extensions': {'code': 'UNAUTHENTICATED'}}]})
            return
        message = BytesParser(policy=default).parsebytes(
            f'Content-Type: {self.headers["Content-Type"]}\r\n\r\n'.encode() + raw)
        parts = list(message.iter_parts())
        names = [p.get_param('name', header='content-disposition') for p in parts]
        assert names[:2] == ['operations', 'map'], names
        operation = json.loads(parts[0].get_payload(decode=True))
        mapping = json.loads(parts[1].get_payload(decode=True))
        assert 'upload' in operation['query'] and operation['variables']['files'] == [None]
        assert mapping == {names[2]: ['variables.files.0']}
        data = parts[2].get_payload(decode=True)
        assert data == b'x' * len(data)
        self.respond({'data': {'upload': f'{parts[2].get_filename()}:{len(data)}'}})

    def ws_send(self, message):
        payload = json.dumps(message).encode()
        prefix = bytes([0x81, len(payload)]) if len(payload) < 126 else b'\x81\x7e' + struct.pack('!H', len(payload))
        self.wfile.write(prefix + payload)
        self.wfile.flush()

    def ws_receive(self):
        frame = self.rfile.read(2)
        if not frame or frame[0] & 0x0f == 8:
            return None
        assert frame[0] == 0x81 and frame[1] & 0x80, 'expected one masked text frame'
        length = frame[1] & 0x7f
        if length == 126:
            length = struct.unpack('!H', self.rfile.read(2))[0]
        assert length < 65536 and length != 127
        mask = self.rfile.read(4)
        payload = self.rfile.read(length)
        return json.loads(bytes(c ^ mask[i % 4] for i, c in enumerate(payload)))

    def websocket(self):
        # Minimal bounded test peer, only for this fixture's modern graphql-ws exchange.
        self.connection.settimeout(15)
        if self.headers.get('Authorization') != 'Bearer synthetic-va017':
            self.send_error(401, 'synthetic access denied')
            return
        assert self.headers.get('Sec-WebSocket-Protocol') == 'graphql-transport-ws'
        accept = base64.b64encode(hashlib.sha1(
            (self.headers['Sec-WebSocket-Key'] + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode(),
            usedforsecurity=False).digest()).decode()
        self.send_response(101)
        self.send_header('Upgrade', 'websocket')
        self.send_header('Connection', 'Upgrade')
        self.send_header('Sec-WebSocket-Accept', accept)
        self.send_header('Sec-WebSocket-Protocol', 'graphql-transport-ws')
        self.end_headers()
        assert self.ws_receive()['type'] == 'connection_init'
        self.ws_send({'type': 'connection_ack'})
        subscribe = self.ws_receive()
        assert subscribe['type'] == 'subscribe' and 'notificationReceived' in subscribe['payload']['query']
        identifier = self.headers['X-Request-ID']
        event = threading.Event()
        with READY:
            EMIT[identifier] = event
            READY.notify_all()
        try:
            assert event.wait(10), 'client never requested a notification'
            self.ws_send({'id': subscribe['id'], 'type': 'next', 'payload': {'data': {
                'notificationReceived': {'id': 'synthetic-1', 'message': 'test-only'}}}})
            self.ws_send({'id': subscribe['id'], 'type': 'complete'})
            # Wait for Router to acknowledge close rather than dropping a buffered event.
            self.ws_receive()
        finally:
            with LOCK:
                EMIT.pop(identifier, None)
            self.close_connection = True

    def respond(self, result):
        encoded = json.dumps(result).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_):
        pass


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
