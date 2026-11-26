/* Shared WKWebView/WebView2 motion: continuity, material feedback, then rest. */
(() => {
  const media = window.matchMedia?.('(prefers-reduced-motion: reduce)');
  const running = new Map();
  const exits = new Map();
  const visible = new Map();
  const stepIds = ['sourceStep','layoutStep','exportStep','reviewStep'];
  let currentStep = Math.max(0, stepIds.findIndex(id => !document.getElementById(id)?.hidden));
  let disposed = false;
  const easing = 'cubic-bezier(.16,1,.3,1)';

  function cancel(element) {
    const active = running.get(element);
    if (!active) return;
    running.delete(element);
    active.cancel();
  }

  function animate(element, frames, duration) {
    cancel(element);
    if (!element?.animate || document.hidden || disposed) return;
    const active = element.animate(frames, {duration,easing,fill:'none'});
    running.set(element, active);
    const clean = () => { if (running.get(element) === active) running.delete(element); };
    active.finished?.then(clean,clean);
    return active;
  }

  function reveal(element, direction=1) {
    if (media?.matches) return animate(element,[{opacity:.8},{opacity:1}],90);
    return animate(element,[{opacity:.66,transform:`translateX(${8 * direction}px)`},
                            {opacity:1,transform:'translateX(0)'}],180);
  }

  function clearExit(menu) {
    const exit = exits.get(menu);
    if (!exit) return;
    exits.delete(menu);
    cancel(exit);
    exit.remove();
  }

  function openPopup(menu) {
    clearExit(menu);
    const frames = media?.matches ? [{opacity:.72},{opacity:1}] :
      [{opacity:.5,clipPath:'inset(0 0 8% 0 round 10px)'},
       {opacity:1,clipPath:'inset(0 0 0 0 round 10px)'}];
    return animate(menu,frames,media?.matches ? 90 : 150);
  }

  function closePopup(menu) {
    const opacity = menu && window.getComputedStyle ? Number(window.getComputedStyle(menu).opacity) : 1;
    cancel(menu);
    clearExit(menu);
    if (!menu || menu.classList.contains('hidden') || document.hidden || disposed) return;
    const bounds = menu.getBoundingClientRect();
    if (!bounds.width || !bounds.height || !menu.animate) return;
    // Remove semantics/focus immediately. This inert proxy only preserves the
    // last visual surface while the real menu closes and focus returns.
    const exit = menu.cloneNode(true);
    exit.removeAttribute('id');
    exit.querySelectorAll('[id]').forEach(node => node.removeAttribute('id'));
    exit.setAttribute('aria-hidden','true');
    exit.setAttribute('inert','');
    exit.inert = true;
    exit.classList.add('motionPopupExit');
    exit.querySelectorAll('button,input,a,[tabindex]').forEach(node => { node.tabIndex = -1; });
    Object.assign(exit.style,{position:'fixed',left:`${bounds.left}px`,top:`${bounds.top}px`,
      width:`${bounds.width}px`,height:`${bounds.height}px`,minWidth:'0',maxWidth:'none',margin:'0'});
    document.body.append(exit);
    exits.set(menu,exit);
    const active = animate(exit,[{opacity:Number.isFinite(opacity) ? opacity : 1},{opacity:0}],media?.matches ? 70 : 110);
    const clean = () => { if (exits.get(menu) === exit) exits.delete(menu); exit.remove(); };
    if (active?.finished) active.finished.then(clean,clean); else clean();
  }

  function isVisible(element) { return !element.hidden && !element.classList.contains('hidden'); }
  const observer = typeof MutationObserver === 'function' ? new MutationObserver(records => {
    const changed = new Set(records.map(record => record.target));
    for (const element of changed) {
      const now = isVisible(element), before = visible.get(element);
      visible.set(element,now);
      if (!now) { cancel(element); continue; }
      if (before !== false) continue;
      const index = stepIds.indexOf(element.id);
      const direction = index >= 0 && index < currentStep ? -1 : 1;
      if (index >= 0) currentStep = index;
      reveal(element,direction);
    }
  }) : null;

  function ready() {
    for (const id of [...stepIds,'queueView','resultsView','customMarginField','splitOptions']) {
      const element = document.getElementById(id);
      if (!element) continue;
      visible.set(element,isVisible(element));
      observer?.observe(element,{attributes:true,attributeFilter:['hidden','class']});
    }
  }

  function stop() {
    for (const element of [...running.keys()]) cancel(element);
    for (const menu of [...exits.keys()]) clearExit(menu);
  }
  function visibilityChanged() {
    document.documentElement.toggleAttribute('data-motion-paused',document.hidden);
    if (document.hidden) stop();
  }
  function preferenceChanged() { stop(); }
  function detailToggled(event) {
    if (event.target?.tagName !== 'DETAILS' || !event.target.open) return;
    for (const child of event.target.children) if (child.tagName !== 'SUMMARY') {
      animate(child,[{opacity:media?.matches ? .8 : .55},{opacity:1}],media?.matches ? 90 : 150);
    }
  }
  document.addEventListener('toggle',detailToggled,true);
  document.addEventListener('visibilitychange',visibilityChanged);
  if (media?.addEventListener) media.addEventListener('change',preferenceChanged);
  else media?.addListener?.(preferenceChanged);
  function dispose() {
    disposed = true; stop(); observer?.disconnect();
    document.removeEventListener('toggle',detailToggled,true);
    document.removeEventListener('visibilitychange',visibilityChanged);
    media?.removeEventListener?.('change',preferenceChanged);
    media?.removeListener?.(preferenceChanged);
  }
  window.addEventListener('pagehide',dispose,{once:true});
  visibilityChanged();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',ready,{once:true}); else ready();
  window.CometForgeMotion = {reveal,openPopup,closePopup,cancel,dispose};
})();
