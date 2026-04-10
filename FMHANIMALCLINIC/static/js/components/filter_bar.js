/* ═══════════════════════════════════════════════════════════════
   COMPONENT — Filter Bar  ·  Active chips & dropdown interactions
   ═══════════════════════════════════════════════════════════════ */

(function initFilterBars() {
  'use strict';

  document.querySelectorAll('.c-filter-bar').forEach(bar => {
    const form = bar.querySelector('.c-filter-bar__form');
    if (!form) return;

    const chipsContainer = bar.querySelector('.c-filter-bar__active-chips');

    // ── Dropdown trigger visual sync ──
    bar.querySelectorAll('.c-filter-dropdown').forEach(dd => {
      const sel = dd.querySelector('.c-filter-dropdown__select');
      const trigger = dd.querySelector('.c-filter-dropdown__trigger');
      const label = trigger?.querySelector('.c-filter-dropdown__label');
      if (!sel || !trigger) return;

      const defaultLabel = sel.options[0]?.textContent || 'All';

      function syncState() {
        const hasValue = sel.value && sel.value !== '';
        const selectedText = sel.options[sel.selectedIndex]?.textContent || defaultLabel;

        if (hasValue) {
          trigger.classList.add('active');
          if (label) label.textContent = selectedText;
        } else {
          trigger.classList.remove('active');
          if (label) label.textContent = defaultLabel;
        }
      }

      sel.addEventListener('change', function () {
        syncState();
        // Submit the form
        form.submit();
      });

      // Initial sync
      syncState();
    });

    // ── Active Chips: remove on click ──
    if (chipsContainer) {
      chipsContainer.addEventListener('click', function (e) {
        const removeBtn = e.target.closest('.c-filter-chip__remove');
        if (!removeBtn) return;

        const chip = removeBtn.closest('.c-filter-chip');
        if (!chip) return;

        const filterName = chip.dataset.filter;
        if (!filterName) return;

        // Animate chip out
        chip.style.transition = 'all 0.25s ease';
        chip.style.opacity = '0';
        chip.style.transform = 'scale(0.7)';

        setTimeout(() => {
          // Find and reset the corresponding select
          const sel = form.querySelector(`select[name="${filterName}"]`);
          if (sel) {
            sel.value = '';
          }

          // Find and reset the corresponding input
          const inp = form.querySelector(`input[name="${filterName}"]`);
          if (inp) {
            inp.value = '';
          }

          // Submit form
          form.submit();
        }, 200);
      });
    }

    // ── Keyboard shortcut (Ctrl+K or / to focus search) ──
    const searchInput = bar.querySelector('.c-filter-bar__search-input');
    if (searchInput) {
      document.addEventListener('keydown', function (e) {
        // Ctrl+K or Cmd+K
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
          e.preventDefault();
          searchInput.focus();
          searchInput.select();
        }
        // "/" key when not in an input
        if (e.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) {
          e.preventDefault();
          searchInput.focus();
        }
      });

      // Submit on Enter
      searchInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
          form.submit();
        }
      });
    }
  });
}());
