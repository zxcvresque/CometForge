from __future__ import annotations

import io
import hashlib
import json
import math
import mimetypes
import os
import stat
import shutil
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Literal, Optional, Sequence

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool
import img2pdf
import pikepdf


APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
STATIC_DIR = APP_DIR / "static"
WORK_DIR = Path(os.environ.get("COMETFORGE_DATA_DIR", str(APP_DIR / "work")))
WORK_DIR.mkdir(parents=True, exist_ok=True)

MB = 1_000_000


def _now() -> float:
    return time.time()


def _safe_filename(name: str) -> str:
    name = (name or "output.pdf").strip()
    # Keep it simple: allow alnum + some safe punctuation
    keep = []
    for ch in name:
        if ch.isalnum() or ch in (" ", ".", "_", "-", "(", ")", "[", "]"):
            keep.append(ch)
        else:
            keep.append("_")
    out = "".join(keep).strip().replace("  ", " ")
    if not out.strip(". "):
        return "output.pdf"
    if not out.lower().endswith(".pdf"):
        out += ".pdf"
    return out or "output.pdf"


def _safe_archive_name(name: str) -> str:
    """Return a safe ZIP filename without accidentally giving it a .pdf suffix."""
    safe_pdf_name = _safe_filename(name)
    return f"{Path(safe_pdf_name).stem}.zip"


def _fmt_mb(n: int) -> float:
    return round(n / MB, 2)


def _run_pdf_tool(command, **options):
    """Run native PDF tools without spawning a console on Windows."""
    if sys.platform == "win32":
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        options.update(creationflags=subprocess.CREATE_NO_WINDOW, startupinfo=startup)
    return subprocess.run(command, capture_output=True, text=True, **options)


def _find_ghostscript() -> Optional[str]:
    if os.environ.get("COMETFORGE_DISABLE_GHOSTSCRIPT") == "1":
        return None
    configured = os.environ.get("COMETFORGE_GHOSTSCRIPT") or os.environ.get("GHOSTSCRIPT_BIN")
    candidates = [Path(configured)] if configured else []
    candidates.extend([APP_DIR / "ghostscript" / "bin" / name for name in ("gs", "gswin64c.exe", "gswin32c.exe")])
    for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if root:
            candidates.extend(sorted((Path(root) / "gs").glob("gs*/bin/gswin*c.exe"), reverse=True))
    for path in candidates:
        if path.is_file() and (os.name == "nt" or os.access(path, os.X_OK)):
            return str(path)
    # Common names on Windows + *nix. Homebrew's ARM prefix is not always in
    # the environment PATH used by a launch agent, so check it explicitly.
    for exe in ("gswin64c", "gswin32c", "gs"):
        p = shutil.which(exe)
        if p:
            return p
    for path in (Path("/opt/homebrew/bin/gs"), Path("/usr/local/bin/gs")):
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


class JobStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[str, dict] = {}

    def create(self) -> str:
        jid = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[jid] = {
                "created_at": _now(),
                "stage": "queued",
                "progress_build": 0,
                "progress_compress": 0,
                "output_bytes": 0,
                "diff_bytes": None,
                "error": None,
                "out_path": None,
                "out_paths": [],
                "download_name": None,
                "target_bytes": None,
                "max_part_bytes": None,
                "target_met": None,
                "phase": "queued",
                "detail": "Waiting to start",
                "part_index": 0,
                "part_count": 0,
            }
        return jid

    def set(self, jid: str, **kwargs) -> None:
        with self._lock:
            if jid in self._jobs:
                self._jobs[jid].update(kwargs)

    def get(self, jid: str) -> Optional[dict]:
        with self._lock:
            j = self._jobs.get(jid)
            return dict(j) if j else None

    def cleanup(self, older_than_s: int = 3600) -> None:
        cutoff = _now() - older_than_s
        to_delete: List[str] = []
        with self._lock:
            for jid, j in self._jobs.items():
                if j.get("created_at", 0) < cutoff and j.get("stage") in {"done", "error"}:
                    to_delete.append(jid)
            for jid in to_delete:
                self._jobs.pop(jid, None)

        # remove job folders too
        for jid in to_delete:
            d = WORK_DIR / jid
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)

    def cleanup_sources(self, older_than_s: int = 3600) -> None:
        cutoff = _now() - older_than_s
        with source_lock, self._lock:
            expired = [sid for sid, source in self._jobs.items()
                       if source["stage"] in {"ready", "error"}
                       and source.get("created_at", 0) < cutoff
                       and not any((jobs.get(jid) or {}).get("stage") in {"queued", "building", "compressing"}
                                   for jid in source.get("active_jobs", []))]
            for sid in expired:
                self._jobs.pop(sid, None)
        for sid in expired:
            shutil.rmtree(WORK_DIR / sid, ignore_errors=True)


jobs = JobStore()
sources = JobStore()
imports = JobStore()
source_lock = threading.RLock()
render_lock = threading.Lock()
app = FastAPI(title="CometForge")


@app.get("/api/capabilities")
def capabilities() -> dict:
    try:
        from version import VERSION
    except ImportError:
        VERSION = "development"
    return {"version": VERSION, "ghostscript": bool(_find_ghostscript()), "size_preview": "estimate-and-exact"}


def _normalized_options(options: dict) -> dict:
    if not isinstance(options, dict):
        raise ValueError("Options must be a JSON object.")
    mode = str(options.get("compress_mode", "targetfit")).strip().lower()
    if mode in {"none", "false", "0"}:
        mode = "off"
    if mode not in {"off", "lossless", "targetfit"}:
        raise ValueError("Unknown compression mode.")
    target = float(options.get("target_mb", 20) or 20)
    if not math.isfinite(target) or not 1 <= target <= 10000:
        raise ValueError("Target must be between 1 and 10000 MB.")
    split = options.get("split_count", options.get("split_parts", options.get("split_files", 1)))
    if options.get("split_enabled") is False:
        split = 1
    if isinstance(split, bool):
        split = 5 if split else 1
    split = int(split or 1)
    dpi = int(options.get("dpi_fallback", 300) or 300)
    if not 1 <= split <= 10000 or not 36 <= dpi <= 2400:
        raise ValueError("Invalid page split count or image DPI.")
    return {"output_name": _safe_filename(str(options.get("output_name", "CometForge.pdf"))),
            "compress_mode": mode, "target_mb": target,
            "linearize": bool(options.get("linearize", False)), "split_count": split,
            "dpi_fallback": dpi}


