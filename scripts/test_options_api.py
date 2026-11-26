"""Malformed numeric options must return client errors on every API path."""
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import server


def main():
    client = TestClient(server.app, raise_server_exceptions=False)
    # Unknown source intentionally proves options are rejected before lookup.
    for name in ('dpi_fallback', 'split_count', 'target_mb', 'margin_mm', 'rotation'):
        for bad in (float('inf'), float('-inf'), float('nan'), 10 ** 500, [], {}):
            options = {name: bad}
            payload = json.dumps(options)
            for endpoint in ('/api/source', '/api/forge'):
                response = client.post(endpoint,
                    files=[('files', ('fixture.pdf', b'%PDF', 'application/pdf'))],
                    data={'options_json': payload})
                assert response.status_code == 400, (name, type(bad), endpoint, response.text)
            for endpoint in ('/api/source/missing/forge', '/api/source/missing/preview'):
                # Send raw JSON so NaN/Infinity and oversized integer values also
                # exercise Python's accepted-but-nonfinite decoder results.
                for body in (payload, json.dumps({'options': options})):
                    response = client.post(endpoint, content=body,
                                           headers={'Content-Type': 'application/json'})
                    assert response.status_code == 400, (name, type(bad), endpoint, response.text)
    options = server._normalized_options({'dpi_fallback': 300, 'split_count': 2,
        'target_mb': 20.5, 'margin_mm': 12.5, 'rotation': -90})
    assert options['dpi_fallback'] == 300 and options['split_count'] == 2
    assert options['target_mb'] == 20.5 and options['margin_mm'] == 12.5 and options['rotation'] == 270
    print('PASS: malformed numeric values return400 across upload/staged/preview APIs; valid numeric options preserved')


if __name__ == '__main__':
    main()
