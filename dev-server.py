#!/usr/bin/env python3
"""
Development server for tennyson_map.

Serves static files and accepts POST /save requests to write files directly
to disk — enabling the "Save to Files" button in the map's edit mode.

Usage:
    python dev-server.py [port]     (default port: 8765)

Then open: http://localhost:8765/tennyson-map.html
"""

import http.server
import json
import os
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Files the client is allowed to write (whitelist for safety)
ALLOWED_FILES = {'tennyson-lots.csv', 'tennyson-map.svg', 'map-styles.css'}


class DevHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def do_POST(self):
        if self.path != '/save':
            self._respond(404, {'ok': False, 'error': 'Not found'})
            return

        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)

        try:
            data = json.loads(body)
            filename = data.get('filename', '')
            content = data.get('content', '')

            if filename not in ALLOWED_FILES:
                self._respond(403, {'ok': False, 'error': f'Not allowed: {filename}'})
                return

            filepath = os.path.join(BASE_DIR, filename)
            with open(filepath, 'w', encoding='utf-8', newline='') as f:
                f.write(content)

            print(f'  Saved: {filename} ({len(content)} bytes)')
            self._respond(200, {'ok': True, 'filename': filename})

        except Exception as e:
            print(f'  Save error: {e}')
            self._respond(500, {'ok': False, 'error': str(e)})

    def _respond(self, status, body_dict):
        body = json.dumps(body_dict).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def log_message(self, fmt, *args):
        # Only log non-GET requests to keep output clean
        first = str(args[0]) if args else ''
        if not first.startswith('GET'):
            print(f'{self.address_string()} - {fmt % args}')


if __name__ == '__main__':
    os.chdir(BASE_DIR)
    print(f'Tennyson Map dev server')
    print(f'  Serving:  http://localhost:{PORT}/')
    print(f'  Root dir: {BASE_DIR}')
    print(f'  POST /save writes: {", ".join(sorted(ALLOWED_FILES))}')
    print()
    with http.server.HTTPServer(('', PORT), DevHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\nStopped.')