IMPORT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}
IMPORT_MAX_FILES = 5000
IMPORT_MAX_FILE_BYTES = 512 * MB
IMPORT_MAX_TOTAL_BYTES = 2000 * MB


def _expand_import(import_id: str, uploads: List[tuple[Path, str]]) -> List[dict]:
    """Expand supported ZIP entries with size limits and no archive paths on disk."""
    directory = WORK_DIR / import_id / "files"
    directory.mkdir()
    metadata: List[dict] = []
    expanded_bytes = 0

    def save_entry(handle, name: str, timestamp: int) -> None:
        nonlocal expanded_bytes
        if len(metadata) >= IMPORT_MAX_FILES:
            raise ValueError("Import supports at most 5000 files.")
        extension = Path(name).suffix.lower()
        destination = directory / f"{len(metadata):06d}{extension}"
        file_bytes = 0
        with destination.open("wb") as output:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                file_bytes += len(chunk)
                expanded_bytes += len(chunk)
                if file_bytes > IMPORT_MAX_FILE_BYTES or expanded_bytes > IMPORT_MAX_TOTAL_BYTES:
                    raise ValueError("Import exceeds the 512 MB per-file or 2 GB total expanded limit.")
                output.write(chunk)
        metadata.append({"name": name, "size": file_bytes, "last_modified": timestamp,
                         "type": mimetypes.guess_type(name)[0] or "application/octet-stream",
                         "url": f"/api/import/{import_id}/file/{len(metadata)}",
                         "path": str(destination)})

    for upload, display_name in uploads:
        if upload.suffix == ".zip":
            with zipfile.ZipFile(upload) as archive:
                supported = []
                file_count = 0
                declared_bytes = 0
                for entry in archive.infolist():
                    normalized = entry.filename.replace("\\", "/")
                    parts = normalized.split("/")
                    mode = (entry.external_attr >> 16) & 0o170000
                    if normalized.startswith("/") or ".." in parts or ":" in parts[0] or mode == stat.S_IFLNK:
                        raise ValueError("ZIP contains an unsafe path or symbolic link.")
                    if entry.is_dir():
                        continue
                    file_count += 1
                    if file_count > IMPORT_MAX_FILES:
                        raise ValueError("ZIP supports at most 5000 files.")
                    if "__MACOSX" in parts or parts[-1] == ".DS_Store":
                        continue
                    name = parts[-1]
                    if Path(name).suffix.lower() not in IMPORT_EXTENSIONS:
                        continue
                    if entry.flag_bits & 1:
                        raise ValueError("Encrypted ZIP files are not supported. Extract the archive first.")
                    declared_bytes += entry.file_size
                    if entry.file_size > IMPORT_MAX_FILE_BYTES or expanded_bytes + declared_bytes > IMPORT_MAX_TOTAL_BYTES:
                        raise ValueError("ZIP exceeds the 512 MB per-file or 2 GB total expanded limit.")
                    supported.append((entry, name))
                for entry, name in supported:
                    try:
                        timestamp = int(datetime(*entry.date_time).timestamp() * 1000)
                    except (ValueError, OverflowError, OSError):
                        timestamp = int(_now() * 1000)
                    with archive.open(entry) as handle:
                        save_entry(handle, name, timestamp)
        else:
            with upload.open("rb") as handle:
                save_entry(handle, display_name, int(_now() * 1000))
    if not metadata:
        raise ValueError("No supported PDFs or images were found in this import.")
    return metadata


@app.post("/api/import")
async def import_files(files: List[UploadFile] = File(...)) -> JSONResponse:
    """Stage ZIP, PDF and image inputs so the browser can expand its queue."""
    imports.cleanup(older_than_s=3600)
    import_id = imports.create()
    directory = WORK_DIR / import_id
    incoming = directory / "incoming"
    incoming.mkdir(parents=True)
    try:
        if not files or len(files) > IMPORT_MAX_FILES:
            raise ValueError("Choose between 1 and 5000 ZIP, PDF or image files.")
        uploads = []
        upload_bytes = 0
        for index, upload in enumerate(files):
            name = (upload.filename or "file").replace("\\", "/").split("/")[-1]
            extension = Path(name).suffix.lower()
            if extension not in IMPORT_EXTENSIONS | {".zip"}:
                raise ValueError("Import accepts ZIP archives, PDFs, JPEG, PNG and TIFF images.")
            path = incoming / f"{index:06d}{extension}"
            file_bytes = 0
            with path.open("wb") as handle:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    file_bytes += len(chunk)
                    upload_bytes += len(chunk)
                    if upload_bytes > IMPORT_MAX_TOTAL_BYTES or (extension != ".zip" and file_bytes > IMPORT_MAX_FILE_BYTES):
                        raise ValueError("Import exceeds the 512 MB per-file or 2 GB total upload limit.")
                    handle.write(chunk)
            uploads.append((path, name))
        metadata = await run_in_threadpool(_expand_import, import_id, uploads)
        imports.set(import_id, stage="done", import_files=metadata)
        shutil.rmtree(incoming)
        return JSONResponse({"import_id": import_id,
                             "files": [{key: value for key, value in entry.items() if key != "path"}
                                       for entry in metadata]})
    except Exception as error:
        message = str(error) if isinstance(error, ValueError) else "Could not import this archive. It may be corrupt or encrypted."
        imports.set(import_id, stage="error", error=message)
        shutil.rmtree(directory, ignore_errors=True)
        return JSONResponse({"error": message}, status_code=400)


@app.get("/api/import/{import_id}/file/{index}")
def imported_file(import_id: str, index: int) -> FileResponse:
    imported = imports.get(import_id)
    entries = imported.get("import_files", []) if imported else []
    if not imported or imported.get("stage") != "done" or index < 0 or index >= len(entries):
        raise HTTPException(404, "Unknown or expired imported file.")
    entry = entries[index]
    try:
        path = Path(entry["path"]).resolve(strict=True)
        directory = (WORK_DIR / import_id / "files").resolve(strict=True)
    except (OSError, RuntimeError):
        raise HTTPException(404, "Imported file has expired.")
    if not path.is_file() or path.parent != directory or path.suffix.lower() not in IMPORT_EXTENSIONS:
        raise HTTPException(404, "Unknown imported file.")
    imports.set(import_id, created_at=_now())
    return FileResponse(path, media_type=entry["type"], filename=entry["name"])


