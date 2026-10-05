/* External files enter once, anywhere; native queue drags keep their own flow. */
(() => {
  const api = window.CometForge, notice = document.getElementById('globalDropNotice');
  const supported = (name) => /\.(pdf|jpe?g|png|tiff?)$/i.test(name || '');
  const archive = (file) => /\.zip$/i.test(file.name || '');
  let chain = Promise.resolve();
  async function walk(entry) {
    if (entry.isFile) return new Promise((resolve, reject) => entry.file((file) => resolve(supported(file.name) || archive(file) ? [file] : []), reject));
    if (!entry.isDirectory) return [];
    const reader = entry.createReader(), files = [];
    while (true) {
      const children = await new Promise((resolve, reject) => reader.readEntries(resolve, reject));
      if (!children.length) break;
      for (const child of children) files.push(...await walk(child));
    }
    return files;
  }
  async function unpack(zipFiles) {
    const body = new FormData(); zipFiles.forEach((file) => body.append('files', file, file.name));
    const response = await fetch('/api/import', {method:'POST', body});
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || result.error || 'ZIP import failed.');
    const entries = (result.files || []).filter((entry) => supported(entry.name));
    const files = new Array(entries.length); let next = 0, complete = 0;
    async function worker() {
      while (next < entries.length) {
        const index = next++, entry = entries[index];
        const download = await fetch(entry.url);
        if (!download.ok) throw new Error(`Could not read ${entry.name} from the ZIP.`);
        const blob = await download.blob();
        files[index] = new File([blob], entry.name.split(/[\\/]/).pop(), {type:entry.type || blob.type, lastModified:Number(entry.last_modified) || 0});
        complete += 1; api.setHint(`Importing ZIP · ${complete} of ${entries.length} files`);
      }
    }
    await Promise.all(Array.from({length:Math.min(6, entries.length)},worker));
    return files;
  }
  async function run(files) {
    const valid = files.filter((file) => supported(file.name) || archive(file));
    if (!valid.length) { api.setHint('No supported files found. Choose PDFs, JPGs, PNGs, TIFFs or ZIPs.'); return; }
    window.CometForgeTour?.close();
    api.closeResults();
    try {
      api.setHint('Reading imported files…');
      const plain = valid.filter((file) => !archive(file)), zips = valid.filter(archive);
      const expanded = zips.length ? await unpack(zips) : [];
      await api.addFiles([...plain,...expanded]);
      api.setHint(`Added ${plain.length + expanded.length} files${zips.length ? ` from ${zips.length} ZIP${zips.length === 1 ? '' : 's'} and your selection` : ''}.`);
    } catch (error) { api.setHint(error.message || 'Import failed.'); }
  }
  function files(values) { const selection = Array.from(values || []); chain = chain.then(() => run(selection)); return chain; }
  function external(event) { return !api.dragActive() && Array.from(event.dataTransfer?.types || []).includes('Files'); }
  function hide() { notice.classList.add('hidden'); document.body.classList.remove('globalDragging'); }
  ['dragenter','dragover'].forEach((name) => document.addEventListener(name, (event) => {
    if (!external(event)) return;
    event.preventDefault(); if (event.dataTransfer) event.dataTransfer.dropEffect='copy';
    notice.classList.remove('hidden'); document.body.classList.add('globalDragging');
  }, true));
  document.addEventListener('dragleave', (event) => { if (!event.relatedTarget) hide(); }, true);
  document.addEventListener('dragend',hide,true);
  document.addEventListener('drop', (event) => {
    if (!external(event)) return;
    event.preventDefault(); event.stopPropagation(); hide();
    // Read browser entries now; some browsers invalidate the transfer after await.
    const entries = Array.from(event.dataTransfer.items || []).map((item) => item.webkitGetAsEntry?.()).filter(Boolean);
    const selected = Array.from(event.dataTransfer.files || []);
    if (!entries.length) { void files(selected); return; }
    void Promise.all(entries.map(walk)).then((groups) => files(groups.flat())).catch((error) => api.setHint(error.message || 'Could not read the folder. Use the Folder button.'));
  }, true);
  const picker = document.getElementById('folderInput');
  document.getElementById('pickFolderBtn').addEventListener('click',()=>picker.click());
  picker.addEventListener('change',(event)=>{const selected=Array.from(event.target.files || []);event.target.value='';void files(selected);});
  window.CometForgeImport = {files,walk};
})();
