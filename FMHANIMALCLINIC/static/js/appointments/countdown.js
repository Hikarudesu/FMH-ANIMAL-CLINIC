(function () {
  var countdowns = document.querySelectorAll('[data-auto-cancel-at]');
  if (!countdowns.length) return;

  function updateCountdowns() {
    countdowns.forEach(function (countdown) {
      var deadline = Date.parse(countdown.dataset.autoCancelAt);
      var display = countdown.querySelector('[data-countdown-value]');
      if (!Number.isFinite(deadline) || !display) return;

      var remaining = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
      var hours = Math.floor(remaining / 3600);
      var minutes = Math.floor((remaining % 3600) / 60);
      var seconds = remaining % 60;

      display.textContent = remaining === 0
        ? 'Cancellation due'
        : [hours, minutes, seconds].map(function (value) {
            return String(value).padStart(2, '0');
          }).join(':');
    });
  }

  updateCountdowns();
  window.setInterval(updateCountdowns, 1000);
})();