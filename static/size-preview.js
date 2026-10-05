/* Quick metadata estimates; only Forge runs compression. */
(() => {
  const api = window.CometForge;
  if (!api) return;
  const status = document.getElementById('sizePreviewStatus');
  const list = document.getElementById('sizePreviewList');
  const summary = document.getElementById('estimateSummary');
  const estimateButton = document.getElementById('previewSizeBtn');
  const forgeButton = document.getElementById('forgeBtn');
  const sourceCache = new Map();
  const identities = new WeakMap();
  let nextIdentity = 1;
  let timer;
  let generation = 0;
  let pendingEstimate = false;
  let estimateRunning = false;

  const mb = (bytes) => `${(bytes / 1_000_000).toFixed(2)} MB`;
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const snapshot = () => api.getSnapshot();
  function queueKey(files) {
    return files.map((file) => {
      if (!identities.has(file)) identities.set(file, nextIdentity++);
      return identities.get(file);
    }).join(',');
  }
  function signature(state) {
    return `${queueKey(state.files)}:${JSON.stringify(state.options)}`;
  }
  async function request(url, init) {
    const response = await fetch(url, init);
    const body = await response.json();
    if (!response.ok) {
      const error = new Error(body.error || body.detail || 'Size calculation failed.');
      error.status = response.status;
      throw error;
    }
    return body;
  }
  function render(outputs, exact, note) {
    const max = Math.max(0, ...outputs.map((output) => output.bytes || 0));
    summary.textContent = outputs.length ? `≈ ${mb(max)}${outputs.length > 1 ? ' max' : ''}` : 'No outputs';
    list.replaceChildren(...outputs.map((output) => {
      const row = document.createElement('div');
      row.className = 'sizePreviewItem';
      const name = document.createElement('span');
      name.textContent = output.name;
      name.title = output.name;
      const size = document.createElement('span');
      size.textContent = exact ? mb(output.bytes) : `≈ ${mb(output.bytes)}`;
      row.append(name, size);
      if (!exact) {
        const range = document.createElement('small');
        range.textContent = `${mb(output.low_bytes)}–${mb(output.high_bytes)} · ${output.confidence || 'estimated'} confidence`;
        row.append(range);
      }
      return row;
    }));
    status.textContent = note;
  }
  async function ensureSource(state) {
    const key = queueKey(state.files);
    let promise = sourceCache.get(key);
    if (!promise) {
      promise = (async () => {
        const body = new FormData();
        state.files.forEach((file) => body.append('files', file, file.name));
        body.append('options_json', JSON.stringify({dpi_fallback: 300}));
        const result = await request('/api/source', {method: 'POST', body});
        while (true) {
          const source = await request(`/api/source/${result.source_id}`);
          if (source.stage === 'ready') return result.source_id;
          if (source.stage === 'error') throw new Error(source.error || 'Could not read these files.');
          await sleep(400);
        }
      })();
      sourceCache.set(key, promise);
      promise.catch(() => sourceCache.delete(key));
    }
    return promise;
  }
  async function sourceRequest(state, operation, options) {
    for (let attempt = 0; attempt < 2; attempt += 1) {
      const source = await ensureSource(state);
      try {
        return await request(`/api/source/${source}/${operation}`, {
          method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(options),
        });
      } catch (error) {
        // A restarted local service or expired upload can be recovered without
        // clearing the user's queue or asking them to select files again.
        if (error.status !== 404 || attempt === 1) throw error;
        sourceCache.delete(queueKey(state.files));
      }
    }
  }
  async function estimate() {
    if (estimateRunning) { pendingEstimate = true; return; }
    const state = snapshot();
    if (!state.files.length) return;
    const revision = generation;
    estimateRunning = true;
    summary.textContent = 'Updating…';
    pendingEstimate = false;
    status.textContent = 'Reading document content to estimate output sizes…';
    try {
      const source = await ensureSource(state);
      if (revision !== generation) return;
      const result = await sourceRequest(state, 'preview', {...state.options, exact: false});
      if (revision === generation) render(result.outputs, false, result.note || 'Estimated from image and PDF metadata. Actual sizes appear after Forge.');
    } catch (error) {
      if (revision === generation) { status.textContent = error.message; summary.textContent = 'Unavailable'; }
    } finally {
      estimateRunning = false;
      if (pendingEstimate) { pendingEstimate = false; void estimate(); }
    }
  }
  function changed() {
    generation += 1;
    clearTimeout(timer);
    list.replaceChildren();
    const state = snapshot();
    estimateButton.disabled = !state.files.length;
    summary.textContent = state.files.length ? 'Updating…' : 'Add files';
    status.textContent = state.files.length ? 'Size estimates are updating for these settings…' : 'Add files to see an estimated size range for every output.';
    if (state.files.length) timer = setTimeout(estimate, 750);
  }
  estimateButton.addEventListener('click', () => { clearTimeout(timer); void estimate(); });
  window.addEventListener('cometforge:change', changed);
  forgeButton.addEventListener('click', async (event) => {
    event.stopImmediatePropagation();
    const state = snapshot();
    if (!state.files.length) { document.getElementById('status').textContent = 'Add files first.'; return; }
    if (forgeButton.disabled) return;
    forgeButton.disabled = true;
    window.dispatchEvent(new CustomEvent('cometforge:busy', {detail: true}));
    document.getElementById('status').textContent = 'Preparing export…';
    document.getElementById('partProgress').textContent = 'Preparing export…';
    document.getElementById('progressWrap').classList.remove('hidden');
    try {
      const result = await sourceRequest(state, 'forge', state.options);
      await api.pollJob(result.job_id, state.options);
    } catch (error) { document.getElementById('status').textContent = error.message; }
    finally { forgeButton.disabled = false; window.dispatchEvent(new CustomEvent('cometforge:busy', {detail: false})); }
  }, true);
  changed();
})();
