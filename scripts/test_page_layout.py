"""Exercise paper geometry, PDF rotation, white canvas and export API reuse."""
import hashlib
import io
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pikepdf
from PIL import Image
from fastapi.testclient import TestClient
import server


def fixture(path, pages=1, *, crop=False, rotation=0, user_unit=1):
    with pikepdf.Pdf.new() as document:
        for _ in range(pages):
            page = document.add_blank_page(page_size=(200, 300))
            page.obj['/Contents'] = document.make_stream(
                b'1 0 0 rg 0 0 200 300 re f 0 0 1 rg 0 0 100 150 re f\n')
            if crop:
                page.obj['/CropBox'] = pikepdf.Array([20, 40, 180, 260])
            page.obj['/Rotate'] = rotation
            page.obj['/UserUnit'] = user_unit
        document.save(path)


def render(path, output):
    result = server._run_pdf_tool([server._find_ghostscript(), '-q', '-dSAFER', '-dBATCH', '-dNOPAUSE',
        '-dUseCropBox', '-sDEVICE=png16m', '-r72', '-dFirstPage=1', '-dLastPage=1',
        f'-sOutputFile={output}', str(path)])
    assert result.returncode == 0, result.stderr
    return Image.open(output).convert('RGB')


def white(pixel):
    assert min(pixel) >= 250, pixel


def wait(client, url, complete):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        response = client.get(url)
        assert response.status_code == 200, response.text
        value = response.json()
        assert value['stage'] != 'error' or complete == 'error', value
        if value['stage'] == complete:
            return value
        time.sleep(.02)
    raise AssertionError(f'Timeout: {url}')


