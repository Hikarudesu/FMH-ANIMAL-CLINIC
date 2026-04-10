/* ═══════════════════════════════════════════════════════════
   SEARCHABLE DROPDOWN — Reusable JS component
   Auto-initializes all elements with data-sd attribute
   ═══════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  /**
   * Initialize a single searchable dropdown.
   *
   * Usage (HTML):
   *   <div class="sd-wrap" data-sd data-sd-name="branch" data-sd-value="3" data-sd-placeholder="All Branches">
   *     <!-- Options rendered by Django template or JS -->
   *     <div class="sd-data" style="display:none">
   *       <span data-val="">All Branches</span>
   *       <span data-val="1">Main Clinic</span>
   *       <span data-val="2">Downtown Branch</span>
   *     </div>
   *   </div>
   *
   * Or build from existing <select>:
   *   <select class="sd-convert" name="branch" ...>
   *     <option value="">All Branches</option>
   *     ...
   *   </select>
   *
   * JS API:
   *   SearchableDropdown.init()          — auto-initialize all
   *   SearchableDropdown.refresh(wrap)   — refresh a specific dropdown
   */

  const SD = {};

  // ── Build the dropdown DOM from a data source ──
  function buildDropdown(wrap) {
    const name = wrap.dataset.sdName || '';
    const placeholder = wrap.dataset.sdPlaceholder || 'Select...';
    const value = wrap.dataset.sdValue || '';
    const onchangeAction = wrap.dataset.sdOnchange || ''; // 'submit-form' or custom function name
    const formId = wrap.dataset.sdForm || '';
    const searchThreshold = parseInt(wrap.dataset.sdSearchThreshold || '6', 10);
    const iconClass = wrap.dataset.icon || ''; // Icon class if available

    // Gather options from .sd-data spans
    const dataContainer = wrap.querySelector('.sd-data');
    const options = [];
    if (dataContainer) {
      dataContainer.querySelectorAll('span[data-val]').forEach(function (span) {
        options.push({ value: span.dataset.val, label: span.textContent.trim() });
      });
      dataContainer.remove();
    }

    // Find selected label
    let selectedLabel = placeholder;
    options.forEach(function (opt) {
      if (opt.value === value) {
        selectedLabel = opt.label;
      }
    });

    // Hidden input for form submission
    const hiddenInput = document.createElement('input');
    hiddenInput.type = 'hidden';
    hiddenInput.name = name;
    hiddenInput.value = value;
    wrap.appendChild(hiddenInput);

    // Trigger button
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'sd-trigger' + (value ? ' has-value' : '');
    
    // Add icon if available
    let triggerHTML = '';
    if (iconClass) {
      triggerHTML += '<i class="' + iconClass + '" style="font-size: 1rem; flex-shrink: 0; opacity: 0.7; margin-right: 4px;"></i>';
    }
    triggerHTML += '<span class="sd-label">' + escapeHtml(selectedLabel) + '</span>';
    trigger.innerHTML = triggerHTML;
    
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');
    wrap.appendChild(trigger);

    // Dropdown panel
    const dropdown = document.createElement('div');
    dropdown.className = 'sd-dropdown';

    // Search input (only if enough options)
    const showSearch = options.length >= searchThreshold;
    if (showSearch) {
      const searchWrap = document.createElement('div');
      searchWrap.className = 'sd-search-wrap';
      const searchInput = document.createElement('input');
      searchInput.type = 'text';
      searchInput.className = 'sd-search';
      searchInput.placeholder = 'Type to search...';
      searchInput.autocomplete = 'off';
      searchWrap.appendChild(searchInput);
      dropdown.appendChild(searchWrap);
    }

    // Options
    const optionsList = document.createElement('div');
    optionsList.className = 'sd-options';
    optionsList.setAttribute('role', 'listbox');

    options.forEach(function (opt) {
      const optEl = document.createElement('div');
      optEl.className = 'sd-option' + (opt.value === value ? ' active' : '');
      optEl.dataset.value = opt.value;
      optEl.textContent = opt.label;
      optEl.setAttribute('role', 'option');
      optEl.setAttribute('aria-selected', opt.value === value ? 'true' : 'false');
      optionsList.appendChild(optEl);
    });
    dropdown.appendChild(optionsList);

    // Empty state
    const emptyEl = document.createElement('div');
    emptyEl.className = 'sd-empty';
    emptyEl.textContent = 'No matches found';
    dropdown.appendChild(emptyEl);

    wrap.appendChild(dropdown);

    // ── Event handlers ──

    // Toggle
    trigger.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      const isOpen = wrap.classList.contains('open');
      closeAll();
      if (!isOpen) {
        wrap.classList.add('open');
        trigger.setAttribute('aria-expanded', 'true');
        checkDropDirection(wrap, dropdown);
        if (showSearch) {
          const searchInput = dropdown.querySelector('.sd-search');
          setTimeout(function () { searchInput.focus(); }, 50);
        }
      }
    });

    // Select option
    optionsList.addEventListener('click', function (e) {
      const optEl = e.target.closest('.sd-option');
      if (!optEl) return;

      const newValue = optEl.dataset.value;
      const newLabel = optEl.textContent;
      const iconClass = wrap.dataset.icon || '';

      // Update state
      hiddenInput.value = newValue;
      wrap.dataset.sdValue = newValue;
      
      // Update label with icon if available
      const labelEl = trigger.querySelector('.sd-label');
      if (labelEl) {
        labelEl.textContent = newLabel;
      } else {
        // Rebuild trigger content with icon
        let triggerHTML = '';
        if (iconClass) {
          triggerHTML += '<i class="' + iconClass + '" style="font-size: 1rem; flex-shrink: 0; opacity: 0.7; margin-right: 4px;"></i>';
        }
        triggerHTML += '<span class="sd-label">' + escapeHtml(newLabel) + '</span>';
        trigger.innerHTML = triggerHTML;
      }
      
      trigger.classList.toggle('has-value', !!newValue);

      // Update active state
      optionsList.querySelectorAll('.sd-option').forEach(function (o) {
        o.classList.remove('active');
        o.setAttribute('aria-selected', 'false');
      });
      optEl.classList.add('active');
      optEl.setAttribute('aria-selected', 'true');

      // Close
      wrap.classList.remove('open');
      trigger.setAttribute('aria-expanded', 'false');

      // Reset search
      if (showSearch) {
        const searchInput = dropdown.querySelector('.sd-search');
        searchInput.value = '';
        filterOptions(optionsList, '', emptyEl);
      }

      // Trigger action
      if (onchangeAction === 'submit-form') {
        const form = formId
          ? document.getElementById(formId)
          : wrap.closest('form');
        if (form) form.submit();
      } else if (onchangeAction && typeof window[onchangeAction] === 'function') {
        window[onchangeAction](newValue, newLabel, wrap);
      }

      // Always dispatch sd-change so any listener can react
      wrap.dispatchEvent(new CustomEvent('sd-change', {
        bubbles: true,
        detail: { name: name, value: newValue, label: newLabel }
      }));
    });

    // Search filtering
    if (showSearch) {
      const searchInput = dropdown.querySelector('.sd-search');
      searchInput.addEventListener('input', function () {
        filterOptions(optionsList, this.value.trim(), emptyEl);
      });
      // Prevent form submission on Enter inside search
      searchInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') e.preventDefault();
      });
    }

    wrap._sd = { hiddenInput, trigger, dropdown, optionsList, options };
  }

  function filterOptions(optionsList, query, emptyEl) {
    const q = query.toLowerCase();
    let hasVisible = false;
    optionsList.querySelectorAll('.sd-option').forEach(function (opt) {
      const text = opt.textContent.toLowerCase();
      const match = !q || text.includes(q);
      opt.classList.toggle('hidden', !match);
      if (match) hasVisible = true;
    });
    emptyEl.classList.toggle('visible', !hasVisible);
  }

  function checkDropDirection(wrap, dropdown) {
    // Disabled intentionally: User explicitly requested dropdowns to ALWAYS 
    // open downwards, even on mobile devices.
    wrap.classList.remove('drop-up');
  }

  function closeAll() {
    document.querySelectorAll('.sd-wrap.open').forEach(function (w) {
      w.classList.remove('open');
      const trig = w.querySelector('.sd-trigger');
      if (trig) trig.setAttribute('aria-expanded', 'false');
    });
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  // ── Auto-convert existing <select> elements with class "sd-convert" ──
  function convertSelect(sel) {
    const wrap = document.createElement('div');
    wrap.className = 'sd-wrap';
    wrap.dataset.sd = sel.id || '';
    wrap.dataset.sdName = sel.name || sel.id || '';
    wrap.dataset.sdValue = sel.value || '';
    wrap.dataset.sdPlaceholder = '';

    // Copy data attributes from parent (for icon, etc.)
    const parent = sel.closest('.c-filter-dropdown');
    if (parent) {
      const trigger = parent.querySelector('.c-filter-dropdown__trigger');
      if (trigger) {
        const icon = trigger.querySelector('.c-filter-dropdown__icon');
        if (icon) {
          // Store icon class for later use
          const iconClass = Array.from(icon.classList).join(' ');
          wrap.dataset.icon = iconClass;
        }
      }
    }

    // Copy onchange behavior
    if (sel.hasAttribute('onchange')) {
      const oc = sel.getAttribute('onchange');
      if (oc.includes('.submit()')) {
        wrap.dataset.sdOnchange = 'submit-form';
        // Extract form ID if present
        const match = oc.match(/getElementById\(['"]([^'"]+)['"]\)/);
        if (match) {
          wrap.dataset.sdForm = match[1];
        }
      }
    }

    // Copy class context
    if (sel.classList.contains('appt-filter-select') ||
        sel.classList.contains('c-filter-dropdown__select') ||
        sel.classList.contains('mypets-filter-select') ||
        sel.classList.contains('filter-select')) {
      // inherits from parent context
    }

    // Build options data
    const dataDiv = document.createElement('div');
    dataDiv.className = 'sd-data';
    dataDiv.style.display = 'none';

    sel.querySelectorAll('option').forEach(function (opt, i) {
      const span = document.createElement('span');
      span.dataset.val = opt.value;
      span.textContent = opt.textContent.trim();
      dataDiv.appendChild(span);

      // First option is usually the placeholder
      if (i === 0 && (!opt.value || opt.value === '' || opt.value === 'all')) {
        wrap.dataset.sdPlaceholder = opt.textContent.trim();
      }
    });

    wrap.appendChild(dataDiv);

    // Replace select in DOM
    sel.parentNode.insertBefore(wrap, sel);
    sel.remove();

    // Build the dropdown
    buildDropdown(wrap);
    return wrap;
  }

  // ── Public API ──
  SD.init = function () {
    // 1) Initialize pre-built [data-sd] wrappers
    document.querySelectorAll('.sd-wrap[data-sd]:not(.sd-ready)').forEach(function (wrap) {
      buildDropdown(wrap);
      wrap.classList.add('sd-ready');
    });

    // 2) Auto-convert <select> elements with .sd-convert
    document.querySelectorAll('select.sd-convert:not(.sd-converted)').forEach(function (sel) {
      sel.classList.add('sd-converted');
      convertSelect(sel);
    });
  };

  SD.refresh = function (wrap) {
    // Re-build a specific dropdown (e.g., after dynamically adding options)
    const old = wrap.querySelector('.sd-trigger');
    if (old) old.remove();
    const oldDrop = wrap.querySelector('.sd-dropdown');
    if (oldDrop) oldDrop.remove();
    const oldInput = wrap.querySelector('input[type="hidden"]');
    if (oldInput) oldInput.remove();
    wrap.classList.remove('sd-ready');
    buildDropdown(wrap);
    wrap.classList.add('sd-ready');
  };

  // getValue helper
  SD.getValue = function (wrap) {
    const input = wrap.querySelector('input[type="hidden"]');
    return input ? input.value : '';
  };

  // setValue helper
  SD.setValue = function (wrap, value) {
    if (!wrap._sd) return;
    const { hiddenInput, trigger, optionsList } = wrap._sd;
    hiddenInput.value = value;
    wrap.dataset.sdValue = value;

    optionsList.querySelectorAll('.sd-option').forEach(function (opt) {
      if (opt.dataset.value === value) {
        opt.classList.add('active');
        opt.setAttribute('aria-selected', 'true');
        trigger.querySelector('.sd-label').textContent = opt.textContent;
        trigger.classList.toggle('has-value', !!value);
      } else {
        opt.classList.remove('active');
        opt.setAttribute('aria-selected', 'false');
      }
    });
  };

  // Close dropdowns on outside click
  document.addEventListener('click', function (e) {
    if (!e.target.closest('.sd-wrap')) {
      closeAll();
    }
  });

  // Close on Escape
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeAll();
  });

  // Expose globally
  window.SearchableDropdown = SD;

  // Auto-init on DOMContentLoaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', SD.init);
  } else {
    SD.init();
  }

})();
