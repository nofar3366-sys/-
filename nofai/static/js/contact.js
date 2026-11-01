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

  const PHONE_RE = /^\+?[\d\s\-().]{7,30}$/;
  const rules = {
    name: (v) => (v ? "" : msg.errName),
    // required: the phone is how the visitor gets called back
    phone: (v) => (PHONE_RE.test(v) && (v.match(/\d/g) || []).length >= 7 ? "" : msg.errPhone),
    // optional: empty is fine, otherwise it must be a valid address
    email: (v) => (!v || EMAIL_RE.test(v) ? "" : msg.errEmail),
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
    const showSuccess = (text) => {
      success.querySelector("[data-success-message]").textContent = text;
      form.hidden = true;
      success.hidden = false;
      success.focus();
    };
    try {
      if (form.hasAttribute("data-netlify")) {
        // Static site on Netlify: Netlify Forms expects a url-encoded POST to "/"
        const res = await fetch("/", {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams(new FormData(form)).toString(),
        });
        if (!res.ok) throw new Error(res.status);
        showSuccess(msg.msgSuccess);
        return;
      }
      const res = await fetch(window.location.href, {
        method: "POST",
        body: new FormData(form),
        headers: { Accept: "application/json", "X-CSRFToken": form.elements.csrf_token.value },
      });
      const data = await res.json();
      if (data.ok) {
        showSuccess(data.message);
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
