/* Matched-page HD rendering. Only the divider moves; both images align. */
(() => {
  const byId = (id) => document.getElementById(id);
  const view = byId('wipeView'), stage = byId('wipeStage'), canvas = byId('wipeCanvas');
  const before = byId('wipeBefore'), after = byId('wipeAfter'), handle = byId('wipeHandle');
  const status = byId('compareStatus'), pageLabel = byId('comparePage');
  const prev = byId('comparePrev'), next = byId('compareNext'), resolution = byId('compareResolution');
  let file = null, page = 1, divider = 50, zoom = 100, revision = 0, fallback, failed = false;
  let zoomTimer, controller, displayedFile = null, displayedPage = 0, renderedDpi = 0;
  function position(value) {
    divider = Math.max(0, Math.min(100, value));
    after.style.clipPath = `inset(0 0 0 ${divider}%)`;
    handle.style.left = `${divider}%`;
    handle.setAttribute('aria-valuenow', String(Math.round(divider)));
    handle.setAttribute('aria-valuetext', `${Math.round(divider)} percent original visible`);
  }
  function requestedDpi() {
    if (resolution.value === 'standard') return 144;
    const density = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
    return Math.min(576, Math.max(288, Math.ceil(144 * density * zoom / 100 / 72) * 72));
  }
  function renderNote(dpi, limited) {
    return `${resolution.value === 'standard' ? 'Standard' : 'HD'} · ${Number(dpi.toFixed(1))} DPI${limited ? ' · large-page safety limit' : ''}. Drag the divider to compare the same page.`;
  }
  function setZoom(value, reload = true) {
    zoom = Math.max(50, Math.min(400, value)); canvas.style.width = `${zoom}%`;
    byId('compareFit').textContent = zoom === 100 ? 'Fit' : `${zoom}% · Fit`;
    clearTimeout(zoomTimer);
    if (reload && file && requestedDpi() !== renderedDpi) {
      // Reject in-flight lower-resolution results as soon as the zoom changes.
      revision += 1; controller?.abort();
      zoomTimer = setTimeout(() => void loadPage(true), 180);
    }
  }
  async function imageUrl(variant, token, renderFile, renderPage, dpi, signal) {
    const response = await fetch(`${renderFile.renderBase}/${renderPage}?variant=${variant}&dpi=${dpi}`, {signal});
    if (!response.ok) {
      let message = 'Page renderer is unavailable.';
      try { const body = await response.json(); message = body.detail || body.error || message; } catch {}
      throw new Error(message);
    }
    const dpiHeader = response.headers.get('X-Render-DPI');
    if (!dpiHeader && dpi > 144) throw new Error('Restart this instance to enable HD rendering.');
    const blob = await response.blob();
    if (token !== revision) return null;
    return {url: URL.createObjectURL(blob), dpi: Number(dpiHeader) || dpi,
      limited: response.headers.get('X-Render-Limited') === 'true'};
  }
  function releaseImages() {
    [before, after].forEach((image) => { const src = image.getAttribute('src'); if (src?.startsWith('blob:')) URL.revokeObjectURL(src); image.removeAttribute('src'); });
  }
  async function loadPage(preserve = false) {
    clearTimeout(zoomTimer);
    if (!file) return;
    failed = false; controller?.abort(); controller = new AbortController();
    const signal = controller.signal, token = ++revision;
    const renderFile = file, renderPage = page, dpi = requestedDpi();
    if (!(preserve && displayedFile === file && displayedPage === page)) {
      releaseImages(); canvas.classList.add('hidden');
    }
    const total = file.pageCount || 1;
    pageLabel.textContent = `Page ${page} of ${total}`;
    prev.disabled = page <= 1; next.disabled = page >= total;
    status.textContent = `Rendering matching pages at ${dpi} DPI…`;
    let images = [];
    try {
      const results = await Promise.allSettled([
        imageUrl('before', token, renderFile, renderPage, dpi, signal),
        imageUrl('after', token, renderFile, renderPage, dpi, signal),
      ]);
      images = results.map((result) => result.status === 'fulfilled' ? result.value : null);
      const error = results.find((result) => result.status === 'rejected');
      if (token !== revision) return;
      if (error) throw error.reason;
      if (images.some((image) => !image)) return;
      // Decode both offscreen so a new render never pairs new and old images.
      const loaders = images.map((image) => { const loader = new Image(); loader.src = image.url; return loader; });
      await Promise.all(loaders.map((image) => image.decode()));
      if (token !== revision) return;
      if (loaders[0].naturalWidth !== loaders[1].naturalWidth || loaders[0].naturalHeight !== loaders[1].naturalHeight ||
          images[0].dpi !== images[1].dpi) throw new Error('Page geometry differs; showing the PDFs instead.');
      releaseImages();
      before.src = images[0].url; after.src = images[1].url;
      renderedDpi = dpi; displayedFile = renderFile; displayedPage = renderPage;
      status.textContent = renderNote(images[0].dpi, images.some((image) => image.limited));
      images = []; // The displayed image elements now own these object URLs.
      canvas.classList.remove('hidden'); position(divider);
    } catch (error) {
      if (token !== revision || error.name === 'AbortError') return;
      failed = true;
      releaseImages();
      status.textContent = `${error.message} Showing the original and output PDFs below.`;
      stage.classList.add('hidden'); fallback?.();
    } finally {
      images.forEach((image) => image?.url && URL.revokeObjectURL(image.url));
    }
  }
  handle.addEventListener('pointerdown', (event) => { event.preventDefault(); handle.focus(); handle.setPointerCapture(event.pointerId); move(event); });
  function move(event) { const rect = canvas.getBoundingClientRect(); if (rect.width > 0) position((event.clientX - rect.left) * 100 / rect.width); }
  handle.addEventListener('pointermove', (event) => { if (handle.hasPointerCapture(event.pointerId)) move(event); });
  handle.addEventListener('pointerup', (event) => { if (handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId); });
  handle.addEventListener('pointercancel', (event) => { if (handle.hasPointerCapture(event.pointerId)) handle.releasePointerCapture(event.pointerId); });
  handle.addEventListener('keydown', (event) => {
    const step = event.shiftKey ? 10 : 1;
    const changes = {ArrowLeft: -step, ArrowRight: step, ArrowDown: -step, ArrowUp: step, PageDown: -10, PageUp: 10};
    if (event.key === 'Home' || event.key === 'End') { event.preventDefault(); position(event.key === 'Home' ? 0 : 100); }
    else if (event.key in changes) { event.preventDefault(); position(divider + changes[event.key]); }
  });
  prev.addEventListener('click', () => { if (page > 1) { page -= 1; stage.classList.remove('hidden'); void loadPage(); } });
  next.addEventListener('click', () => { if (file && page < file.pageCount) { page += 1; stage.classList.remove('hidden'); void loadPage(); } });
  byId('compareZoomOut').addEventListener('click', () => setZoom(zoom - 25));
  byId('compareZoomIn').addEventListener('click', () => setZoom(zoom + 25));
  byId('compareFit').addEventListener('click', () => setZoom(100));
  resolution.addEventListener('change', () => { if (file) { stage.classList.remove('hidden'); void loadPage(true); } });
  window.CometForgeComparison = {
    show(nextFile, onFallback) {
      view.classList.remove('hidden'); fallback = onFallback;
      if (file === nextFile) { if (failed) fallback?.(); return; }
      file = nextFile; page = 1; renderedDpi = 0; stage.classList.remove('hidden'); setZoom(100, false); position(50);
      byId('compareSizes').textContent = `${window.CometForge.fmtMB(file.beforeBytes || 0)} → ${window.CometForge.fmtMB(file.bytes)}`;
      void loadPage();
    },
    clear() {
      revision += 1; controller?.abort(); clearTimeout(zoomTimer); file = null;
      displayedFile = null; displayedPage = 0; renderedDpi = 0;
      releaseImages(); view.classList.add('hidden');
    },
  };
})();