async def _save_uploads(files: List[UploadFile], directory: Path) -> List[Path]:
    paths = []
    for index, upload in enumerate(files):
        raw = Path(upload.filename or f"file_{index}").name
        extension = Path(raw).suffix.lower()
        if extension not in {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
            raise ValueError(f"Unsupported file type: {raw}")
        path = directory / f"{index:04d}_{Path(_safe_filename(raw)).stem}{extension}"
        with path.open("wb") as handle:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        paths.append(path)
    return paths


@app.post("/api/source")
async def stage_source(files: List[UploadFile] = File(...), options_json: str = Form("{}")) -> JSONResponse:
    try:
        options = _normalized_options(json.loads(options_json))
        if not files:
            raise ValueError("No files uploaded.")
    except (ValueError, TypeError) as error:
        return JSONResponse({"error": str(error)}, status_code=400)
    sid = sources.create()
    directory = WORK_DIR / sid
    directory.mkdir(parents=True, exist_ok=True)
    try:
        paths = await _save_uploads(files, directory)
    except Exception as error:
        sources.set(sid, stage="error", error=str(error))
        return JSONResponse({"error": str(error)}, status_code=400)
    sources.set(sid, input_bytes=sum(p.stat().st_size for p in paths), cache={}, active_jobs=[], dpi_fallback=options["dpi_fallback"])
    threading.Thread(target=_run_source, args=(sid, paths, options["dpi_fallback"]), daemon=True).start()
    return JSONResponse({"source_id": sid})


def _run_source(source_id: str, paths: List[Path], dpi: int) -> None:
    try:
        sources.set(source_id, stage="building")
        built = WORK_DIR / source_id / "built.pdf"
        _build_pdf(paths, built, dpi_fallback=dpi,
                   progress_cb=lambda value: sources.set(source_id, progress_build=value))
        with pikepdf.open(built) as document:
            page_count = len(document.pages)
        sources.set(source_id, stage="ready", progress_build=100, page_count=page_count, built_path=str(built))
    except Exception as error:
        sources.set(source_id, stage="error", error=str(error))


@app.get("/api/source/{source_id}")
def source_status(source_id: str) -> dict:
    source = sources.get(source_id)
    if not source:
        raise HTTPException(404, "Unknown or expired source.")
    sources.set(source_id, created_at=_now())
    return {key: source.get(key) for key in ("stage", "progress_build", "page_count", "input_bytes", "error")}


def _ready_source(source_id: str) -> dict:
    source = sources.get(source_id)
    if not source:
        raise HTTPException(404, "Unknown or expired source. Upload the queue again.")
    if source["stage"] != "ready":
        raise HTTPException(409, "Source is not ready.")
    sources.set(source_id, created_at=_now())
    return source


def _request_options(payload: dict) -> dict:
    try:
        return _normalized_options(payload.get("options", payload))
    except (ValueError, TypeError) as error:
        raise HTTPException(400, str(error))


def _source_job(source_id: str, options: dict) -> dict:
    with source_lock:
        source = _ready_source(source_id)
        if options["dpi_fallback"] != source["dpi_fallback"]:
            raise HTTPException(409, "Image DPI changed. Upload the queue again.")
        try:
            _page_ranges(source["page_count"], options["split_count"])
        except ValueError as error:
            raise HTTPException(400, str(error))
        key = hashlib.sha256(json.dumps(options, sort_keys=True).encode()).hexdigest()
        cache = dict(source.get("cache", {}))
        existing = cache.get(key)
        existing_job = jobs.get(existing) if existing else None
        if existing_job and existing_job["stage"] != "error":
            jobs.set(existing, created_at=_now())
            return {"job_id": existing, "cached": True}
        jid = jobs.create()
        directory = WORK_DIR / jid
        directory.mkdir(parents=True, exist_ok=True)
        cache[key] = jid
        sources.set(source_id, cache=cache, active_jobs=[*source.get("active_jobs", []), jid])
        jobs.set(jid, source_id=source_id)
        threading.Thread(target=_run_job, args=(jid, [], options, Path(source["built_path"])), daemon=True).start()
        return {"job_id": jid, "cached": False}


@app.post("/api/source/{source_id}/forge")
def forge_source(source_id: str, payload: dict = Body(...)) -> dict:
    return _source_job(source_id, _request_options(payload))


@app.post("/api/source/{source_id}/preview")
def preview_source(source_id: str, payload: dict = Body(...)) -> dict:
    options = _request_options(payload)
    if payload.get("exact") is True:
        return {"kind": "exact", **_source_job(source_id, options)}
    source = _ready_source(source_id)
    if options["dpi_fallback"] != source["dpi_fallback"]:
        raise HTTPException(409, "Image DPI changed. Upload the queue again.")
    try:
        return _estimate_outputs(Path(source["built_path"]), options)
    except (ValueError, TypeError) as error:
        raise HTTPException(400, str(error))


@app.get("/")
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "favicon.ico", media_type="image/x-icon")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.post("/api/forge")
async def forge(
    files: List[UploadFile] = File(...),
    options_json: str = Form(...),
) -> JSONResponse:
    try:
        options = _normalized_options(json.loads(options_json))
    except Exception:
        return JSONResponse({"error": "Invalid options."}, status_code=400)

    if not files:
        return JSONResponse({"error": "No files uploaded."}, status_code=400)

    jid = jobs.create()
    job_dir = WORK_DIR / jid
    job_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: List[Path] = []
    try:
        saved_paths = await _save_uploads(files, job_dir)
    except Exception as e:
        jobs.set(jid, stage="error", error=f"Upload save failed: {e}")
        shutil.rmtree(job_dir, ignore_errors=True)
        return JSONResponse({"error": "Failed saving uploads."}, status_code=500)

    # Kick off background thread
    t = threading.Thread(target=_run_job, args=(jid, saved_paths, options), daemon=True)
    t.start()

    return JSONResponse({"job_id": jid})


