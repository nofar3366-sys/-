// "Floating" scroll: native scrolling stays untouched (accessibility, anchors, touch),
// while every [data-speed] element trails a smoothed copy of the scroll position and
// drifts at its own depth, so the whole page feels like it's gliding on water.
//
//   data-speed="0.1"   parallax depth (positive and negative move in opposite directions)
//
// Writes `transform` only; entrance animations use the separate `translate` property,
// so both effects compose. Fully disabled for prefers-reduced-motion.
(() => {
  const elements = [...document.querySelectorAll("[data-speed]")];
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  if (!elements.length || reduceMotion.matches) return;

  const EASE = 0.085;          // how quickly the smoothed position catches up (per frame)
  const LAG_BASE = 0.35;       // how much every element trails behind fast scrolling
  const small = window.matchMedia("(max-width: 600px)");

  let items = [];
  let smooth = window.scrollY;
  let viewport = window.innerHeight;
  let frame = null;

  function measure() {
    viewport = window.innerHeight;
    items = elements.map((el) => {
      el.style.transform = "";                       // measure the untransformed position
      const rect = el.getBoundingClientRect();
      return { el, speed: parseFloat(el.dataset.speed) || 0,
               center: rect.top + window.scrollY + rect.height / 2, height: rect.height };
    });
    render(true);
  }

  function render(force) {
    const target = window.scrollY;
    smooth += (target - smooth) * EASE;
    const lag = target - smooth;                      // > 0 while scrolling down
    const factor = small.matches ? 0.5 : 1;
    const viewCenter = smooth + viewport / 2;

    for (const item of items) {
      const distance = item.center - viewCenter;
      if (!force && Math.abs(distance) > viewport * 1.4 + item.height) continue;  // far off-screen
      const y = (-distance * item.speed + lag * (LAG_BASE + Math.abs(item.speed))) * factor;
      item.el.style.transform = `translate3d(0, ${y.toFixed(2)}px, 0)`;
    }

    frame = Math.abs(lag) > 0.05 ? requestAnimationFrame(() => render(false)) : null;
  }

  function wake() {
    if (frame === null) frame = requestAnimationFrame(() => render(false));
  }

  window.addEventListener("scroll", wake, { passive: true });
  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(measure, 150);
  });
  // images change element heights as they load; re-measure once everything is in
  window.addEventListener("load", measure);
  reduceMotion.addEventListener("change", (e) => {
    if (e.matches) { cancelAnimationFrame(frame); elements.forEach((el) => { el.style.transform = ""; }); }
  });
  measure();
})();
