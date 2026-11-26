"""Live page previews must match real exported pages, including all layout edits."""
import hashlib
import io
import json
import sys
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pikepdf
from PIL import Image
from fastapi.testclient import TestClient
import server


def wait(client, path, done):
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        response = client.get(path)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data['stage'] != 'error', data
        if data['stage'] == done:
            return data
        time.sleep(.02)
    raise AssertionError(f'Timed out: {path}')


def fixture_pdf():
    output = io.BytesIO()
    with pikepdf.Pdf.new() as document:
        for angle in (0, 90):
            page = document.add_blank_page(page_size=(200, 300))
            page.obj['/Contents'] = document.make_stream(b'1 0 0 rg 0 0 200 300 re f 0 0 1 rg 20 40 80 110 re f\n')
            page.obj['/CropBox'] = pikepdf.Array([20, 40, 180, 260])
            page.obj['/Rotate'] = angle
            page.obj['/UserUnit'] = 2
        document.save(output)
    return output.getvalue()


def main():
    assert server._find_ghostscript(), 'Ghostscript required for live preview regression'
    old_work = server.WORK_DIR
    with tempfile.TemporaryDirectory(prefix='cometforge-live-preview-') as temporary:
        root = Path(temporary)
        server.WORK_DIR = root
        client = TestClient(server.app)
        try:
            alpha = Image.new('RGBA', (150, 80), (0, 0, 0, 0))
            for x in range(30, 120):
                for y in range(20, 60):
                    alpha.putpixel((x, y), (0, 160, 0, 255))
            png = io.BytesIO(); alpha.save(png, format='PNG', dpi=(72, 72))
            tiff = io.BytesIO()
            Image.new('RGB', (70, 110), 'yellow').save(tiff, format='TIFF', save_all=True,
                append_images=[Image.new('RGB', (70, 110), 'cyan')], dpi=(72, 72))
            uploaded = client.post('/api/source', files=[
                ('files', ('cropped.pdf', fixture_pdf(), 'application/pdf')),
                ('files', ('transparent.png', png.getvalue(), 'image/png')),
                ('files', ('pages.tiff', tiff.getvalue(), 'image/tiff'))])
            assert uploaded.status_code == 200, uploaded.text
            sid = uploaded.json()['source_id']
            metadata = wait(client, f'/api/source/{sid}', 'ready')
            assert metadata['source_page_counts'] == [2, 1, 2]
            built = root / sid / 'built.pdf'
            before = hashlib.sha256(built.read_bytes()).digest()
            endpoint = f'/api/source/{sid}/render'
            cases = [
                dict(page_size='original', rotation=90, source_rotations=[90,180,270], page_rotations={'2':90,'4':180}),
                dict(page_size='a4', orientation='portrait', fit='contain', margin='medium', rotation=90,
                     source_rotations=[90,180,270], page_rotations={'2':90,'4':180}),
                dict(page_size='letter', orientation='landscape', fit='cover', margin='custom', margin_mm=12.5,
                     source_rotations=[270,90,180], page_rotations={'1':90,'5':270}),
                dict(page_size='photo4x6', orientation='portrait', fit='actual', margin='small', rotation=270),
            ]
            for options in cases:
                export = client.post(f'/api/source/{sid}/forge', json={**options, 'compress_mode':'off'})
                assert export.status_code == 200, export.text
                jid = export.json()['job_id']
                wait(client, f'/api/job/{jid}', 'done')
                for page in range(1, 6):
                    live = client.post(endpoint, json={'page':page,'dpi':72,'options':options})
                    assert live.status_code == 200, live.text
                    actual = client.get(f'/api/job/{jid}/render/0/{page}?variant=after&dpi=72')
                    assert actual.status_code == 200, actual.text
                    live_image = Image.open(io.BytesIO(live.content)).convert('RGB')
                    exported_image = Image.open(io.BytesIO(actual.content)).convert('RGB')
                    assert live_image.size == exported_image.size, (options,page,live_image.size,exported_image.size)
                    assert live_image.tobytes() == exported_image.tobytes(), (options,page,'preview differs from export')
                    assert float(live.headers['x-page-width']) > 0 and float(live.headers['x-page-height']) > 0
                    assert live.headers['x-preview-page'] == str(page)
                    if options.get('margin'):
                        assert live_image.getpixel((0,0)) == (255,255,255)
            assert hashlib.sha256(built.read_bytes()).digest() == before, 'Preview mutated source'
            # Compression/name/split changes do not recompute identical geometry.
            base = {'page_size':'a4','margin':'small'}
            first = client.post(endpoint, json={'page':3,'dpi':72,'options':base})
            assert first.status_code == 200
            with patch.object(server, '_run_pdf_tool', side_effect=AssertionError('cache must not render')):
                repeated = client.post(endpoint, json={'page':3,'dpi':72,'options':{
                    **base,'compress_mode':'lossless','output_name':'Different','split_count':4}})
                assert repeated.status_code == 200 and repeated.content == first.content
            rotated = client.post(endpoint, json={'page':3,'dpi':72,'options':{**base,'rotation':90}})
            assert rotated.status_code == 200 and rotated.content != first.content
            dpi = client.post(endpoint, json={'page':3,'dpi':144,'options':base})
            assert dpi.status_code == 200 and dpi.content != first.content
            for value in [0,6,-1,1.5,True,'nope',float('inf')]:
                # JSON permits nonfinite literals in Python's encoder but httpx's
                # strict json path does not, so submit our encoded body directly.
                response = client.post(endpoint, content=json.dumps({'page':value}), headers={'Content-Type':'application/json'})
                assert response.status_code == 400, (value,response.text)
            for value in [0,71,577,True,100.5,float('nan')]:
                response = client.post(endpoint, content=json.dumps({'dpi':value}), headers={'Content-Type':'application/json'})
                assert response.status_code == 400, (value,response.text)
            for options in [{'source_rotations':[0]}, {'page_rotations':{'6':90}}, {'rotation':45},
                            {'page_size':'a6','margin':'custom','margin_mm':100}, {'fit':'invalid'}]:
                response = client.post(endpoint, json={'options':options})
                assert response.status_code == 400, (options,response.text)
            assert client.post(endpoint,json={'options':{'dpi_fallback':72}}).status_code == 409
            assert client.post('/api/source/missing/render',json={}).status_code == 404
            queued = server.sources.create()
            assert client.post(f'/api/source/{queued}/render',json={}).status_code == 409
            with patch.object(server,'_find_ghostscript',return_value=None):
                response = client.post(endpoint,json={'page':1,'dpi':73,'options':{'rotation':180}})
                assert response.status_code == 503, response.text
            with patch.object(server, '_run_pdf_tool', side_effect=subprocess.TimeoutExpired('gs', 60)):
                response = client.post(endpoint, json={'page':1,'dpi':75})
                assert response.status_code == 503, response.text
            large = io.BytesIO()
            with pikepdf.Pdf.new() as document:
                page = document.add_blank_page(page_size=(12000, 200))
                page.obj['/UserUnit'] = 2
                document.save(large)
            large_upload = client.post('/api/source', files=[('files',('wide.pdf',large.getvalue(),'application/pdf'))])
            large_id = large_upload.json()['source_id']
            wait(client, f'/api/source/{large_id}', 'ready')
            limited = client.post(f'/api/source/{large_id}/render', json={'dpi':576})
            assert limited.status_code == 200, limited.text
            assert limited.headers['x-render-limited'] == 'true'
            with Image.open(io.BytesIO(limited.content)) as image:
                assert max(image.size) <= 8192 and image.width * image.height <= 20_000_000
            # Cache eviction is bounded and never removes the currently sent image.
            cache_dir = root / sid / 'layout-previews'
            with patch.object(server,'SOURCE_PREVIEW_MAX_ENTRIES',3):
                response = client.post(endpoint,json={'page':5,'dpi':74})
                assert response.status_code == 200
                assert len(list(cache_dir.glob('*.png'))) <= 3
                assert len(list(cache_dir.glob('*.json'))) <= 3
            assert not list(cache_dir.glob('.*.pdf')) and not list(cache_dir.glob('.*.png'))
            print('PASS: live preview equals exported pixels for PDF CropBox/Rotate/UserUnit, transparent PNG, multipage TIFF; all rotations, fit/margins/paper/orientation, cache/validation/dependency/eviction and immutable sources')
        finally:
            server.WORK_DIR = old_work


if __name__ == '__main__':
    main()