@app.get("/api/job/{job_id}")
def job_status(job_id: str) -> JSONResponse:
    j = jobs.get(job_id)
    if not j:
        return JSONResponse({"error": "Unknown job."}, status_code=404)

    # also run occasional cleanup opportunistically
    jobs.cleanup(older_than_s=3600)
    sources.cleanup_sources(older_than_s=3600)

    return JSONResponse(
        {
            "stage": j["stage"],
            "progress_build": j["progress_build"],
            "progress_compress": j["progress_compress"],
            "output_bytes": j["output_bytes"],
            "diff_bytes": j["diff_bytes"],
            "error": j["error"],
            # Keep these explicit fields for clients which need to show the
            # generated files before initiating the single download endpoint.
            "out_paths": [Path(path).name for path in j.get("out_paths", []) if Path(path).exists()],
            "download_name": j.get("download_name"),
            "target_bytes": j.get("target_bytes"),
            "max_part_bytes": j.get("max_part_bytes"),
            "target_met": j.get("target_met"),
            "phase": j.get("phase"),
            "detail": j.get("detail"),
            "part_index": j.get("part_index", 0),
            "part_count": j.get("part_count", 0),
            "outputs": [
                {
                    "index": index,
                    "job_id": job_id,
                    "name": Path(path).name,
                    "bytes": Path(path).stat().st_size,
                    "preview_url": f"/api/job/{job_id}/preview/{index}",
                    "before_url": f"/api/job/{job_id}/before/{index}",
                    "render_before_url": f"/api/job/{job_id}/render/{index}/{{page}}?variant=before",
                    "render_after_url": f"/api/job/{job_id}/render/{index}/{{page}}?variant=after",
                    **(j.get("output_details", [{}] * len(j.get("out_paths", [])))[index]),
                }
                for index, path in enumerate(j.get("out_paths", []))
                if Path(path).exists()
            ],
        }
    )


@app.get("/api/job/{job_id}/download")
def job_download(job_id: str) -> FileResponse:
    j = jobs.get(job_id)
    if not j or j.get("stage") != "done" or not j.get("out_path"):
        raise HTTPException(status_code=404, detail="Output is not ready.")
    path = Path(j["out_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Output has expired.")
    media_type = "application/zip" if path.suffix.lower() == ".zip" else "application/pdf"
    return FileResponse(path, media_type=media_type, filename=j.get("download_name") or path.name)


@app.get("/api/job/{job_id}/preview/{index}")
def job_preview(job_id: str, index: int) -> FileResponse:
    """Serve one completed PDF part inline for the browser preview pane.

    Indexes are zero-based and only refer to the server-recorded generated
    PDFs. Resolving and checking the parent directory prevents an altered job
    record or path traversal from exposing an arbitrary local file.
    """
    j = jobs.get(job_id)
    if not j or j.get("stage") != "done":
        raise HTTPException(status_code=404, detail="Output is not ready.")
    output_paths = j.get("out_paths", [])
    if index < 0 or index >= len(output_paths):
        raise HTTPException(status_code=404, detail="Unknown output preview.")

    try:
        path = Path(output_paths[index]).resolve(strict=True)
        job_dir = (WORK_DIR / job_id).resolve(strict=True)
    except (OSError, RuntimeError):
        raise HTTPException(status_code=404, detail="Output has expired.")

    if (
        path.suffix.lower() != ".pdf"
        or not path.is_file()
        or path.parent != job_dir
    ):
        raise HTTPException(status_code=404, detail="Unknown output preview.")

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=path.name,
        content_disposition_type="inline",
    )


@app.get("/api/job/{job_id}/before/{index}")
def job_before(job_id: str, index: int) -> FileResponse:
    """Serve the uncompressed pages corresponding to one completed output."""
    job = jobs.get(job_id)
    if not job or job.get("stage") != "done":
        raise HTTPException(404, "Output is not ready.")
    paths = job.get("original_paths", [])
    if index < 0 or index >= len(paths):
        raise HTTPException(404, "Unknown original preview.")
    try:
        path = Path(paths[index]).resolve(strict=True)
        job_dir = (WORK_DIR / job_id).resolve(strict=True)
    except (OSError, RuntimeError):
        raise HTTPException(404, "Original has expired.")
    if path.suffix.lower() != ".pdf" or not path.is_file() or path.parent != job_dir / "originals":
        raise HTTPException(404, "Unknown original preview.")
    return FileResponse(path, media_type="application/pdf", filename=f"original_part_{index + 1:02d}.pdf",
                        content_disposition_type="inline")


def _comparison_page_geometry(path: Path, page: int) -> tuple:
    """Return displayed page size in points, including CropBox/Rotate/UserUnit.

    Ghostscript applies these PDF attributes itself. Reading them here only
    determines a safe resolution; we never rewrite or rasterize the PDF first.
    """
    with pikepdf.open(path) as document:
        if page > len(document.pages):
            raise HTTPException(404, "Page is outside this PDF part.")
        pdf_page = document.pages[page - 1]
        box = [float(value) for value in pdf_page.cropbox]
        unit = float(pdf_page.obj.get("/UserUnit", 1))
        width, height = abs(box[2] - box[0]) * unit, abs(box[3] - box[1]) * unit
        if not all(math.isfinite(value) and value > 0 for value in (unit, width, height)):
            raise HTTPException(422, "This page has invalid dimensions.")
        # Rotate is inheritable through the page tree, unlike UserUnit.
        node = pdf_page.obj
        rotation = 0
        for _ in range(64):
            if "/Rotate" in node:
                rotation = int(node["/Rotate"])
                break
            node = node.get("/Parent")
            if node is None:
                break
        if rotation % 180 == 90:
            width, height = height, width
        return width, height


def _comparison_dpi(paths: Sequence[Path], page: int, requested: int) -> float:
    """Bound BOTH sides to the same DPI, even if their page sizes differ."""
    effective = float(requested)
    dimensions = [_comparison_page_geometry(path, page) for path in paths]
    for width, height in dimensions:
        # Leave a one-pixel margin for Ghostscript's raster rounding.
        effective = min(effective, 8191 * 72 / max(width, height),
                        math.sqrt(19_990_000 / (width * height)) * 72)
    effective = math.floor(effective * 1_000_000) / 1_000_000
    if effective <= 0:
        raise HTTPException(422, "This page is too large to render safely.")
    return effective


