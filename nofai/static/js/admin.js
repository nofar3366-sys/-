// Admin conveniences. Every action also works as a plain form post without JS.
document.addEventListener("DOMContentLoaded", () => {
  // Confirm destructive actions
  document.querySelectorAll("form[data-confirm]").forEach((form) =>
    form.addEventListener("submit", (e) => { if (!confirm(form.dataset.confirm)) e.preventDefault(); })
  );

  // Image upload: drag & drop highlight + local previews of the chosen files
  const zone = document.querySelector("[data-dropzone]");
  if (zone) {
    const input = zone.querySelector("[data-file-input]");
    const list = zone.querySelector("[data-file-list]");
    const previews = document.querySelector("[data-previews]");
    ["dragenter", "dragover"].forEach((t) => zone.addEventListener(t, () => zone.classList.add("is-over")));
    ["dragleave", "drop"].forEach((t) => zone.addEventListener(t, () => zone.classList.remove("is-over")));
    input.addEventListener("change", () => {
      previews.replaceChildren();
      const files = [...input.files];
      list.textContent = files.length ? `${files.length} קבצים נבחרו. הם יועלו בלחיצה על שמירה.` : "";
      files.slice(0, 24).forEach((file) => {
        if (!file.type.startsWith("image/")) return;
        const img = document.createElement("img");
        img.alt = file.name;
        img.src = URL.createObjectURL(file);   // allowed by the CSP (img-src blob:)
        img.onload = () => URL.revokeObjectURL(img.src);
        previews.append(img);
      });
    });
  }

  // Account page: show / hide password fields
  document.querySelectorAll("[data-toggle-passwords]").forEach((box) =>
    box.addEventListener("change", () => {
      box.form.querySelectorAll("input[name$='password']").forEach((i) => { i.type = box.checked ? "text" : "password"; });
    })
  );
});
