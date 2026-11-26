/* Live, print-accurate source preview, using the same layout engine as export. */
(() => {
  const api = window.CometForge;
  if (!api || !window.CometForgeSources) return;
  const dialog = document.createElement('dialog');
  dialog.id = 'sourcePreviewDialog'; dialog.className = 'sourcePreviewDialog';
  dialog.setAttribute('aria-labelledby','sourcePreviewTitle');
  dialog.innerHTML = `
    <header class="sourcePreviewHeader"><div><h2 id="sourcePreviewTitle">Page preview</h2><p id="sourcePreviewSubtitle">Changes apply to your export.</p></div><button id="sourcePreviewClose" class="btn sourcePreviewClose" type="button" aria-label="Close source preview"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg></button></header>
    <div class="sourcePreviewBody"><section class="sourcePreviewDocument" aria-label="Live page preview"><div class="sourcePreviewToolbar"><button id="sourcePreviewPrev" class="btn small" type="button" aria-label="Previous source page">Previous</button><span id="sourcePreviewPage" aria-live="polite">Page 1</span><button id="sourcePreviewNext" class="btn small" type="button" aria-label="Next source page">Next</button><span class="sourcePreviewToolbarSpace"></span><button id="sourcePreviewRotateLeft" class="btn small" type="button" aria-label="Rotate this page counterclockwise"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M3 10a9 9 0 1 1 2 8M3 4v6h6"/></svg>Left</button><button id="sourcePreviewRotateRight" class="btn small" type="button" aria-label="Rotate this page clockwise"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M21 10a9 9 0 1 0-2 8M21 4v6h-6"/></svg>Right</button></div><div id="sourcePreviewStage" class="sourcePreviewStage" aria-busy="true"><img id="sourcePreviewImage" alt="Selected page with the current export layout" hidden><div class="sourcePreviewPlaceholder" aria-hidden="true"><span></span><span></span><span></span></div></div><p id="sourcePreviewStatus" class="sourcePreviewStatus" role="status" aria-live="polite">Preparing page preview…</p></section><aside class="sourcePreviewInspector" aria-label="Live page layout"><h3>Page layout</h3><p>Changes are shown here and saved to your export.</p><div id="sourcePreviewControls"></div><p class="sourcePreviewNote">Paper settings apply to every page. Left and Right turn only the page you’re viewing. Unused space is white.</p><button id="sourcePreviewDone" class="btn primary" type="button">Done</button></aside></div>`;
  document.body.append(dialog);
  const id = name => document.getElementById(name);
  const image = id('sourcePreviewImage'), status = id('sourcePreviewStatus'), stage = id('sourcePreviewStage');
  let selectedId = null, localPage = 1, pageCount = 1, combinedPage = null;
  let revision = 0, timer, controller, blobUrl = null, opener = null, lastSignature = null;
  let busy = false;
  const controls = [];
  const fields = [
    ['pageSize','sourcePreviewSize','Page size'],['pageOrientation','sourcePreviewOrientation','Orientation'],
    ['pageFit','sourcePreviewFit','Content fit'],['pageMargin','sourcePreviewMargin','Margins'],
    ['marginMm','sourcePreviewMarginMm','Custom margin (mm)'],['pageRotation','sourcePreviewRotation','Rotate all pages'],
  ];
  for (const [sourceId,targetId,title] of fields) {
    const source = id(sourceId), target = source.cloneNode(true);
    const field = document.createElement('div'); field.className = 'sourcePreviewField';
    const label = document.createElement('label'); label.htmlFor = targetId; label.textContent = title;
    target.id = targetId; target.hidden = false; target.value = source.value;
    target.removeAttribute('aria-labelledby');
    target.setAttribute('aria-label',title);
    field.append(label,target); id('sourcePreviewControls').append(field);
    const commit = () => {
      if (target.type === 'number') {
        if (!target.checkValidity()) { target.reportValidity(); return; }
      }
      if (source.value !== target.value) { source.value = target.value; source.dispatchEvent(new Event('change',{bubbles:true})); }
    };
    target.addEventListener('change',commit);
    if (target.type === 'number') target.addEventListener('input',commit);
    if (target.tagName === 'SELECT') api.setupPopupSelect(target);
    controls.push({source,target,field});
  }
  function synchronizeControls() {
    for (const {source,target,field} of controls) {
      if (target.value !== source.value) { target.value = source.value; target.dispatchEvent(new Event('change')); }
      field.hidden = source.id === 'marginMm' && id('pageMargin').value !== 'custom';
      const trigger = id(`${target.id}Trigger`);
      target.disabled = busy; if (trigger) trigger.disabled = busy;
    }
    id('sourcePreviewRotateLeft').disabled = busy || combinedPage === null;
    id('sourcePreviewRotateRight').disabled = busy || combinedPage === null;
    id('sourcePreviewPrev').disabled = localPage <= 1;
    id('sourcePreviewNext').disabled = localPage >= pageCount;
  }
  function layoutOptions() {
    return {...window.CometForgeLayout.getOptions(),source_rotations:api.getSnapshot().options.source_rotations};
  }
  function signature() {
    return JSON.stringify({sources:api.getSources().map(source=>source.id),selectedId,localPage,options:layoutOptions()});
  }
  function cancel() {
    revision += 1; clearTimeout(timer); controller?.abort(); controller = null;
  }
  function schedule(immediate=false) {
    if (!dialog.open) return;
    synchronizeControls();
    const next = signature();
    if (!immediate && lastSignature === next) return;
    lastSignature = next;
    cancel();
    stage.setAttribute('aria-busy','true'); stage.classList.add('updating');
    status.textContent = 'Updating page layout…';
    timer = setTimeout(render,immediate ? 0 : 150);
  }
  async function render() {
    const token = revision;
    const sources = api.getSources(), index = sources.findIndex(source=>source.id === selectedId);
    if (index < 0) { close(); return; }
    try {
      const state = api.getSnapshot();
      const metadata = await window.CometForgeSources.ensureDetails(state);
      if (token !== revision || !dialog.open) return;
      pageCount = metadata.sourcePageCounts[index] || 1;
      localPage = Math.max(1,Math.min(localPage,pageCount));
      combinedPage = metadata.sourcePageCounts.slice(0,index).reduce((sum,count)=>sum+count,0) + localPage;
      id('sourcePreviewPage').textContent = `Page ${localPage} of ${pageCount}`;
      id('sourcePreviewSubtitle').textContent = `${sources[index].name} · Page ${combinedPage} in the combined PDF`;
      synchronizeControls();
      controller = new AbortController();
      const response = await fetch(`/api/source/${metadata.sourceId}/render`,{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({page:combinedPage,dpi:120,options:layoutOptions()}),signal:controller.signal,
      });
      if (!response.ok) {
        const result = await response.json().catch(()=>({}));
        throw new Error(result.detail || result.error || 'The page preview could not be rendered.');
      }
      const blob = await response.blob();
      if (token !== revision || !dialog.open) return;
      const nextUrl = URL.createObjectURL(blob);
      const loaded = new Image(); loaded.src = nextUrl;
      try { await loaded.decode(); } catch { URL.revokeObjectURL(nextUrl); throw new Error('The page preview image could not be loaded.'); }
      if (token !== revision || !dialog.open) { URL.revokeObjectURL(nextUrl); return; }
      const previous = blobUrl; blobUrl = nextUrl; image.src = nextUrl; image.hidden = false;
      image.dataset.page = String(combinedPage); image.dataset.revision = String(token);
      image.dataset.options = JSON.stringify(layoutOptions());
      image.dataset.widthPoints = response.headers.get('X-Page-Width') || '';
      image.dataset.heightPoints = response.headers.get('X-Page-Height') || '';
      if (previous) URL.revokeObjectURL(previous);
      stage.classList.remove('updating'); stage.setAttribute('aria-busy','false');
      const width = Number(image.dataset.widthPoints), height = Number(image.dataset.heightPoints);
      const dimensions = width && height ? ` · ${(width * 25.4 / 72).toFixed(1)} × ${(height * 25.4 / 72).toFixed(1)} mm` : '';
      status.textContent = `Live layout preview${dimensions}. Export uses these same settings.`;
      dialog.dispatchEvent(new CustomEvent('cometforge:preview-rendered',{detail:{page:combinedPage,options:layoutOptions()}}));
    } catch (error) {
      if (token !== revision || error.name === 'AbortError' || !dialog.open) return;
      stage.classList.remove('updating'); stage.setAttribute('aria-busy','false');
      image.hidden = true; status.textContent = `${error.message} Your sources and layout settings are still available.`;
    }
  }
  function open(sourceId,trigger) {
    if (busy) return;
    const source = api.getSources().find(entry=>entry.id === sourceId);
    if (!source) return;
    opener = trigger || document.activeElement; selectedId = sourceId;
    localPage = 1; pageCount = 1; combinedPage = null; lastSignature = null;
    image.hidden = true; image.removeAttribute('src');
    id('sourcePreviewTitle').textContent = source.name;
    id('sourcePreviewSubtitle').textContent = 'Preparing source pages…';
    document.dispatchEvent(new CustomEvent('cometforge:closemenus'));
    if (!dialog.open) dialog.showModal();
    synchronizeControls();
    window.CometForgeMotion?.reveal(dialog);
    id('sourcePreviewClose').focus(); schedule(true);
  }
  function cleanup() {
    cancel(); lastSignature = null;
    document.dispatchEvent(new CustomEvent('cometforge:closemenus'));
    if (blobUrl) URL.revokeObjectURL(blobUrl);
    blobUrl = null; image.removeAttribute('src'); image.hidden = true;
    const focus = opener?.isConnected ? opener : document.querySelector(`.item[data-id="${selectedId}"] .sourceThumbButton`);
    focus?.focus({preventScroll:true}); selectedId = null;
  }
  function close() { if (dialog.open) dialog.close(); }
  dialog.addEventListener('close',cleanup);
  dialog.addEventListener('cancel',event=>{
    // Escape dismisses an open control menu before closing the preview itself.
    if (dialog.querySelector('.popupMenu:not(.hidden)')) { event.preventDefault(); document.dispatchEvent(new CustomEvent('cometforge:closemenus')); }
  });
  dialog.addEventListener('click',event=>{ if (event.target === dialog) { const box=dialog.getBoundingClientRect(); if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)close(); } });
  id('sourcePreviewClose').addEventListener('click',close); id('sourcePreviewDone').addEventListener('click',close);
  id('sourcePreviewPrev').addEventListener('click',()=>{ localPage-=1; combinedPage=null; schedule(true); });
  id('sourcePreviewNext').addEventListener('click',()=>{ localPage+=1; combinedPage=null; schedule(true); });
  id('sourcePreviewRotateLeft').addEventListener('click',()=>{ if (combinedPage) window.CometForgeLayout.rotatePage(combinedPage,-90); });
  id('sourcePreviewRotateRight').addEventListener('click',()=>{ if (combinedPage) window.CometForgeLayout.rotatePage(combinedPage,90); });
  window.addEventListener('cometforge:change',()=>schedule());
  window.addEventListener('cometforge:busy',event=>{ busy=Boolean(event.detail); if(dialog.open)synchronizeControls(); });
  window.addEventListener('pagehide',()=>{ cancel(); if(blobUrl)URL.revokeObjectURL(blobUrl); });
  window.CometForgeSourcePreview = {open,close};
})();