@app.get("/api/job/{job_id}/render/{index}/{page}")
def job_render(job_id: str, index: int, page: int,
               variant: Literal["before", "after"] = "after",
               dpi: int = Query(default=144, ge=72, le=576)) -> FileResponse:
    """Render a matching original/output page for the draggable comparison."""
    job = jobs.get(job_id)
    if not job or job.get("stage") != "done":
        raise HTTPException(404, "Output is not ready.")
    paths = job.get("original_paths" if variant == "before" else "out_paths", [])
    if index < 0 or index >= len(paths) or page < 1:
        raise HTTPException(404, "Unknown comparison page.")
    try:
        path = Path(paths[index]).resolve(strict=True)
        job_dir = (WORK_DIR / job_id).resolve(strict=True)
    except (OSError, RuntimeError):
        raise HTTPException(404, "Comparison PDF has expired.")
    allowed_dir = job_dir / "originals" if variant == "before" else job_dir
    if path.suffix.lower() != ".pdf" or not path.is_file() or path.parent != allowed_dir:
        raise HTTPException(404, "Unknown comparison PDF.")
    paired_paths = [path]
    counterpart_paths = job.get("out_paths" if variant == "before" else "original_paths", [])
    if index < len(counterpart_paths):
        try:
            counterpart = Path(counterpart_paths[index]).resolve(strict=True)
        except (OSError, RuntimeError):
            raise HTTPException(404, "Comparison PDF has expired.")
        counterpart_dir = job_dir if variant == "before" else job_dir / "originals"
        if counterpart.suffix.lower() != ".pdf" or not counterpart.is_file() or counterpart.parent != counterpart_dir:
            raise HTTPException(404, "Unknown comparison PDF.")
        paired_paths.append(counterpart)
    effective_dpi = _comparison_dpi(paired_paths, page, dpi)
    dpi_text = f"{effective_dpi:.6f}".rstrip("0").rstrip(".")
    jobs.set(job_id, created_at=_now())
    previews_dir = job_dir / "previews"
    destination = previews_dir / f"{index:04d}_{page:06d}_{variant}_{dpi}_{dpi_text}dpi.png"
    with render_lock:
        if not destination.is_file():
            ghostscript = _find_ghostscript()
            if not ghostscript:
                raise HTTPException(503, "Page comparison requires Ghostscript. Use the PDF comparison instead.")
            previews_dir.mkdir(exist_ok=True)
            temporary = previews_dir / f".{destination.stem}.png"
            command = [ghostscript, "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE",
                       "-sDEVICE=png16m", f"-r{dpi_text}", "-dUseCropBox",
                       "-dTextAlphaBits=4", "-dGraphicsAlphaBits=4",
                       f"-dFirstPage={page}", f"-dLastPage={page}",
                       f"-sOutputFile={temporary}", str(path)]
            try:
                result = _run_pdf_tool(command, timeout=60)
                if result.returncode != 0 or not temporary.is_file():
                    raise HTTPException(503, "Could not render this page. Use the PDF comparison instead.")
                temporary.replace(destination)
            except subprocess.TimeoutExpired:
                raise HTTPException(503, "Page rendering timed out. Use the PDF comparison instead.")
            except OSError:
                raise HTTPException(503, "Ghostscript could not start. Use the PDF comparison instead.")
            finally:
                temporary.unlink(missing_ok=True)
    return FileResponse(destination, media_type="image/png",
                        headers={"Cache-Control": "private, max-age=3600",
                                 "X-Render-DPI": dpi_text,
                                 "X-Render-Requested-DPI": str(dpi),
                                 "X-Render-Limited": str(effective_dpi < dpi).lower()})


def _image_layout(dpi_fallback: int):
    """Create img2pdf's layout callback with a sensible DPI fallback."""
    def layout_fun(imgwidthpx, imgheightpx, ndpi):
        if not ndpi or len(ndpi) < 2 or not ndpi[0] or not ndpi[1]:
            ndpi = (dpi_fallback, dpi_fallback)
        return img2pdf.default_layout_fun(imgwidthpx, imgheightpx, ndpi)

    return layout_fun


def _build_pdf(inputs: List[Path], out_pdf: Path, dpi_fallback: int = 300, progress_cb=None) -> None:
    # Supports: PDFs (preserved) + raster images (losslessly wrapped via img2pdf)
    pdf_inputs = [p for p in inputs if p.suffix.lower() == ".pdf"]
    if not pdf_inputs and all(p.suffix.lower() in (".jpg", ".jpeg", ".png", ".tif", ".tiff") for p in inputs):
        # fast path: all raster images -> one img2pdf call
        if progress_cb:
            progress_cb(10)
        layout_fun = _image_layout(dpi_fallback)
        pdf_bytes = img2pdf.convert([str(p) for p in inputs], layout_fun=layout_fun)
        out_pdf.write_bytes(pdf_bytes)
        if progress_cb:
            progress_cb(100)
        return

    # Mixed path: stitch PDFs + single-image PDFs into one
    dst = pikepdf.Pdf.new()
    n = len(inputs)

    for i, p in enumerate(inputs):
        if progress_cb:
            progress_cb(int((i / max(1, n)) * 95) + 5)

        if p.suffix.lower() == ".pdf":
            with pikepdf.open(p) as src:
                dst.pages.extend(src.pages)
            continue

        # image -> single-page PDF, lossless wrap
        if p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".tif", ".tiff"):
            raise ValueError(f"Unsupported file type: {p.name}")

        layout_fun = _image_layout(dpi_fallback)
        pdf_bytes = img2pdf.convert(str(p), layout_fun=layout_fun)
        with pikepdf.open(io.BytesIO(pdf_bytes)) as imgpdf:
            dst.pages.extend(imgpdf.pages)

    dst.save(out_pdf)
    dst.close()
    if progress_cb:
        progress_cb(100)


def _lossless_optimize(in_pdf: Path, out_pdf: Path, linearize: bool, progress_cb=None) -> None:
    # Lossless PDF optimization using qpdf via pikepdf:
    # - object streams (smallest)
    # - recompress flate streams
    # - generalized stream decode/encode to prefer modern Flate
    with pikepdf.open(in_pdf) as pdf:
        try:
            pdf.remove_unreferenced_resources()
        except Exception:
            pass

        def _p(v: int) -> None:
            if progress_cb:
                progress_cb(int(v))

        pdf.save(
            out_pdf,
            compress_streams=True,
            stream_decode_level=pikepdf.StreamDecodeLevel.generalized,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
            recompress_flate=True,
            linearize=bool(linearize),
            deterministic_id=True,
            progress=_p if progress_cb else None,
        )


