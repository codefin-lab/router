"""Synthetic subgraphs only. Never accepts or stores real credentials or business data."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'ready')

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        field = self.path.strip('/')
        assert field in ('left', 'right') and field in body['query']
        if self.headers.get('Authorization') != 'Bearer synthetic-va017':
            result = {'data': {field: None}, 'errors': [{
                'message': 'synthetic access denied', 'path': [field],
                'extensions': {'code': 'UNAUTHENTICATED'}}]}
        elif (self.headers.get('X-Request-ID') != 'va017-test'
              or self.headers.get('X-Correlation-ID') != 'va017-correlation'
              or not self.headers.get('traceparent')):
            result = {'errors': [{'message': 'synthetic header propagation failed'}]}
        else:
            result = {'data': {field: f'{field}-ok'}}
        encoded = json.dumps(result).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_):
        pass


ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
