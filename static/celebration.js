/* One local, non-blocking comet flyby per successful Forge. No looping. */
(() => {
  let stop = () => {};
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const celebrated = new Set();

  function flyby(detail) {
    stop();
    const layer = document.createElement('div');
    layer.className = 'cometCelebration';
    const message = document.createElement('div');
    message.className = 'cometSuccess';
    message.setAttribute('role', 'status');
    message.textContent = `${detail.count} PDF${detail.count === 1 ? '' : 's'} ready. Beautifully forged.`;
    layer.append(message);
    document.body.append(layer);
    let frame, timer, ended = false;
    function cleanup() {
      if (ended) return;
      ended = true;
      cancelAnimationFrame(frame);
      clearTimeout(timer);
      window.removeEventListener('resize', cleanup);
      document.removeEventListener('visibilitychange', visibility);
      reduced.removeEventListener('change', cleanup);
      layer.remove();
    }
    function visibility() { if (document.hidden) cleanup(); }
    stop = cleanup;
    document.addEventListener('visibilitychange', visibility);
    reduced.addEventListener('change', cleanup);
    if (reduced.matches) { timer = setTimeout(cleanup, 1800); return; }

    const canvas = document.createElement('canvas');
    canvas.setAttribute('aria-hidden', 'true');
    layer.prepend(canvas);
    const ctx = canvas.getContext('2d');
    if (!ctx) { timer = setTimeout(cleanup, 1800); return; }
    const width = window.innerWidth, height = window.innerHeight;
    const scale = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * scale); canvas.height = Math.round(height * scale);
    ctx.scale(scale, scale);
    window.addEventListener('resize', cleanup);
    const duration = 2400;
    const started = performance.now();
    const dust = [];
    function point(t) {
      return {x: -100 + (width + 280) * t, y: height * (.73 - .52 * t) - Math.sin(t * Math.PI) * Math.min(height * .14, 100)};
    }
    function draw(now) {
      if (ended) return;
      const elapsed = now - started;
      const t = Math.min(1.12, elapsed / 1900);
      ctx.clearRect(0, 0, width, height);
      const head = point(t);
      const fade = Math.max(0, Math.min(1, (duration - elapsed) / 400));
      ctx.globalCompositeOperation = 'lighter';
      // Layered tapered trails: a diffuse mint aura around a white-hot core.
      for (let i = 30; i >= 1; i -= 1) {
        const tail = point(t - i * .008), next = point(t - (i - 1) * .008);
        const strength = (1 - i / 31) ** 2;
        ctx.lineCap = 'round';
        ctx.strokeStyle = `rgba(92,220,181,${strength * .13 * fade})`;
        ctx.lineWidth = 4 + strength * 25;
        ctx.beginPath(); ctx.moveTo(tail.x, tail.y); ctx.lineTo(next.x, next.y); ctx.stroke();
        ctx.strokeStyle = `rgba(170,245,221,${strength * .8 * fade})`;
        ctx.lineWidth = .5 + strength * 4;
        ctx.beginPath(); ctx.moveTo(tail.x, tail.y); ctx.lineTo(next.x, next.y); ctx.stroke();
      }
      if (t < 1.04) {
        for (let i = 0; i < 3; i += 1) dust.push({x:head.x,y:head.y,vx:-.7-Math.random()*2,vy:(Math.random()-.5)*1.4,life:1,size:.5+Math.random()*1.7});
      }
      for (let i = dust.length - 1; i >= 0; i -= 1) {
        const particle = dust[i];
        particle.life -= .025; particle.x += particle.vx; particle.y += particle.vy;
        if (particle.life <= 0) { dust.splice(i, 1); continue; }
        ctx.fillStyle = `rgba(164,242,213,${particle.life * .6 * fade})`;
        ctx.beginPath(); ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2); ctx.fill();
      }
      const glow = ctx.createRadialGradient(head.x, head.y, 0, head.x, head.y, 36);
      glow.addColorStop(0, `rgba(240,255,249,${fade})`);
      glow.addColorStop(.16, `rgba(166,255,218,${.85 * fade})`);
      glow.addColorStop(.5, `rgba(91,226,181,${.18 * fade})`);
      glow.addColorStop(1, 'rgba(91,226,181,0)');
      ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(head.x, head.y, 36, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = `rgba(255,255,255,${fade})`; ctx.beginPath(); ctx.arc(head.x, head.y, 3.2, 0, Math.PI * 2); ctx.fill();
      // Small star glints give the head a crisp, luminous finish.
      ctx.strokeStyle = `rgba(228,255,246,${fade * .75})`; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(head.x - 12, head.y); ctx.lineTo(head.x + 12, head.y); ctx.moveTo(head.x, head.y - 12); ctx.lineTo(head.x, head.y + 12); ctx.stroke();
      ctx.globalCompositeOperation = 'source-over';
      if (elapsed > 2100) layer.classList.add('leaving');
      if (elapsed >= duration) cleanup();
      else frame = requestAnimationFrame(draw);
    }
    frame = requestAnimationFrame(draw);
  }
  window.addEventListener('cometforge:complete', (event) => {
    const detail = event.detail;
    if (!detail?.jobId || !detail.count || celebrated.has(detail.jobId) || document.hidden) return;
    celebrated.add(detail.jobId);
    if (celebrated.size > 30) celebrated.delete(celebrated.values().next().value);
    flyby(detail);
  });
})();