def _ghostscript_target_fit(in_pdf: Path, out_pdf: Path, target_bytes: int, linearize: bool, progress_cb=None, detail_cb=None) -> dict:
    """
    Best-effort target fit using Ghostscript *if installed*.
    Keeps vectors/text where possible, but may recompress raster images.
    """
    gs = _find_ghostscript()
    if not gs:
        raise RuntimeError("Target-fit mode requires Ghostscript (gswin64c/gs). Install it or use Lossless mode.")

    # Work down from the highest useful raster resolution in fine enough steps
    # to land just below a target instead of needlessly undershooting it. The
    # explicit JPEG setting keeps encoding reproducible; it is lossy and is
    # not a guarantee of perceptual quality. A 1.0 downsample threshold makes
    # resolution steps effective for scans near a usual threshold.
    quality_factor = 0.99
    temporary_prefix = f".gs-{uuid.uuid4().hex[:8]}-"
    resolutions = [450, 300, 295, 290, 280, 260, 240, 220, 200]
    desired_floor = max(0, target_bytes - 3 * MB)
    attempts = resolutions
    best_any = None    # smallest result if nothing fits
    chosen = None

    total = len(attempts)
    for idx, res in enumerate(attempts, start=1):
        if detail_cb:
            detail_cb("fitting", f"Fitting to size · {res} DPI · pass {idx} of {total}")
        if progress_cb:
            progress_cb(int((idx - 1) / total * 90) + 5)

        tmp_out = out_pdf.with_name(f"{temporary_prefix}{res}dpi_q99.pdf")

        # Note: linearize tends to increase size, so default off in UI.
        # We only linearize on final output if requested.
        cmd = [
            gs,
            "-q",
            "-dNOPAUSE",
            "-dBATCH",
            "-dSAFER",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.7",
            "-dPDFSETTINGS=/prepress",
            # Force photographic recompression when fitting a target. Without
            # these flags, pdfwrite may retain a large PNG/Flate image stream
            # unchanged, making a size target impossible even at low DPI.
            "-dAutoFilterColorImages=false",
            "-dColorImageFilter=/DCTEncode",
            "-dAutoFilterGrayImages=false",
            "-dGrayImageFilter=/DCTEncode",
            "-dDownsampleColorImages=true",
            "-dDownsampleGrayImages=true",
            "-dDownsampleMonoImages=true",
            "-dColorImageDownsampleThreshold=1.0",
            "-dGrayImageDownsampleThreshold=1.0",
            "-dMonoImageDownsampleThreshold=1.0",
            f"-dColorImageResolution={res}",
            f"-dGrayImageResolution={res}",
            f"-dMonoImageResolution={res}",
            f"-sOutputFile={str(tmp_out)}",
            "-c",
            (
                f"<</ColorImageDict <</QFactor {quality_factor}>> "
                f"/GrayImageDict <</QFactor {quality_factor}>> >> setdistillerparams"
            ),
            "-f",
            str(in_pdf),
        ]

        p = _run_pdf_tool(cmd)
        if p.returncode != 0 or not tmp_out.exists():
            raise RuntimeError(
                f"Ghostscript failed (dpi={res}, quality={quality_factor}). "
                f"{p.stderr.strip()[:400]}"
            )

        # Measure the actual final form. Linearization can push an apparently
        # safe intermediate above the requested cap.
        if linearize:
            if detail_cb:
                detail_cb("linearizing", f"Preparing fast web view · {res} DPI candidate")
            finalized = out_pdf.with_name(f"{temporary_prefix}{res}dpi_q99_linearized.pdf")
            _lossless_optimize(tmp_out, finalized, linearize=True)
            tmp_out.unlink()
            tmp_out = finalized
        b = tmp_out.stat().st_size
        if best_any is None or b < best_any[0]:
            best_any = (b, tmp_out)

        if b <= target_bytes:
            # The attempts are ordered from higher to lower resolution, so
            # this is a safe result. Keep the largest safe candidate: it is
            # closest to the user's cap and retains the most detail.
            if chosen is None or b > chosen[0]:
                chosen = (b, tmp_out)
            if b >= desired_floor:
                break

    if not chosen:
        smallest = _fmt_mb(best_any[0]) if best_any else None
        for temporary in out_pdf.parent.glob(f"{temporary_prefix}*.pdf"):
            temporary.unlink(missing_ok=True)
        raise RuntimeError(
            f"Cannot fit this PDF below {target_bytes / MB:g} MB while retaining at least 200 DPI. "
            f"Smallest measured result: {smallest} MB. Increase the cap or number of PDF parts."
        )
    chosen_bytes, chosen_path = chosen

    # Finalize: optional linearize + lossless optimize after gs (optional but helpful)
    shutil.move(str(chosen_path), str(out_pdf))

    # cleanup remaining gs_* files
    for f in out_pdf.parent.glob(f"{temporary_prefix}*.pdf"):
        if f.exists() and f.name != out_pdf.name:
            try:
                f.unlink()
            except Exception:
                pass

    return {"bytes": chosen_bytes, "used_ghostscript": True}


def _page_ranges(page_count: int, split_count: int) -> List[tuple[int, int]]:
    """Return contiguous, balanced page ranges for an exact number of PDFs."""
    if split_count < 1:
        raise ValueError("Split count must be at least 1.")
    if split_count > page_count:
        raise ValueError(
            f"Cannot create {split_count} non-empty PDFs from a {page_count}-page document."
        )

    base, remainder = divmod(page_count, split_count)
    ranges: List[tuple[int, int]] = []
    start = 0
    for index in range(split_count):
        end = start + base + (1 if index < remainder else 0)
        ranges.append((start, end))
        start = end
    return ranges


def _extract_pages(in_pdf: Path, out_pdf: Path, start: int, end: int) -> None:
    """Write a standalone PDF containing pages [start, end), preserving page order."""
    with pikepdf.open(in_pdf) as source:
        result = pikepdf.Pdf.new()
        try:
            result.pages.extend(source.pages[start:end])
            result.save(out_pdf)
        finally:
            result.close()


