/* Load before CSS so restored appearance never flashes another theme. */
(() => {
  const allowed = new Set(['prism','comet','light','system']);
  const media = window.matchMedia?.('(prefers-color-scheme: dark)');
  let preference = 'prism';
  try { const saved = localStorage.getItem('cometforge:theme'); if (allowed.has(saved)) preference = saved; } catch {}
  function apply(value,persist=true) {
    preference = allowed.has(value) ? value : 'prism';
    const resolved = preference === 'system' ? (media?.matches ? 'prism' : 'light') : preference;
    document.documentElement.dataset.theme = resolved;
    document.documentElement.dataset.themePreference = preference;
    if (persist) { try { localStorage.setItem('cometforge:theme',preference); } catch {} }
    const select = document.getElementById('appTheme');
    if (select && select.value !== preference) { select.value = preference; select.dispatchEvent(new Event('change')); }
  }
  apply(preference,false);
  function ready() {
    const select = document.getElementById('appTheme');
    if (!select) return;
    select.value = preference;
    select.dispatchEvent(new Event('change'));
    select.addEventListener('change',() => apply(select.value));
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',ready,{once:true}); else ready();
  const changed = () => { if (preference === 'system') apply('system',false); };
  if (media?.addEventListener) media.addEventListener('change',changed); else media?.addListener?.(changed);
  window.CometForgeTheme = {apply,getPreference:()=>preference};
})();
