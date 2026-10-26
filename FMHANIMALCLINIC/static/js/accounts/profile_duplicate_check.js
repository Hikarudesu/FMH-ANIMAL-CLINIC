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
  let allowConfirmedSubmit = false;
  let submissionPending = false;

  function getCurrentValues() {
    return {
      first_name: firstName.value.trim(),
      last_name: lastName.value.trim(),
      email: email.value.trim(),
    };
  }

  function getValuesKey(values) {
    return JSON.stringify(values);
  }

  async function checkForDuplicates() {
    const values = getCurrentValues();
    const valuesKey = getValuesKey(values);
    const requestId = ++latestRequest;
    const params = new URLSearchParams(values);

    try {
      const response = await fetch(`${form.dataset.duplicateCheckUrl}?${params}`, {
        headers: { Accept: 'application/json' },
      });
      if (!response.ok) {
        throw new Error(`Duplicate check failed with status ${response.status}.`);
      }

      const conflicts = await response.json();
      if (
        requestId !== latestRequest
        || valuesKey !== getValuesKey(getCurrentValues())
      ) return null;
      nameNote.hidden = !conflicts.name_exists;
      emailNote.hidden = !conflicts.email_exists;
      email.setAttribute('aria-invalid', conflicts.email_exists ? 'true' : 'false');
      checkError.hidden = true;
      return conflicts;
    } catch (error) {
      if (
        requestId === latestRequest
        && valuesKey === getValuesKey(getCurrentValues())
      ) {
        nameNote.hidden = true;
        emailNote.hidden = true;
        email.removeAttribute('aria-invalid');
        checkError.hidden = false;
      }
      console.error('Unable to check profile duplicates.', error);
      throw error;
    }
  }

  function resubmitAfterCheck(submitter) {
    allowConfirmedSubmit = true;
    if (typeof form.requestSubmit === 'function') {
      if (submitter) form.requestSubmit(submitter);
      else form.requestSubmit();
    } else {
      allowConfirmedSubmit = false;
      form.submit();
    }
  }

  function scheduleDuplicateCheck() {
    window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(() => {
      checkForDuplicates().catch(() => {});
    }, 350);
  }

  [firstName, lastName, email].forEach((input) => {
    input.addEventListener('input', scheduleDuplicateCheck);
    input.addEventListener('change', scheduleDuplicateCheck);
  });

  form.addEventListener('submit', async (event) => {
    if (allowConfirmedSubmit) {
      allowConfirmedSubmit = false;
      return;
    }
    event.preventDefault();
    if (submissionPending) return;

    submissionPending = true;
    window.clearTimeout(debounceTimer);
    try {
      const conflicts = await checkForDuplicates();
      if (!conflicts) {
        checkError.hidden = false;
        return;
      }
      if (conflicts.email_exists) {
        email.focus();
        return;
      }

      resubmitAfterCheck(event.submitter);
    } catch (error) {
      checkError.hidden = false;
      resubmitAfterCheck(event.submitter);
    } finally {
      submissionPending = false;
    }
  });

  scheduleDuplicateCheck();
});
