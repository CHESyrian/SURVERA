/**
 * SURVERA – password show/hide toggle + strength meter.
 */
(function () {
  "use strict";

  function scorePassword(pw) {
    if (!pw) return { score: 0, label: "", level: "" };
    var score = 0;
    var len = pw.length;
    if (len >= 8) score += 1;
    if (len >= 12) score += 1;
    if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score += 1;
    if (/\d/.test(pw)) score += 1;
    if (/[^A-Za-z0-9]/.test(pw)) score += 1;
    // Cap at 4 levels for UI
    var level, label;
    if (score <= 1) {
      level = "weak";
      label = "Weak";
    } else if (score === 2) {
      level = "fair";
      label = "Fair";
    } else if (score === 3) {
      level = "good";
      label = "Good";
    } else {
      level = "strong";
      label = "Strong";
    }
    return { score: Math.min(score, 4), label: label, level: level };
  }

  function initToggles() {
    document.querySelectorAll("[data-pw-toggle]").forEach(function (btn) {
      if (btn.dataset.bound) return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-pw-toggle");
        var input = document.getElementById(id);
        if (!input) return;
        var showing = input.type === "text";
        input.type = showing ? "password" : "text";
        btn.classList.toggle("is-showing", !showing);
        btn.setAttribute(
          "aria-label",
          showing ? "Show password" : "Hide password"
        );
        btn.setAttribute("title", showing ? "Show password" : "Hide password");
      });
    });
  }

  function initMeters() {
    document.querySelectorAll("[data-pw-meter]").forEach(function (input) {
      if (input.dataset.meterBound) return;
      input.dataset.meterBound = "1";
      var wrap = document.querySelector(
        '[data-pw-meter-for="' + input.id + '"]'
      );
      if (!wrap) return;
      var fill = wrap.querySelector(".sv-pw-meter-fill");
      var labelEl = wrap.querySelector(".sv-pw-meter-label");

      function update() {
        var r = scorePassword(input.value);
        if (!input.value) {
          wrap.hidden = true;
          return;
        }
        wrap.hidden = false;
        wrap.setAttribute("data-level", r.level);
        if (fill) {
          fill.style.width = (r.score / 4) * 100 + "%";
        }
        if (labelEl) {
          labelEl.textContent = r.label;
        }
      }
      input.addEventListener("input", update);
      input.addEventListener("focus", update);
      update();
    });
  }

  function init() {
    initToggles();
    initMeters();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
