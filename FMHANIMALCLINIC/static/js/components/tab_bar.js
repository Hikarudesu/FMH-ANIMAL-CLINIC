/* ═══════════════════════════════════════════════════════════════
   COMPONENT JS — Tab Bar  ·  Sliding Indicator + Tab Switching
   ═══════════════════════════════════════════════════════════════

   Auto-initialises every .c-tab-bar on the page.

   API:
     • Clicking a .c-tab-btn sets it active and shows #tab-{id}
     • The indicator slides smoothly to the active button
     • Fires custom event "tabchange" on the bar element
       with detail: { tab: "tabId", prevTab: "prevTabId" }

   Supports two modes automatically:
     • Client-side tabs (content panels with id="tab-{id}")
     • Navigation tabs (onclick navigates away) — entrance animation
   ═══════════════════════════════════════════════════════════════ */

(function () {
  "use strict";

  function initTabBar(bar) {
    var btns = bar.querySelectorAll(".c-tab-btn");
    var indicator = bar.querySelector(".c-tab-bar__indicator");
    if (!btns.length || !indicator) return;

    /* ── Helper: position the sliding indicator ── */
    function moveIndicator(btn, animate) {
      if (!btn) return;
      var barRect = bar.getBoundingClientRect();
      var btnRect = btn.getBoundingClientRect();

      var left = btnRect.left - barRect.left + bar.scrollLeft;
      var width = btnRect.width;

      if (!animate) {
        indicator.style.transition = "none";
      }

      indicator.style.left = left + "px";
      indicator.style.width = width + "px";

      if (!animate) {
        // Force reflow then restore transition
        indicator.offsetHeight; // eslint-disable-line no-unused-expressions
        indicator.style.transition = "";
      }
    }

    /* ── Set active tab ── */
    function setActive(targetBtn) {
      var prevActive = bar.querySelector(".c-tab-btn.active");
      var prevTab = prevActive ? prevActive.dataset.tab : null;
      var newTab = targetBtn.dataset.tab;

      if (prevTab === newTab) return;

      // Switch button states
      btns.forEach(function (b) { b.classList.remove("active"); });
      targetBtn.classList.add("active");

      // Slide indicator
      moveIndicator(targetBtn, true);

      // Switch tab content panels (only if they exist on this page)
      document.querySelectorAll(".appt-tab-content, .c-tab-content").forEach(function (panel) {
        panel.classList.remove("active");
      });
      var targetPanel = document.getElementById("tab-" + newTab);
      if (targetPanel) targetPanel.classList.add("active");

      // Dispatch custom event
      bar.dispatchEvent(
        new CustomEvent("tabchange", {
          bubbles: true,
          detail: { tab: newTab, prevTab: prevTab }
        })
      );
    }

    /* ── Bind click events ── */
    btns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        setActive(btn);
      });
    });

    /* ── Position indicator on the initially active button ── */
    var initial = bar.querySelector(".c-tab-btn.active") || btns[0];
    if (initial) {
      if (!initial.classList.contains("active")) initial.classList.add("active");

      // Use double-rAF to ensure DOM has fully rendered & painted
      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          // First, position without animation (instant snap)
          moveIndicator(initial, false);

          // Then play a subtle entrance animation (scale-in + fade)
          // This makes it feel alive even on full page reloads (e.g. notification filters)
          indicator.style.animation = "cTabIndicatorEntrance 0.45s cubic-bezier(0.4, 0, 0.1, 1) both";
        });
      });
    }

    /* ── Reposition on window resize ── */
    var resizeTimer;
    window.addEventListener("resize", function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(function () {
        var active = bar.querySelector(".c-tab-btn.active");
        if (active) moveIndicator(active, false);
      }, 100);
    });
  }

  /* ── Auto-init on DOMContentLoaded ── */
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".c-tab-bar").forEach(initTabBar);
  });
})();
