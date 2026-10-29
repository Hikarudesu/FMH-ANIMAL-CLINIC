(() => {
  let titleSequence = 0;

  window.showCenteredConfirmation = function({
    title,
    message,
    confirmText = 'Confirm',
    cancelText = 'Cancel',
    tone = 'default',
  }) {
    return new Promise(resolve => {
      const dialog = document.createElement('dialog');
      const titleId = `centered-confirm-title-${++titleSequence}`;
      dialog.className = `centered-confirmation centered-confirmation--${tone}`;
      dialog.setAttribute('aria-labelledby', titleId);

      const content = document.createElement('div');
      content.className = 'centered-confirmation__content';

      const closeButton = document.createElement('button');
      closeButton.type = 'button';
      closeButton.className = 'centered-confirmation__close';
      closeButton.setAttribute('aria-label', 'Close confirmation');
      closeButton.innerHTML = "<i class='bx bx-x'></i>";
      closeButton.addEventListener('click', () => dialog.close('cancel'));

      const icon = document.createElement('span');
      icon.className = 'centered-confirmation__icon';
      icon.setAttribute('aria-hidden', 'true');
      icon.innerHTML = tone === 'danger'
        ? "<i class='bx bx-error-circle'></i>"
        : "<i class='bx bx-info-circle'></i>";

      const heading = document.createElement('h2');
      heading.className = 'centered-confirmation__title';
      heading.id = titleId;
      heading.textContent = title;

      const description = document.createElement('p');
      description.className = 'centered-confirmation__message';
      description.textContent = message;

      const actions = document.createElement('div');
      actions.className = 'centered-confirmation__actions';

      const cancelButton = document.createElement('button');
      cancelButton.type = 'button';
      cancelButton.className = 'centered-confirmation__button centered-confirmation__button--cancel';
      cancelButton.textContent = cancelText;
      cancelButton.addEventListener('click', () => dialog.close('cancel'));

      const confirmButton = document.createElement('button');
      confirmButton.type = 'button';
      confirmButton.className = 'centered-confirmation__button centered-confirmation__button--confirm';
      confirmButton.textContent = confirmText;
      confirmButton.addEventListener('click', () => dialog.close('confirm'));

      actions.append(cancelButton, confirmButton);
      content.append(closeButton, icon, heading, description, actions);
      dialog.appendChild(content);
      dialog.addEventListener('click', event => {
        if (event.target === dialog) dialog.close('cancel');
      });
      dialog.addEventListener('close', () => {
        resolve(dialog.returnValue === 'confirm');
        dialog.remove();
      }, {once: true});

      document.body.appendChild(dialog);
      dialog.showModal();
      cancelButton.focus();
    });
  };

  window.bindCenteredFormConfirmation = function(form, options) {
    let approvedSubmit = false;
    let confirmationPending = false;

    form.addEventListener('submit', async event => {
      if (approvedSubmit) {
        approvedSubmit = false;
        return;
      }

      event.preventDefault();
      if (confirmationPending) return;

      confirmationPending = true;
      try {
        const confirmationOptions = typeof options === 'function'
          ? options(event)
          : options;
        const confirmed = await window.showCenteredConfirmation(confirmationOptions);
        if (!confirmed) return;

        approvedSubmit = true;
        if (event.submitter) form.requestSubmit(event.submitter);
        else form.requestSubmit();
      } finally {
        confirmationPending = false;
      }
    });
  };
})();