def main():
    original_work_dir = server.WORK_DIR
    with tempfile.TemporaryDirectory(prefix='cometforge-layout-') as directory:
        root = Path(directory)
        server.WORK_DIR = root
        try:
            source, destination = root / 'source.pdf', root / 'layout.pdf'
            fixture(source, crop=True, rotation=90, user_unit=2)
            before = hashlib.sha256(source.read_bytes()).digest()
            options = server._normalized_options({'page_size': 'original', 'margin': 'medium'})
            assert server._apply_page_layout(source, destination, options, [1])
            with pikepdf.open(destination) as document:
                assert not document.check_pdf_syntax()
                w, h = [float(n) for n in list(document.pages[0].MediaBox)[2:]]
                assert abs(w - (440 + 20 * server.MM)) < .001
                assert abs(h - (320 + 20 * server.MM)) < .001
            assert hashlib.sha256(source.read_bytes()).digest() == before
            if server._find_ghostscript():
                original = render(source, root / 'source.png')
                resized = render(destination, root / 'layout.png')
                assert original.size == (440, 320), original.size
                margin = 10 * server.MM
                for fx in (.2, .8):
                    for fy in (.2, .8):
                        assert original.getpixel((int(440 * fx), int(320 * fy))) == resized.getpixel(
                            (round(margin + 440 * fx), round(margin + 320 * fy)))
                for point in [(0, 0), (20, 100), (100, 20), (resized.width - 1, resized.height - 1)]:
                    white(resized.getpixel(point))

            # A transparent raster must sit on opaque white paper, including its
            # own transparent pixels and the unused space in a different aspect.
            image = Image.new('RGBA', (120, 60), (0, 0, 0, 0))
            for x in range(40, 80):
                for y in range(20, 40):
                    image.putpixel((x, y), (0, 180, 0, 255))
            png, built = root / 'alpha.png', root / 'image.pdf'
            image.save(png, dpi=(72, 72))
            assert server._build_pdf([png], built) == [1]
            tiff, multi_built = root / 'multi.tiff', root / 'multi-image.pdf'
            Image.new('RGB', (40, 60), 'red').save(tiff, save_all=True,
                append_images=[Image.new('RGB', (40, 60), 'blue')])
            assert server._build_pdf([tiff, png], multi_built) == [2, 1]
            server._apply_page_layout(multi_built, destination,
                server._normalized_options({'source_rotations': [90, 180]}), [2, 1])
            with pikepdf.open(destination) as document:
                assert [int(page.obj.get('/Rotate', 0)) for page in document.pages] == [90, 90, 180]
            fixed = server._normalized_options({'page_size': 'a4', 'orientation': 'portrait', 'margin': 'small'})
            server._apply_page_layout(built, destination, fixed, [1])
            if server._find_ghostscript():
                preview = render(destination, root / 'alpha-layout.png')
                assert preview.size == (595, 842), preview.size
                for point in [(0, 0), (100, 100), (50, 421), (297, 180)]:
                    white(preview.getpixel(point))
                assert preview.getpixel((297, 421)) == (0, 180, 0)

            # Cover crops at the margin; actual size keeps physical dimensions.
            fixture(source)
            for fit in ('contain', 'cover', 'actual'):
                value = server._normalized_options({'page_size': 'photo4x6', 'fit': fit, 'margin': 'medium'})
                server._apply_page_layout(source, destination, value, [1])
                if server._find_ghostscript():
                    preview = render(destination, root / f'{fit}.png')
                    white(preview.getpixel((10, preview.height // 2)))
                    assert preview.getpixel((preview.width // 2, preview.height // 2)) != (255, 255, 255)
            for paper in server.PAGE_SIZES_MM:
                value = server._normalized_options({'page_size': paper, 'orientation': 'landscape'})
                server._apply_page_layout(source, destination, value, [1])
                with pikepdf.open(destination) as document:
                    width, height = (float(n) for n in list(document.pages[0].MediaBox)[2:])
                    assert width >= height

            if server._find_ghostscript():
                # Force a real lossy pass (not just the lossless fast path) and
                # ensure compression preserves the user's displayed rotation.
                noisy, noisy_pdf, compressed = root / 'noise.png', root / 'noise.pdf', root / 'compressed.pdf'
                Image.effect_noise((1800, 2400), 128).save(noisy, dpi=(300, 300))
                server._build_pdf([noisy], noisy_pdf)
                with pikepdf.open(noisy_pdf, allow_overwriting_input=True) as document:
                    document.pages[0].rotate(90, relative=True)
                    document.save(noisy_pdf)
                assert noisy_pdf.stat().st_size > server.MB
                server._finish_pdf(noisy_pdf, compressed, compress_mode='targetfit',
                                   target_bytes=server.MB, linearize=False)
                assert compressed.stat().st_size <= server.MB
                assert server._comparison_page_geometry(noisy_pdf, 1) == server._comparison_page_geometry(compressed, 1)

            # Existing annotations stay interactive in rotation-only output.
            with pikepdf.open(source, allow_overwriting_input=True) as document:
                document.pages[0].obj['/Annots'] = pikepdf.Array([document.make_indirect(pikepdf.Dictionary(
                    Type=pikepdf.Name.Annot, Subtype=pikepdf.Name.Link, Rect=pikepdf.Array([10, 10, 20, 20]),
                    A=pikepdf.Dictionary(S=pikepdf.Name.URI, URI='https://example.com')))])
                document.save(source)
            value = server._normalized_options({'rotation': 90})
            server._apply_page_layout(source, destination, value, [1])
            with pikepdf.open(destination) as document:
                assert int(document.pages[0].obj['/Rotate']) == 90
                assert len(document.pages[0].obj['/Annots']) == 1
            assert not server._apply_page_layout(source, destination, server._normalized_options({}), [1])
            for bad in ({'rotation': 45}, {'page_size': 'bogus'}, {'margin_mm': -1}, {'margin_mm': float('nan')},
                        {'page_rotations': {'0': 90}}, {'source_rotations': '90'}, {'fit': 'stretch'}):
                try:
                    server._normalized_options(bad)
                    raise AssertionError(f'Accepted {bad}')
                except (ValueError, TypeError):
                    pass
            try:
                server._apply_page_layout(source, destination,
                    server._normalized_options({'page_size': 'a6', 'margin': 'custom', 'margin_mm': 100}), [1])
                raise AssertionError('Accepted a margin larger than the page')
            except ValueError:
                pass

            # Both APIs apply queue/page/global rotation, staged source remains
            # immutable, changed options invalidate exact-preview/forge cache.
            first, second = root / 'first.pdf', root / 'second.pdf'
            fixture(first, pages=2)
            fixture(second)
            files = [('files', ('first.pdf', first.read_bytes(), 'application/pdf')),
                     ('files', ('second.pdf', second.read_bytes(), 'application/pdf'))]
            client = TestClient(server.app)
            stage = client.post('/api/source', files=files)
            assert stage.status_code == 200, stage.text
            sid = stage.json()['source_id']
            status = wait(client, f'/api/source/{sid}', 'ready')
            assert status['source_page_counts'] == [2, 1], status
            source_hash = hashlib.sha256(Path(server.sources.get(sid)['built_path']).read_bytes()).digest()
            values = {'compress_mode': 'off', 'rotation': 90, 'source_rotations': [90, 0],
                      'page_rotations': {'2': 90}, 'output_name': 'rotated.pdf'}
            job_response = client.post(f'/api/source/{sid}/preview', json={**values, 'exact': True})
            assert job_response.status_code == 200, job_response.text
            jid = job_response.json()['job_id']
            result = wait(client, f'/api/job/{jid}', 'done')
            exported = client.get(f'/api/job/{jid}/download')
            with pikepdf.open(io.BytesIO(exported.content)) as document:
                assert [int(p.obj.get('/Rotate', 0)) for p in document.pages] == [180, 270, 90]
            repeated = client.post(f'/api/source/{sid}/forge', json=values).json()
            assert repeated['cached'] and repeated['job_id'] == jid
            changed = client.post(f'/api/source/{sid}/forge', json={**values, 'rotation': 0}).json()
            assert changed['job_id'] != jid
            wait(client, f'/api/job/{changed["job_id"]}', 'done')
            assert hashlib.sha256(Path(server.sources.get(sid)['built_path']).read_bytes()).digest() == source_hash
            for bad in ({'source_rotations': [90]}, {'page_rotations': {'4': 90}}):
                assert client.post(f'/api/source/{sid}/forge', json=bad).status_code == 400
                assert client.post(f'/api/source/{sid}/preview', json=bad).status_code == 400
            # No-op rotations still need validation on the legacy upload route.
            for bad in ({'source_rotations': [0]}, {'page_rotations': {'999': 0}}):
                response = client.post('/api/forge', files=files,
                    data={'options_json': json.dumps({'compress_mode': 'off', **bad})})
                assert response.status_code == 200, response.text
                rejected = wait(client, f'/api/job/{response.json()["job_id"]}', 'error')
                assert rejected['error'], rejected
            legacy = client.post('/api/forge', files=files,
                                 data={'options_json': json.dumps({**values, 'page_size': 'letter', 'margin': 'medium'})})
            assert legacy.status_code == 200, legacy.text
            legacy_id = legacy.json()['job_id']
            wait(client, f'/api/job/{legacy_id}', 'done')
            with pikepdf.open(io.BytesIO(client.get(f'/api/job/{legacy_id}/download').content)) as document:
                assert len(document.pages) == 3
                assert abs(float(document.pages[0].MediaBox[2]) - 612) < .01
                assert abs(float(document.pages[1].MediaBox[2]) - 792) < .01
            print('PASS: paper sizes/orientation/fit, white canvas/transparency, crop/rotation/UserUnit pixels, per-source/page rotation, annotations, staged and legacy exports, validation and cache invalidation')
        finally:
            server.WORK_DIR = original_work_dir


if __name__ == '__main__':
    main()
