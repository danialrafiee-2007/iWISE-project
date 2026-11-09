// Contact us: a message goes to majidrafiee1404@gmail.com. When the server has a mail account (smtp.local.env,
// contact.py, which fixes that recipient), the server sends it. When it has none, or the mail server cannot be reached,
// nothing is blocked: the visitor's own email app opens with the message ready for the same address.

(() => {
  const form = document.getElementById("contact-form");
  if (!form) return;
  const TO = "majidrafiee1404@gmail.com";
  const status = document.getElementById("contact-status");
  const button = document.getElementById("contact-send");
  const label = button.querySelector("[data-i18n]");
  const tr = (key, vars) => (window.TG ? window.TG.t(key, vars) : key);
  const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  function say(key, kind, vars) {
    status.hidden = false;
    status.textContent = tr(key, vars);
    status.className = `form-status ${kind}`;
  }

  function values() {
    const data = Object.fromEntries(new FormData(form).entries());
    for (const k of Object.keys(data)) data[k] = String(data[k]).trim();
    return data;
  }

  // The visitor's own email app, with the message ready to send.
  function openMailApp(v) {
    const body = `${v.message}\n\n— ${v.name} <${v.email}>`;
    window.location.href = `mailto:${TO}?subject=${encodeURIComponent(`[Truth Guardian] ${v.subject}`)}&body=${encodeURIComponent(body)}`;
    say("html.mailFallback", "info");
  }

  async function configured() {
    try {
      const res = await fetch("/api/contact", { cache: "no-store" });
      return res.ok && (await res.json()).configured === true;
    } catch {
      return false;
    }
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const v = values();
    if (!v.name || !EMAIL.test(v.email) || !v.subject || !v.message) return say("contact.invalid", "bad");

    if (!(await configured())) return openMailApp(v);

    button.disabled = true;
    label.textContent = tr("contact.sending");
    try {
      const res = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...v, lang: window.TG ? window.TG.lang : "en" }),
      });
      if (res.ok) {
        form.reset();
        say("contact.sent", "ok");
      } else if (res.status === 429) {
        say("contact.tooMany", "bad");
      } else if (res.status === 422) {
        say("contact.invalid", "bad");
      } else {
        openMailApp(v); // not set up after all, or the mail server refused or was out of reach
      }
    } catch {
      openMailApp(v);
    } finally {
      button.disabled = false;
      label.textContent = tr("contact.send");
    }
  });
})();
