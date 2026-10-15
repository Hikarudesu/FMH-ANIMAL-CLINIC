(function () {
  'use strict';

  const form = document.getElementById('ownerAppointmentHistorySearch');
  if (!form) return;

  const input = form.querySelector('.c-filter-bar__search-input');
  const dropdown = document.getElementById('ownerAppointmentHistorySearchDropdown');
  const searchUrl = form.dataset.searchUrl;
  if (!input || !dropdown || !searchUrl) return;

  let debounceTimer;
  let activeIndex = -1;
  let controller;

  function hideDropdown() {
    dropdown.classList.remove('active');
    dropdown.replaceChildren();
    input.setAttribute('aria-expanded', 'false');
    activeIndex = -1;
  }

  function showMessage(message) {
    const item = document.createElement('div');
    item.className = 'search-dropdown-empty';
    const icon = document.createElement('i');
    icon.className = 'bx bx-search-alt';
    const text = document.createElement('span');
    text.textContent = message;
    item.append(icon, text);
    dropdown.replaceChildren(item);
    dropdown.classList.add('active');
    input.setAttribute('aria-expanded', 'true');
    activeIndex = -1;
  }

  function selectSuggestion(item) {
    input.value = item.dataset.value;
    hideDropdown();
    form.requestSubmit();
  }

  function renderSuggestions(results) {
    dropdown.replaceChildren();
    if (!results.length) {
      showMessage('No matching appointments found');
      return;
    }

    results.forEach(result => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'search-dropdown-item';
      button.setAttribute('role', 'option');
      button.dataset.value = result.value;

      const icon = document.createElement('i');
      icon.className = 'bx bxs-dog';

      const info = document.createElement('span');
      info.className = 'item-info';
      const label = document.createElement('span');
      label.className = 'item-name';
      label.textContent = result.label;
      const subtitle = document.createElement('span');
      subtitle.className = 'item-sub';
      subtitle.textContent = result.subtitle;
      info.append(label, subtitle);
      button.append(icon, info);
      dropdown.append(button);
    });

    dropdown.classList.add('active');
    input.setAttribute('aria-expanded', 'true');
    activeIndex = -1;
  }

  async function loadSuggestions(query) {
    if (controller) controller.abort();
    controller = new AbortController();
    try {
      const url = new URL(searchUrl, window.location.origin);
      url.searchParams.set('q', query);
      const response = await fetch(url, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`Search request failed (${response.status})`);
      const data = await response.json();
      renderSuggestions(data.results);
    } catch (error) {
      if (error.name === 'AbortError') return;
      showMessage('Suggestions are unavailable. Press Enter to search.');
    }
  }

  input.setAttribute('aria-haspopup', 'listbox');
  input.setAttribute('aria-controls', dropdown.id);
  input.setAttribute('aria-expanded', 'false');

  input.addEventListener('input', function () {
    window.clearTimeout(debounceTimer);
    const query = input.value.trim();
    if (query.length < 2) {
      if (controller) controller.abort();
      hideDropdown();
      return;
    }
    debounceTimer = window.setTimeout(() => loadSuggestions(query), 220);
  });

  input.addEventListener('keydown', function (event) {
    const items = Array.from(dropdown.querySelectorAll('.search-dropdown-item'));
    if (event.key === 'Escape') {
      hideDropdown();
    } else if (event.key === 'ArrowDown' && items.length) {
      event.preventDefault();
      activeIndex = (activeIndex + 1) % items.length;
    } else if (event.key === 'ArrowUp' && items.length) {
      event.preventDefault();
      activeIndex = activeIndex <= 0 ? items.length - 1 : activeIndex - 1;
    } else if (event.key === 'Enter' && activeIndex >= 0 && items[activeIndex]) {
      event.preventDefault();
      selectSuggestion(items[activeIndex]);
      return;
    } else {
      return;
    }

    items.forEach((item, index) => {
      item.classList.toggle('active', index === activeIndex);
      item.setAttribute('aria-selected', index === activeIndex ? 'true' : 'false');
    });
  });

  dropdown.addEventListener('click', function (event) {
    const item = event.target.closest('.search-dropdown-item');
    if (item) selectSuggestion(item);
  });

  document.addEventListener('click', function (event) {
    if (!form.contains(event.target)) hideDropdown();
  });
}());
