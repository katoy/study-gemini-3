(function () {
  function initTheme() {
    const saved = localStorage.getItem("theme") || "auto";
    const html = document.documentElement;
    if (saved === "auto") {
      const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      html.setAttribute("data-theme", dark ? "dark" : "light");
    } else {
      html.setAttribute("data-theme", saved);
    }
  }

  function initFontSize() {
    const saved = localStorage.getItem("fontSize") || "100";
    const percentage = parseInt(saved, 10);
    const baseFontSize = 16;
    const newFontSize = (baseFontSize * percentage) / 100;
    document.documentElement.style.fontSize = `${newFontSize}px`;
  }

  initTheme();
  initFontSize();
})();
