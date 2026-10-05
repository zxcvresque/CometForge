/* Guided export uses the same queue, options and Forge pipeline in every step. */
(() => {
  const api = window.CometForge;
  const id = (name) => document.getElementById(name);
  const sections = ['sourceStep', 'exportStep', 'reviewStep'].map(id);
  const steps = [...id('flowSteps').querySelectorAll('button')];
  const next = id('flowNext'), back = id('flowBack'), forge = id('forgeBtn');
  let step = 1;
  let busy = false;

  function setStep(value, focus = true) {
    step = Math.max(1, Math.min(3, value));
    document.dispatchEvent(new CustomEvent('cometforge:closemenus'));
    sections.forEach((section, index) => { section.hidden = index !== step - 1; });
    steps.forEach((button, index) => {
      if (index === step - 1) button.setAttribute('aria-current', 'step');
      else button.removeAttribute('aria-current');
    });
    next.classList.toggle('hidden', step === 3);
    forge.classList.toggle('hidden', step !== 3);
    refresh();
    id('flowBody').scrollTop = 0;
    if (focus) sections[step - 1].querySelector('h2').focus({preventScroll: true});
  }

  function refresh() {
    const {files, options} = api.getSnapshot();
    const count = files.length;
    const parts = options.split_enabled ? options.split_count : 1;
    const modes = {off: 'Build only', lossless: 'Lossless optimize', targetfit: 'Quality first'};
    id('flowSourceCount').textContent = count ? `${count} source${count === 1 ? '' : 's'} ready` : 'No sources yet';
    id('flowSourceBytes').textContent = api.fmtMB(files.reduce((total, file) => total + file.size, 0));
    id('flowSummary').textContent = count ? `${parts} PDF${parts === 1 ? '' : 's'} · ${options.compress_mode === 'targetfit' ? `${options.target_mb} MB cap each` : modes[options.compress_mode]}` : 'Add sources to begin';
    const rows = [
      ['Name', options.output_name], ['Sources', `${count} file${count === 1 ? '' : 's'}`],
      ['Compression', modes[options.compress_mode]],
      ['Size cap', options.compress_mode === 'targetfit' ? `${options.target_mb} MB per PDF` : 'Not enforced'],
      ['Output', `${parts} PDF${parts === 1 ? '' : 's'}`], ['Fast web view', options.linearize ? 'On' : 'Off'],
    ];
    id('flowReview').replaceChildren(...rows.flatMap(([label, value]) => {
      const key = document.createElement('dt'), text = document.createElement('dd');
      key.textContent = label; text.textContent = value; text.title = value;
      return [key, text];
    }));
    next.disabled = !count || busy;
    back.disabled = step === 1 || busy;
    steps.forEach((button, index) => { button.disabled = busy || (!count && index > 0); });
    id('queueIllustration').classList.toggle('hidden', count > 3);
    id('splitOptions').hidden = !options.split_enabled;
    const capActive = options.compress_mode === 'targetfit';
    id('targetMb').disabled = busy || !capActive;
    id('targetMbNumber').disabled = busy || !capActive;
    id('targetMbHelp').textContent = capActive
      ? 'Per-part estimates appear in Review. Final measured sizes appear after Forge.'
      : 'This mode preserves image quality and does not enforce a size cap.';
    id('targetMb').style.setProperty('--range-fill', `${(Number(id('targetMb').value) - 1) / 199 * 100}%`);
    forge.setAttribute('aria-busy', String(busy));
    forge.textContent = busy ? 'Forging…' : 'Forge';
    if (!busy) forge.disabled = !count;
  }

  steps.forEach((button) => button.addEventListener('click', () => setStep(Number(button.dataset.step))));
  next.addEventListener('click', () => setStep(step + 1));
  back.addEventListener('click', () => setStep(step - 1));
  window.addEventListener('cometforge:change', refresh);
  window.addEventListener('cometforge:busy', (event) => {
    busy = Boolean(event.detail);
    ['outName', 'compressModeTrigger', 'splitEnabled', 'splitCount', 'linearize', 'pickBtn', 'pickFolderBtn', 'clearBtn'].forEach((name) => { id(name).disabled = busy; });
    if (!busy) id('splitCount').disabled = !id('splitEnabled').checked;
    refresh();
  });
  setStep(1, false);
})();
