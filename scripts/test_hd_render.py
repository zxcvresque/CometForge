"""HD comparison API checks; no browser or visual/computer testing."""
import struct
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pikepdf
from fastapi.testclient import TestClient
import server


def fixture(path, sizes, crop=None, rotation=0, user_unit=1, inherited_rotation=False, color="0.2 0.6 0.4"):
    with pikepdf.Pdf.new() as document:
        for size in sizes:
            page = document.add_blank_page(page_size=size)
            if crop:
                page.obj["/CropBox"] = pikepdf.Array(crop)
            if inherited_rotation:
                page.obj["/Parent"]["/Rotate"] = rotation
            else:
                page.obj["/Rotate"] = rotation
            page.obj["/UserUnit"] = user_unit
            page.obj["/Contents"] = document.make_stream(
                (color + " rg 40 60 100 150 re f\n").encode() +
                b"0 0 0 RG 0.3 w 20 20 m 400 500 l S\n"
            )
        document.save(path)


def dimensions(response):
    assert response.status_code == 200, response.text
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", response.content[16:24])


def main():
    assert server._find_ghostscript(), "Ghostscript is needed for these rendering checks"
    original_work_dir = server.WORK_DIR
    with tempfile.TemporaryDirectory(prefix="cometforge-hd-") as directory:
        server.WORK_DIR = Path(directory)
        try:
            job_id = server.jobs.create()
            job_dir = server.WORK_DIR / job_id
            originals = job_dir / "originals"
            originals.mkdir(parents=True)
            before, after = originals / "before.pdf", job_dir / "after.pdf"
            fixture(before, [(612, 792), (700, 900)], crop=[30, 50, 630, 850], rotation=90)
            fixture(after, [(612, 792), (700, 900)], crop=[30, 50, 630, 850], rotation=90,
                    inherited_rotation=True, color="0.2 0.5 0.4")
            server.jobs.set(job_id, stage="done", original_paths=[str(before)], out_paths=[str(after)])
            client = TestClient(server.app)
            url = f"/api/job/{job_id}/render/0/2"
            with patch.object(server.subprocess, "run", wraps=server.subprocess.run) as run:
                baseline = client.get(url)
                assert baseline.headers["x-render-dpi"] == "144"
                assert dimensions(baseline) == (1600, 1200)
                hd_before = client.get(url, params={"variant": "before", "dpi": 432})
                hd_after = client.get(url, params={"variant": "after", "dpi": 432})
                assert dimensions(hd_before) == dimensions(hd_after) == (4800, 3600)
                assert hd_before.content != hd_after.content, "Both sides must render their own PDF content"
                assert hd_before.headers["x-render-dpi"] == hd_after.headers["x-render-dpi"] == "432"
                assert hd_after.headers["x-render-limited"] == "false"
                assert run.call_count == 3
                cached = client.get(url, params={"variant": "after", "dpi": 432})
                assert cached.content == hd_after.content and run.call_count == 3
                assert len(list((job_dir / "previews").glob("*.png"))) == 3

            # A different-sized counterpart must produce the SAME effective DPI
            # in either request, without exceeding either image's memory bound.
            second_id = server.jobs.create()
            second_dir = server.WORK_DIR / second_id
            (second_dir / "originals").mkdir(parents=True)
            giant_before, giant_after = second_dir / "originals/before.pdf", second_dir / "after.pdf"
            fixture(giant_before, [(12000, 10000)], rotation=90, user_unit=2)
            fixture(giant_after, [(11000, 9000)], rotation=90, user_unit=2)
            server.jobs.set(second_id, stage="done", original_paths=[str(giant_before)], out_paths=[str(giant_after)])
            giant_url = f"/api/job/{second_id}/render/0/1"
            responses = [client.get(giant_url, params={"variant": variant, "dpi": 576})
                         for variant in ("before", "after")]
            assert responses[0].headers["x-render-dpi"] == responses[1].headers["x-render-dpi"]
            for response in responses:
                width, height = dimensions(response)
                assert max(width, height) <= 8192 and width * height <= 20_000_000
                assert response.headers["x-render-limited"] == "true"
                assert float(response.headers["x-render-dpi"]) < 72

            # A long, thin page exercises the dimension bound rather than area.
            thin = second_dir / "thin.pdf"
            fixture(thin, [(12000, 1000)])
            thin_dpi = server._comparison_dpi([thin], 1, 576)
            assert abs(thin_dpi - 8191 * 72 / 12000) < .000001
            for invalid in (71, 577, "broken", "144.5"):
                assert client.get(url, params={"dpi": invalid}).status_code == 422
            assert client.get(f"/api/job/{job_id}/render/0/99?dpi=432").status_code == 404
            assert client.get(f"/api/job/{job_id}/render/99/1?dpi=432").status_code == 404
            assert client.get(url, params={"variant": "invalid", "dpi": 432}).status_code == 422
            print("PASS: HD sizes, matching crop/rotation, per-DPI cache, pair-shared resolution, UserUnit, raster safety limits, API validation")
        finally:
            server.WORK_DIR = original_work_dir


if __name__ == "__main__":
    main()
