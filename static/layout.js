/* Page geometry is shared by staged estimates, Forge and the review summary. */
(() => {
  const id = name => document.getElementById(name);
  const pageRotations = {};
  const dimensions = {a0:[841,1189],a1:[594,841],a2:[420,594],b4:[250,353],photo4x6:[101.6,152.4],photo5x7:[127,177.8],a3:[297,420],a4:[210,297],a5:[148,210],a6:[105,148],letter:[215.9,279.4],legal:[215.9,355.6],tabloid:[279.4,431.8],executive:[184.15,266.7],b5:[176,250]};
  let busy = false;
  let pageCount = null;
  let sourceFiles = [];
  function getOptions() {
    return {
      page_size:id('pageSize').value, orientation:id('pageOrientation').value, fit:id('pageFit').value,
      margin:id('pageMargin').value, margin_mm:Math.max(0, Math.min(100, Number(id('marginMm').value) || 0)),
      rotation:Number(id('pageRotation').value), page_rotations:{...pageRotations},
    };
  }
  function changed() { refresh(); window.dispatchEvent(new Event('cometforge:change')); }
  function refresh() {
    const options = getOptions();
    id('customMarginField').hidden = options.margin !== 'custom';
    const helps = {contain:'Fit inside keeps the whole page visible. Any unused space stays white.', cover:'Fill covers the sheet and crops content at the edges. Margins stay white.', actual:'Actual size keeps the original scale. Content outside the sheet is cropped.'};
    id('layoutFitHelp').textContent = options.page_size === 'original' && options.orientation === 'auto' ? 'Original size follows each source page after rotation. Margins add white space around it.' : helps[options.fit];
    const size = [...(dimensions[options.page_size] || [210,297])];
    if (options.orientation === 'landscape') size.reverse();
    id('layoutPaper').style.aspectRatio = `${size[0]} / ${size[1]}`;
    const margin = {none:0,small:5,medium:10,large:20,custom:options.margin_mm}[options.margin];
    id('layoutPaper').style.padding = `${Math.min(40, margin / size[0] * 100)}%`;
    id('layoutContent').style.transform = `rotate(${options.rotation}deg)`;
    const count = Object.keys(pageRotations).length;
    id('pageRotationStatus').textContent = count ? `${count} page${count === 1 ? '' : 's'} with additional rotation. Reset before changing queue order.` : '';
    id('resetPageRotations').disabled = busy || !count;
  }
  function rotateAll(degrees) {
    id('pageRotation').value = String((Number(id('pageRotation').value) + degrees + 360) % 360);
    id('pageRotation').dispatchEvent(new Event('change', {bubbles:true}));
  }
  function parsePages(value) {
    const pages = new Set();
    if (!value.trim()) throw new Error('Enter page numbers, such as 1, 3–5.');
    for (const part of value.split(',')) {
      const match = part.trim().match(/^(\d+)(?:\s*[-–]\s*(\d+))?$/);
      if (!match) throw new Error('Use page numbers or ranges separated by commas, such as 1, 3–5.');
      const first = Number(match[1]), last = Number(match[2] || match[1]);
      if (first < 1 || last < first || last > 10000) throw new Error('Use ascending page ranges between 1 and 10,000.');
      for (let page = first; page <= last; page += 1) pages.add(page);
    }
    return [...pages];
  }
  function rotatePages(degrees) {
    try {
      const pages = parsePages(id('rotatePages').value);
      if (pageCount !== null && Math.max(...pages) > pageCount) throw new Error(`This queue has ${pageCount} pages. Choose numbers within that range.`);
      for (const page of pages) {
        const angle = ((pageRotations[page] || 0) + degrees + 360) % 360;
        if (angle) pageRotations[page] = angle; else delete pageRotations[page];
      }
      id('rotatePages').removeAttribute('aria-invalid'); changed();
    } catch (error) { id('rotatePages').setAttribute('aria-invalid','true'); id('pageRotationStatus').textContent = error.message; }
  }
  function resetPageRotations() { for (const key of Object.keys(pageRotations)) delete pageRotations[key]; refresh(); }
  ['pageSize','pageOrientation','pageFit','pageMargin','marginMm','pageRotation'].forEach(name => id(name).addEventListener('change', changed));
  id('rotateAllLeft').addEventListener('click', () => rotateAll(-90));
  id('rotateAllRight').addEventListener('click', () => rotateAll(90));
  id('rotatePagesLeft').addEventListener('click', () => rotatePages(-90));
  id('rotatePagesRight').addEventListener('click', () => rotatePages(90));
  id('resetPageRotations').addEventListener('click', () => { resetPageRotations(); changed(); });
  window.addEventListener('cometforge:source-ready', event => {
    const current = window.CometForge.getSnapshot().files;
    if (event.detail.files.length === current.length && event.detail.files.every((file,index) => file === current[index])) { sourceFiles = current; pageCount = event.detail.pageCount; }
  });
  window.addEventListener('cometforge:change', () => {
    const current = window.CometForge.getSnapshot().files;
    if (current.length !== sourceFiles.length || current.some((file,index) => file !== sourceFiles[index])) pageCount = null;
  });
  window.addEventListener('cometforge:busy', event => { busy = Boolean(event.detail); refresh(); });
  window.CometForgeLayout = {getOptions,resetPageRotations,parsePages};
  refresh();
})();
