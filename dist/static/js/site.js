// Site-wide interactions: header behaviour, mobile menu, scroll reveal, custom cursor.
(() => {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---- Header: blurred background once scrolled; hides on the way down, returns on the way up
  const header = document.querySelector("[data-header]");
  let lastY = window.scrollY;
  const syncHeader = () => {
    const y = window.scrollY;
    header.classList.toggle("is-scrolled", y > 20);
    header.classList.toggle("is-hidden", y > 400 && y > lastY && !document.body.classList.contains("menu-open"));
    lastY = y;
  };
  window.addEventListener("scroll", syncHeader, { passive: true });
  syncHeader();

  // ---- Mobile menu (full-screen overlay)
  const toggle = document.querySelector("[data-menu-toggle]");
  const nav = document.querySelector("[data-nav]");
  const setMenu = (open) => {
    toggle.setAttribute("aria-expanded", String(open));
    nav.classList.toggle("is-open", open);
    document.body.classList.toggle("menu-open", open);
    if (open) nav.querySelector("a").focus();
  };
  toggle.addEventListener("click", () => setMenu(toggle.getAttribute("aria-expanded") !== "true"));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && nav.classList.contains("is-open")) { setMenu(false); toggle.focus(); }
  });
  nav.addEventListener("click", (e) => { if (e.target.closest("a")) setMenu(false); });

  // ---- Reveal elements as they enter the viewport
  const items = document.querySelectorAll(".reveal");
  if (reduceMotion || !("IntersectionObserver" in window)) {
    items.forEach((el) => el.classList.add("is-in"));
  } else {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) { entry.target.classList.add("is-in"); observer.unobserve(entry.target); }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -6% 0px" });
    items.forEach((el) => observer.observe(el));
  }

  // ---- Custom cursor (mouse/trackpad only): a dot that eases after the pointer
  //      and opens into a labelled circle over clickable work
  const cursor = document.querySelector("[data-cursor]");
  const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  if (cursor && finePointer) {
    let x = 0, y = 0, cx = 0, cy = 0, running = false;
    const follow = () => {
      cx += (x - cx) * (reduceMotion ? 1 : 0.2);
      cy += (y - cy) * (reduceMotion ? 1 : 0.2);
      cursor.style.transform = `translate3d(${cx}px, ${cy}px, 0)`;
      running = Math.abs(x - cx) > 0.1 || Math.abs(y - cy) > 0.1;
      if (running) requestAnimationFrame(follow);
    };
    document.addEventListener("pointermove", (e) => {
      x = e.clientX; y = e.clientY;
      cursor.classList.add("is-visible");
      if (!running) { running = true; requestAnimationFrame(follow); }
    });
    document.addEventListener("pointerleave", () => cursor.classList.remove("is-visible"));
    document.addEventListener("pointerover", (e) => {
      cursor.classList.toggle("is-hover", !!e.target.closest("[data-cursor-hover], .tile-button"));
    });
  }
})();
