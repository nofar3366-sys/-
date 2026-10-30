// Contact form: client-side checks (the server re-validates everything), AJAX submit,
// inline errors per field, success panel. Works as a normal form post without JS.
(() => {
  const form = document.querySelector("[data-contact-form]");
  if (!form) return;

  const status = form.querySelector("[data-form-status]");
  const button = form.querySelector("button[type=submit]");
  const label = form.querySelector("[data-btn-label]");
  const success = document.querySelector("[data-form-success]");
  const msg = form.dataset;
  const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

  const rules = {
    name: (v) => (v ? "" : msg.errName),
    email: (v) => (EMAIL_RE.test(v) ? "" : msg.errEmail),
    message: (v) => (v.length >= 10 ? "" : msg.errMessage),
  };

  const setError = (name, text) => {
    const input = form.elements[name];
    const out = form.querySelector(`#e-${name}`);
    if (!input || !out) return;
    out.textContent = text || "";
    if (text) input.setAttribute("aria-invalid", "true"); else input.removeAttribute("aria-invalid");
  };

  const check = (name) => {
    const text = rules[name](form.elements[name].value.trim());
    setError(name, text);
    return !text;
  };

  Object.keys(rules).forEach((name) => {
    const input = form.elements[name];
    input.addEventListener("blur", () => check(name));
    input.addEventListener("input", () => { if (input.hasAttribute("aria-invalid")) check(name); });
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    status.textContent = "";
    const invalid = Object.keys(rules).filter((name) => !check(name));
    if (invalid.length) {
      status.textContent = msg.msgFix;
      form.elements[invalid[0]].focus();
      return;
    }
    const original = label.textContent;
    button.disabled = true;
    label.textContent = msg.msgSending;
    try {
      const res = await fetch(form.action || window.location.href, {
        method: "POST",
        body: new FormData(form),
        headers: { Accept: "application/json", "X-CSRFToken": form.elements.csrf_token.value },
      });
      const data = await res.json();
      if (data.ok) {
        success.querySelector("[data-success-message]").textContent = data.message;
        form.hidden = true;
        success.hidden = false;
        success.focus();
      } else {
        Object.entries(data.errors || {}).forEach(([name, text]) => setError(name, text));
        status.textContent = data.message;
      }
    } catch {
      status.textContent = msg.msgOffline;
    } finally {
      button.disabled = false;
      label.textContent = original;
    }
  });
})();
