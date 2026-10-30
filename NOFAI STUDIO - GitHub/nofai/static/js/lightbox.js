// Gallery lightbox. Each [data-lightbox] tile carries its project's images as JSON
// (data-gallery). Native <dialog>: focus is kept inside, Esc closes.
// Keyboard arrows follow reading direction (in Hebrew, ← is "next"). Swipe on touch.
(() => {
  const dialog = document.querySelector("[data-lightbox-dialog]");
  if (!dialog) return;

  const img = dialog.querySelector("[data-lb-image]");
  const title = dialog.querySelector("[data-lb-title]");
  const sub = dialog.querySelector("[data-lb-sub]");
  const desc = dialog.querySelector("[data-lb-desc]");
  const count = dialog.querySelector("[data-lb-count]");
  const prevBtn = dialog.querySelector("[data-lb-prev]");
  const nextBtn = dialog.querySelector("[data-lb-next]");
  const ofLabel = dialog.dataset.labelOf;
  const rtl = document.documentElement.dir === "rtl";

  let gallery = null, index = 0, trigger = null;

  function preload(i) {
    const item = gallery.images[i];
    if (item) { const p = new Image(); p.src = item.src; }
  }

  function show(i, animate = true) {
    index = Math.max(0, Math.min(i, gallery.images.length - 1));
    const item = gallery.images[index];
    const apply = () => {
      img.src = item.src;
      img.width = item.w;
      img.height = item.h;
      img.alt = item.alt || gallery.title;
      img.classList.remove("is-changing");
    };
    if (animate) {
      img.classList.add("is-changing");
      setTimeout(apply, 220);
    } else {
      apply();
    }
    count.textContent = `${index + 1} ${ofLabel} ${gallery.images.length}`;
    prevBtn.disabled = index === 0;
    nextBtn.disabled = index === gallery.images.length - 1;
    preload(index + 1);
    preload(index - 1);
  }

  function open(tile) {
    gallery = JSON.parse(tile.dataset.gallery);
    if (!gallery.images.length) return;
    trigger = tile;
    title.textContent = gallery.title;
    sub.textContent = [gallery.client, gallery.year].filter(Boolean).join(" · ");
    desc.textContent = gallery.description || "";
    count.hidden = prevBtn.hidden = nextBtn.hidden = gallery.images.length < 2;
    show(0, false);
    dialog.showModal();
    document.documentElement.classList.add("lb-open");
  }

  dialog.addEventListener("close", () => {
    document.documentElement.classList.remove("lb-open");
    if (trigger) trigger.focus();
  });

  document.addEventListener("click", (e) => {
    const tile = e.target.closest("[data-lightbox]");
    if (tile) open(tile);
  });
  prevBtn.addEventListener("click", () => show(index - 1));
  nextBtn.addEventListener("click", () => show(index + 1));
  dialog.querySelector("[data-lb-close]").addEventListener("click", () => dialog.close());
  // click on the empty stage area (not the image) closes
  dialog.querySelector(".lb-stage").addEventListener("click", (e) => { if (e.target === e.currentTarget) dialog.close(); });

  dialog.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    const forward = (e.key === "ArrowRight") !== rtl;
    show(index + (forward ? 1 : -1));
    e.preventDefault();
  });

  // swipe
  let startX = null;
  dialog.addEventListener("pointerdown", (e) => { if (e.pointerType !== "mouse") startX = e.clientX; });
  dialog.addEventListener("pointerup", (e) => {
    if (startX === null) return;
    const dx = e.clientX - startX;
    startX = null;
    if (Math.abs(dx) < 50) return;
    const forward = (dx < 0) !== rtl;   // swipe left = next in LTR
    show(index + (forward ? 1 : -1));
  });
})();
