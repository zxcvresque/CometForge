/* A short first-visit introduction, with an explicit replay entry point. */
(() => {
  const id = (value) => document.getElementById(value);
  const overlay=id('tourOverlay'), dialog=id('tourDialog'), next=id('tourNext'), back=id('tourBack');
  const steps = [
    {title:'Welcome to CometForge',description:'Build clear, shareable PDFs from images and existing documents. Everything is processed by your own CometForge instance.',tip:'Start with files, ZIPs or a whole folder. Drop them anywhere to fill the queue.'},
    {title:'Keep quality. Choose your cap.',description:'Follow Sources, Export and Review. Target-fit seeks the highest quality below your size cap; lossless preserves image quality.',tip:'In Export, choose page-based parts and fast web view. Review shows your settings and approximate size ranges before Forge.'},
    {title:'Compare the details',description:'Forge once, then inspect the same page before and after compression. Drag the vertical divider left and right, change pages, or zoom in.',tip:'Each output shows its actual size. Download one PDF or the ZIP containing all parts.'},
    {title:'Ready to forge',description:'Queue order becomes page order. Files start in natural name order: 1, 2, 10, then A–Z. Select a group to move it, or sort by modification date.',tip:'Collapse the settings panel for more room. You can replay this introduction from Quick tour.'},
  ];
  let index=0, previousFocus=null;
  function render() {
    const step=steps[index];id('tourTitle').textContent=step.title;id('tourDescription').textContent=step.description;id('tourTip').textContent=step.tip;
    id('tourStep').textContent=`${index+1} / ${steps.length}`;back.disabled=index===0;next.textContent=index===steps.length-1?'Start forging':'Next';
  }
  function open() {
    try { id('tourDontShow').checked=localStorage.getItem('cometforge:tour-hidden')==='true'||localStorage.getItem('cometforge:tour-seen')==='true'; } catch {}
    previousFocus=document.activeElement;index=0;render();overlay.classList.remove('hidden');
    document.getElementById('app').inert=true;document.body.classList.add('tourOpen');dialog.focus();
  }
  function close() {
    if(overlay.classList.contains('hidden'))return;
    overlay.classList.add('hidden');document.getElementById('app').inert=false;document.body.classList.remove('tourOpen');
    try {
      if(id('tourDontShow').checked){localStorage.setItem('cometforge:tour-seen','true');localStorage.setItem('cometforge:tour-hidden','true');}
      else{localStorage.removeItem('cometforge:tour-seen');localStorage.removeItem('cometforge:tour-hidden');}
    } catch { window.CometForgeTourSessionSeen=true; }
    previousFocus?.focus?.();
  }
  next.addEventListener('click',()=>{if(index===steps.length-1)close();else{index+=1;render();}});
  back.addEventListener('click',()=>{if(index>0){index-=1;render();}});
  id('tourSkip').addEventListener('click',close);id('replayTourBtn').addEventListener('click',open);
  overlay.addEventListener('keydown',(event)=>{
    if(event.key==='Escape'){event.preventDefault();close();return;}
    if(event.key!=='Tab')return;
    const controls=Array.from(dialog.querySelectorAll('button,a[href],input')).filter((el)=>!el.disabled);
    const first=controls[0],last=controls[controls.length-1];
    if(event.shiftKey&&(document.activeElement===first||document.activeElement===dialog)){event.preventDefault();last.focus();}
    else if(!event.shiftKey&&(document.activeElement===last||document.activeElement===dialog)){event.preventDefault();first.focus();}
  });
  let seen=Boolean(window.CometForgeTourSessionSeen);try{seen=seen||localStorage.getItem('cometforge:tour-seen')==='true'||localStorage.getItem('cometforge:tour-hidden')==='true';}catch{}
  if(!seen)open();
  window.CometForgeTour={open,close};
})();
