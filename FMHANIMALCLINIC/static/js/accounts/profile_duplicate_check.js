document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('profileEditForm');
  if (!form) return;

  const firstName = form.querySelector('[name="first_name"]');
  const lastName = form.querySelector('[name="last_name"]');
  const email = form.querySelector('[name="email"]');
  const nameNote = form.querySelector('[data-duplicate-note="name"]');
  const emailNote = form.querySelector('[data-duplicate-note="email"]');
  const checkError = form.querySelector('[data-duplicate-check-error]');
  if (!firstName || !lastName || !email || !nameNote || !emailNote || !checkError) return;

  let debounceTimer;
  let latestRequest = 0;

  function checkForDuplicates() {
    const requestId = ++latestRequest;
    window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(async () => {
      const params = new URLSearchParams({
        first_name: firstName.value.trim(),
        last_name: lastName.value.trim(),
        email: email.value.trim(),
      });

      try {
        const response = await fetch(`${form.dataset.duplicateCheckUrl}?${params}`, {
          headers: { Accept: 'application/json' },
        });
        if (!response.ok) {
          throw new Error(`Duplicate check failed with status ${response.status}.`);
        }

        const conflicts = await response.json();
        if (requestId !== latestRequest) return;
        nameNote.hidden = !conflicts.name_exists;
        emailNote.hidden = !conflicts.email_exists;
        checkError.hidden = true;
      } catch (error) {
        if (requestId === latestRequest) {
          nameNote.hidden = true;
          emailNote.hidden = true;
          checkError.hidden = false;
        }
        console.error('Unable to check profile duplicates.', error);
      }
    }, 350);
  }

  [firstName, lastName, email].forEach((input) => {
    input.addEventListener('input', checkForDuplicates);
    input.addEventListener('change', checkForDuplicates);
  });
  checkForDuplicates();
});
