"""Verify staging, estimates, exact reuse, names and page-based exports."""
import io
import json
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pikepdf
from fastapi.testclient import TestClient
import server


def wait(client, url, finished):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        response = client.get(url)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['stage'] != 'error', result
        if result['stage'] == finished:
            return result
        time.sleep(.05)
    raise AssertionError(f'Timed out: {url}')


def main():
    client = TestClient(server.app)
    with pikepdf.Pdf.new() as doc:
        for index in range(11):
            page = doc.add_blank_page(page_size=(612, 792))
            page.obj['/Contents'] = doc.make_stream(f'% page {index + 1}\n'.encode())
        data = io.BytesIO()
        doc.save(data)
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, 'w') as bundle:
        bundle.writestr('nested/1.pdf', data.getvalue())
        bundle.writestr('nested/ignored.txt', b'Not a PDF input')
    imported = client.post('/api/import', files=[('files', ('fixture.zip', zipped.getvalue(), 'application/zip'))])
    assert imported.status_code == 200, imported.text
    entries = imported.json()['files']
    assert len(entries) == 1 and entries[0]['name'] == '1.pdf'
    assert entries[0]['size'] == len(data.getvalue()) and entries[0]['last_modified'] > 0
    assert client.get(entries[0]['url']).content == data.getvalue()
    unsafe = io.BytesIO()
    with zipfile.ZipFile(unsafe, 'w') as bundle:
        bundle.writestr('../outside.pdf', data.getvalue())
    assert client.post('/api/import', files=[('files', ('unsafe.zip', unsafe.getvalue(), 'application/zip'))]).status_code == 400
    result = client.post('/api/source', files=[('files', ('sample.pdf', data.getvalue(), 'application/pdf'))])
    assert result.status_code == 200, result.text
    source = result.json()['source_id']
    assert wait(client, f'/api/source/{source}', 'ready')['page_count'] == 11
    options = dict(output_name='QA export', compress_mode='targetfit', linearize=True,
                   target_mb=20.1, split_enabled=True, split_count=5, dpi_fallback=300)
    estimate = client.post(f'/api/source/{source}/preview', json={**options, 'exact': False})
    assert estimate.status_code == 200, estimate.text
    outputs = estimate.json()['outputs']
    assert len(outputs) == 5
    assert all(row['low_bytes'] <= row['bytes'] <= row['high_bytes'] for row in outputs)
    job_response = client.post(f'/api/source/{source}/preview', json={**options, 'exact': True})
    assert job_response.status_code == 200, job_response.text
    job = job_response.json()['job_id']
    measured = wait(client, f'/api/job/{job}', 'done')
    assert measured['target_met'] is True and measured['target_bytes'] == 20_100_000
    assert len(measured['outputs']) == 5
    assert measured['download_name'] == 'QA export.zip'
    reuse = client.post(f'/api/source/{source}/forge', json=options).json()
    assert reuse['job_id'] == job and reuse['cached'] is True
    archive = client.get(f'/api/job/{job}/download')
    assert archive.headers['content-type'] == 'application/zip'
    count = 0
    with zipfile.ZipFile(io.BytesIO(archive.content)) as zipped:
        assert len(zipped.namelist()) == 5
        for name in zipped.namelist():
            assert name.endswith('.pdf')
            with pikepdf.open(io.BytesIO(zipped.read(name))) as doc:
                count += len(doc.pages)
                assert doc.is_linearized and doc.check_linearization()
    assert count == 11
    preview = client.get(measured['outputs'][0]['preview_url'])
    assert preview.status_code == 200 and preview.content.startswith(b'%PDF')
    assert preview.headers['content-disposition'].startswith('inline')
    assert measured['part_index'] == measured['part_count'] == 5
    assert measured['detail'] == 'Export complete'
    for output in measured['outputs']:
        before = client.get(output['before_url'])
        assert before.status_code == 200 and before.content.startswith(b'%PDF')
        assert before.headers['content-disposition'].startswith('inline')
        assert len(before.content) == output['original_bytes']
        with pikepdf.open(io.BytesIO(before.content)) as original:
            assert len(original.pages) == output['page_end'] - output['page_start'] + 1
    assert client.get(f'/api/job/{job}/before/99').status_code == 404
    if server._find_ghostscript():
        before_png = client.get(f'/api/job/{job}/render/0/1?variant=before')
        after_png = client.get(f'/api/job/{job}/render/0/1?variant=after')
        assert before_png.status_code == after_png.status_code == 200
        assert before_png.content[:8] == after_png.content[:8] == b'\x89PNG\r\n\x1a\n'
        assert before_png.content[16:24] == after_png.content[16:24]
        assert client.get(f'/api/job/{job}/render/0/999?variant=before').status_code == 404
    assert client.get(f'/api/job/{job}/preview/-1').status_code == 404
    assert client.post(f'/api/source/{source}/forge', json={**options, 'target_mb': -5}).status_code == 400
    assert client.post(f'/api/source/{source}/forge', json={**options, 'split_count': 12}).status_code == 400
    print('PASS: ZIP import, source reuse, estimates, cache, 5 PDFs, all pages, linearization, comparison rendering and per-part progress')


if __name__ == '__main__':
    main()
