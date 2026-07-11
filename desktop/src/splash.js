(function () {
  const statusEl = document.getElementById("status");
  const stageEl = document.getElementById("stage");

  function paint(stage, text) {
    statusEl.textContent = text;
    if (stage === "error") {
      statusEl.classList.remove("active");
      statusEl.classList.add("error");
      stageEl.classList.add("error");
    } else {
      statusEl.classList.add("active");
    }
  }

  function attach() {
    if (window.__TAURI__ && window.__TAURI__.event) {
      window.__TAURI__.event.listen("mia://progress", (e) => {
        const p = e.payload || {};
        paint(p.stage, p.text);
      });
    } else {
      // Reintentar hasta que el puente de Tauri esté disponible.
      setTimeout(attach, 120);
    }
  }
  attach();
})();