def _estimate_outputs(source_pdf: Path, options: dict) -> dict:
    """Inspect encoded stream lengths only; never encode/recompress a sample.

    JPEG entropy, vector complexity and final linearization make an exact size
    unknowable without actually producing the file. Bounds intentionally stay
    broad rather than presenting the selected cap as a measured prediction.
    """
    target = int(options["target_mb"] * MB)
    source_bytes = source_pdf.stat().st_size
    with pikepdf.open(source_pdf) as document:
        ranges = _page_ranges(len(document.pages), options["split_count"])
        page_metrics = []
        for page in document.pages:
            images = []
            streams = 0
            seen = set()
            width = abs(float(page.MediaBox[2]) - float(page.MediaBox[0])) or 612
            height = abs(float(page.MediaBox[3]) - float(page.MediaBox[1])) or 792

            def inspect(resources):
                nonlocal streams
                if not resources:
                    return
                for _, resource in resources.get("/XObject", {}).items():
                    ident = resource.objgen
                    if ident in seen:
                        continue
                    seen.add(ident)
                    length = int(resource.get("/Length", 0))
                    streams += length
                    if resource.get("/Subtype") == "/Image":
                        dpi = max(float(resource.get("/Width", 0)) * 72 / width,
                                  float(resource.get("/Height", 0)) * 72 / height, 72)
                        filters = str(resource.get("/Filter", ""))
                        # Existing JPEGs usually have little lossless headroom.
                        # Flate scans often shrink when photographic encoding is used.
                        encoding_ratio = 1.0 if "/DCTDecode" in filters or "/JPXDecode" in filters else 0.40
                        images.append((length, dpi, encoding_ratio))
                    elif resource.get("/Subtype") == "/Form":
                        inspect(resource.get("/Resources"))
            inspect(page.get("/Resources"))
            contents = page.get("/Contents")
            if isinstance(contents, pikepdf.Stream):
                streams += int(contents.get("/Length", 0))
            elif contents is not None:
                streams += sum(int(stream.get("/Length", 0)) for stream in contents)
            page_metrics.append((max(1000, streams), images))
        total_weight = sum(metric[0] for metric in page_metrics) or 1
        outputs = []
        for index, (start, end) in enumerate(ranges):
            metrics = page_metrics[start:end]
            current = max(1000, int(source_bytes * sum(m[0] for m in metrics) / total_weight))
            image_bytes = sum(item[0] for metric in metrics for item in metric[1])
            overhead = max(1000, current - image_bytes)
            projected = current
            confidence = "medium" if options["compress_mode"] == "off" else "low"
            if options["compress_mode"] == "lossless":
                projected = int(current * .97)
            elif options["compress_mode"] == "targetfit" and current > target:
                projected = current
                for dpi in (450, 300, 295, 290, 280, 260, 240, 220, 200):
                    candidate = overhead + sum(int(size * min(1, (dpi / image_dpi) ** 2) * ratio)
                                               for metric in metrics for size, image_dpi, ratio in metric[1])
                    projected = min(projected, candidate)
                    if projected <= target:
                        break
            if options["linearize"]:
                projected = int(projected * 1.005) + 2048
            uncertainty = .12 if confidence == "medium" else .35
            name = options["output_name"] if len(ranges) == 1 else f"{Path(options['output_name']).stem}_part_{index + 1:02d}-of-{len(ranges):02d}.pdf"
            outputs.append({"index": index, "name": name, "bytes": projected,
                            "low_bytes": max(1000, int(projected * (1 - uncertainty))),
                            "high_bytes": int(projected * (1 + uncertainty)),
                            "source_bytes": current, "page_start": start + 1, "page_end": end,
                            "confidence": confidence, "target_likely_met": projected <= target})
    return {"kind": "estimate", "outputs": outputs, "target_bytes": target,
            "note": "Estimated from PDF content without compression. The range is approximate; actual file sizes appear after Forge. Files already below the cap keep their quality and are not enlarged."}


def _finish_pdf(
    source_pdf: Path,
    destination: Path,
    *,
    compress_mode: str,
    target_bytes: int,
    linearize: bool,
    progress_cb=None,
    detail_cb=None,
) -> None:
    """Make one downloadable PDF, applying lossless and optional target-fit work.

    Linearization is deliberately the *last* lossless rewrite.  That makes it
    compatible with every compression choice; previously the lossless/off paths
    silently ignored the Fast web view switch.
    """
    mode = compress_mode if compress_mode in {"off", "lossless", "targetfit"} else "lossless"

    def phase_progress(start: int, end: int):
        if not progress_cb:
            return None
        return lambda value: progress_cb(start + int(max(0, min(100, value)) * (end - start) / 100))

    if mode == "off":
        if linearize:
            if detail_cb:
                detail_cb("linearizing", "Preparing fast web view")
            _lossless_optimize(source_pdf, destination, linearize=True, progress_cb=progress_cb)
        else:
            shutil.copyfile(source_pdf, destination)
            if progress_cb:
                progress_cb(100)
        return

    lossless = destination.with_name(f".{destination.stem}.lossless.pdf")
    if detail_cb:
        detail_cb("optimizing", "Optimizing PDF without quality loss")
    optimize_end = 20 if mode == "targetfit" else 85
    _lossless_optimize(source_pdf, lossless, linearize=False, progress_cb=phase_progress(0, optimize_end))

    try:
        # Avoid a lossy Ghostscript pass when the quality-preserving output is
        # already within the requested per-file target.
        # Linearize the lossless candidate first so its *final* size determines
        # whether a raster recompression pass is actually necessary.
        if linearize:
            if detail_cb:
                detail_cb("linearizing", "Preparing fast web view")
            linearize_end = 30 if mode == "targetfit" else 100
            _lossless_optimize(lossless, destination, linearize=True,
                               progress_cb=phase_progress(optimize_end, linearize_end))
            comparison_bytes = destination.stat().st_size
        else:
            comparison_bytes = lossless.stat().st_size
        needs_target_fit = mode == "targetfit" and comparison_bytes > target_bytes
        if needs_target_fit:
            _ghostscript_target_fit(
                lossless,
                destination,
                target_bytes=target_bytes,
                linearize=linearize,
                progress_cb=phase_progress(30, 99),
                detail_cb=detail_cb,
            )
            if progress_cb:
                progress_cb(100)
        elif linearize:
            if progress_cb:
                progress_cb(100)
        else:
            shutil.move(str(lossless), str(destination))
            if progress_cb:
                progress_cb(100)
    finally:
        if lossless.exists():
            lossless.unlink()


