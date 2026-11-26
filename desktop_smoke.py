"""Installed desktop checks, enabled only by an explicit launcher flag."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import time
import urllib.request
import uuid


def exercise_pdf_engine(base_url):
    import pikepdf
    from PIL import Image
    fixture = io.BytesIO()
    with pikepdf.Pdf.new() as document:
        page = document.add_blank_page(page_size=(300, 450))
        image = document.make_stream(os.urandom(1200 * 1800 * 3))
        for key, value in dict(Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Image, Width=1200,
                               Height=1800, ColorSpace=pikepdf.Name.DeviceRGB, BitsPerComponent=8).items():
            image['/' + key] = value
        page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Photo=image))
        page.Contents = document.make_stream(b"q 300 0 0 450 0 0 cm /Photo Do Q\n")
        document.save(fixture)
    assert len(fixture.getvalue()) > 1_000_000, 'Fixture must force target-fit recompression'
    options = dict(output_name='Desktop-smoke.pdf', compress_mode='targetfit', target_mb=1,
                   linearize=True, split_enabled=False, rotation=90, page_size='a4',
                   orientation='portrait', fit='contain', margin='medium')
    boundary = 'CometForgeSmoke' + uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="options_json"\r\n\r\n'
            f'{json.dumps(options)}\r\n--{boundary}\r\n'
            'Content-Disposition: form-data; name="files"; filename="smoke.pdf"\r\n'
            'Content-Type: application/pdf\r\n\r\n').encode() + fixture.getvalue() + f'\r\n--{boundary}--\r\n'.encode()

    def get(path):
        with urllib.request.urlopen(base_url + path, timeout=120) as response:
            return response.read()

    request = urllib.request.Request(base_url + '/api/forge', data=body,
                                     headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    with urllib.request.urlopen(request, timeout=30) as response:
        job_id = json.load(response)['job_id']
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline:
        result = json.loads(get(f'/api/job/{job_id}'))
        assert result['stage'] != 'error', result
        if result['stage'] == 'done':
            break
        time.sleep(.1)
    else:
        raise AssertionError('Installed engine did not finish the smoke export')
    assert result['target_met'] and result['max_part_bytes'] <= 1_000_000, result
    output = result['outputs'][0]
    with pikepdf.open(io.BytesIO(get(output['preview_url']))) as document:
        assert len(document.pages) == 1 and document.is_linearized
        width, height = (float(document.pages[0].MediaBox[index]) for index in (2, 3))
        assert abs(width - 210 * 72 / 25.4) < 1 and abs(height - 297 * 72 / 25.4) < 1
    rendered = get(output['render_after_url'].replace('{page}', '1') + '&dpi=72')
    assert rendered.startswith(b'\x89PNG\r\n\x1a\n'), 'Bundled Ghostscript did not render'
    with Image.open(io.BytesIO(rendered)) as image:
        assert image.convert('RGB').getpixel((3, 3)) == (255, 255, 255), 'Unused page area must be white'
    return dict(export_success=True, preview_success=True, white_margins=True,
                target_met=True, output_bytes=result['max_part_bytes'])


def run(window, base_url, report_path, close_when_done=False):
    from version import __version__
    result = dict(version=__version__, desktop_window=True, success=False)
    try:
        deadline = time.monotonic() + 30
        setup_clicked = False
        while time.monotonic() < deadline:
            try:
                ui = window.evaluate_js("""({ready:document.readyState==='complete',
                    title:document.title, app:!!window.CometForge,
                    setup:!!document.getElementById('gs'),
                    bridge:typeof window.pywebview?.api?.finish==='function',
                    layout:!!document.getElementById('layoutStep'),
                    paper:document.getElementById('pageSize')?.options.length || 0})""")
            except Exception:
                # WKWebView can briefly reject evaluation while the setup
                # bridge navigates to the application document.
                time.sleep(.1)
                continue
            if ui and ui.get('setup') and ui.get('bridge') and not setup_clicked:
                window.evaluate_js("document.querySelector('button').click()")
                setup_clicked = True
            if ui and ui.get('ready') and ui.get('app') and ui.get('layout') and ui.get('paper', 0) >= 10:
                result['ui'] = ui
                result['setup_success'] = setup_clicked
                break
            time.sleep(.1)
        else:
            raise AssertionError('Desktop document did not load its app and layout controls')
        result.update(exercise_pdf_engine(base_url.rstrip('/')))
        result['success'] = True
    except Exception as error:
        result['error'] = str(error)
    finally:
        report = Path(report_path)
        report.parent.mkdir(parents=True, exist_ok=True)
        temporary = report.with_suffix('.partial')
        temporary.write_text(json.dumps(result, indent=2), encoding='utf-8')
        temporary.replace(report)
        if close_when_done:
            window.destroy()