def _zip_outputs(output_paths: Sequence[Path], archive_path: Path) -> None:
    """Put split PDF files in a portable single-download archive."""
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in output_paths:
            archive.write(path, arcname=path.name)


def _run_job(job_id: str, paths: List[Path], options: dict, staged_pdf: Optional[Path] = None) -> None:
    job_dir = WORK_DIR / job_id

    try:
        options = _normalized_options(options)
        output_name = _safe_filename(str(options.get("output_name", "CometForge.pdf")))
        compress_mode = str(options.get("compress_mode", "lossless")).lower().strip()
        if compress_mode in {"none", "false", "0"}:
            compress_mode = "off"
        # "target_mb" is deliberately per generated PDF. This is important
        # for workflows such as a 200 MB document split into five <=20 MB PDFs.
        target_mb = float(options.get("target_mb", 19.5) or 19.5)
        linearize = bool(options.get("linearize", False))
        dpi_fallback = int(options.get("dpi_fallback", 300) or 300)
        # Accept the names used by earlier clients as well as split_count.
        raw_split_count = options.get(
            "split_count",
            options.get("split_parts", options.get("split_files", 1)),
        )
        # An explicit false wins over a stale/default count sent by an older
        # client, so a regular one-to-four-page job never fails just because
        # the UI happened to retain a "5" in its split-count input.
        split_enabled = options.get("split_enabled")
        if split_enabled is False:
            split_count = 1
        else:
            if isinstance(raw_split_count, bool):
                raw_split_count = 5 if raw_split_count else 1
            split_count = int(raw_split_count or 1)
        target_bytes = int(max(1.0, target_mb) * MB)
        built_pdf = job_dir / ".built.pdf"

        jobs.set(job_id, stage="building", phase="building", detail="Preparing document pages",
                 progress_build=0, progress_compress=0, error=None)

        def build_progress(p: int) -> None:
            jobs.set(job_id, progress_build=max(0, min(100, int(p))))

        if staged_pdf is None:
            _build_pdf(paths, built_pdf, dpi_fallback=dpi_fallback, progress_cb=build_progress)
        else:
            # The queue was already assembled once during upload. Reuse it
            # read-only across previews/forges instead of uploading/building again.
            built_pdf = staged_pdf
        jobs.set(job_id, progress_build=100)

        with pikepdf.open(built_pdf) as built:
            page_count = len(built.pages)
        ranges = _page_ranges(page_count, split_count)
        jobs.set(job_id, stage="compressing", progress_compress=0, part_count=split_count)

        output_paths: List[Path] = []
        original_paths: List[Path] = []
        output_details: List[dict] = []
        originals_dir = job_dir / "originals"
        originals_dir.mkdir(exist_ok=True)
        for index, (start, end) in enumerate(ranges, start=1):
            jobs.set(job_id, phase="splitting", detail=f"Preparing pages {start + 1}–{end}", part_index=index)
            if split_count == 1:
                final_pdf = job_dir / output_name
                source_pdf = originals_dir / "part_01.pdf"
                # Keep originals with this job, even after its staged source expires.
                # A hard link avoids duplicating a large PDF on the same disk.
                try:
                    if built_pdf.resolve() == final_pdf.resolve():
                        shutil.copyfile(built_pdf, source_pdf)
                    else:
                        os.link(built_pdf, source_pdf)
                except OSError:
                    shutil.copyfile(built_pdf, source_pdf)
            else:
                part_name = f"{Path(output_name).stem}_part_{index:02d}-of-{split_count:02d}.pdf"
                final_pdf = job_dir / part_name
                source_pdf = originals_dir / f"part_{index:02d}.pdf"
                _extract_pages(built_pdf, source_pdf, start, end)

            start_progress = int((index - 1) * 100 / split_count)
            end_progress = int(index * 100 / split_count)

            def compress_progress(progress: int, low=start_progress, high=end_progress) -> None:
                mapped = low + int(max(0, min(100, int(progress))) * (high - low) / 100)
                jobs.set(job_id, progress_compress=mapped)

            _finish_pdf(
                source_pdf,
                final_pdf,
                compress_mode=compress_mode,
                target_bytes=target_bytes,
                linearize=linearize,
                progress_cb=compress_progress,
                detail_cb=lambda phase, detail: jobs.set(job_id, phase=phase, detail=detail),
            )
            output_paths.append(final_pdf)
            original_paths.append(source_pdf)
            original_bytes = source_pdf.stat().st_size
            output_details.append({"original_bytes": original_bytes, "before_bytes": original_bytes,
                                   "page_start": start + 1, "page_end": end, "page_count": end - start})

        max_part_bytes = max(path.stat().st_size for path in output_paths)
        if split_count == 1:
            download_path = output_paths[0]
            download_name = output_name
            diff_bytes = max_part_bytes - target_bytes
        else:
            jobs.set(job_id, phase="packaging", detail="Packaging PDF files for download")
            download_name = _safe_archive_name(output_name)
            download_path = job_dir / download_name
            _zip_outputs(output_paths, download_path)
            # Report whether the largest individual PDF reached the per-file
            # goal, rather than comparing the ZIP's total to one part's goal.
            diff_bytes = max_part_bytes - target_bytes

        jobs.set(
            job_id,
            stage="done",
            phase="done",
            detail="Export complete",
            progress_compress=100,
            output_bytes=download_path.stat().st_size,
            diff_bytes=diff_bytes,
            out_path=str(download_path),
            out_paths=[str(path) for path in output_paths],
            original_paths=[str(path) for path in original_paths],
            output_details=output_details,
            download_name=download_name,
            target_bytes=target_bytes,
            max_part_bytes=max_part_bytes,
            target_met=max_part_bytes <= target_bytes,
        )

    except Exception as e:
        jobs.set(job_id, stage="error", phase="error", detail=str(e), error=str(e))
        # keep folder for debugging, but you can uncomment cleanup if desired
        # shutil.rmtree(job_dir, ignore_errors=True)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="127.0.0.1", port=5173, reload=False)
