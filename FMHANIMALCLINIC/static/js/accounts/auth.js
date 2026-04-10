document.addEventListener('DOMContentLoaded', function() {
  
  // ==========================================
  // PASSWORD TOGGLE
  // ==========================================
  const passwordToggles = document.querySelectorAll('.password-toggle');
  passwordToggles.forEach(toggle => {
    toggle.addEventListener('click', function() {
      // If it uses data-target (register page)
      const targetId = this.getAttribute('data-target');
      let input;
      
      if (targetId) {
        input = document.getElementById(targetId);
      } else {
        // Fallback for simple single-password structures (login page)
        const wrapper = this.closest('.auth-input-wrapper');
        input = wrapper ? wrapper.querySelector('input') : null;
      }
      
      const icon = this.querySelector('i');
      
      if (input) {
        if (input.type === 'password') {
          input.type = 'text';
          icon.classList.remove('bx-hide');
          icon.classList.add('bx-show');
        } else {
          input.type = 'password';
          icon.classList.remove('bx-show');
          icon.classList.add('bx-hide');
        }
      }
    });
  });

  // ==========================================
  // PASSWORD STRENGTH INDICATOR
  // ==========================================
  const passwordInput = document.getElementById('regPassword');
  const strengthBar = document.querySelector('.strength-bar span');
  const strengthText = document.querySelector('.strength-text');

  if (passwordInput && strengthBar && strengthText) {
    passwordInput.addEventListener('input', function() {
      const password = this.value;
      let strength = 0;
      
      if (password.length >= 8) strength += 25;
      if (/[A-Z]/.test(password)) strength += 25;
      if (/[0-9]/.test(password)) strength += 25;
      if (/[^A-Za-z0-9]/.test(password)) strength += 25;

      strengthBar.style.width = strength + '%';
      
      if (strength <= 25) {
        strengthBar.style.background = '#e63946';
        strengthText.textContent = 'Weak';
        strengthText.style.color = '#e63946';
      } else if (strength <= 50) {
        strengthBar.style.background = '#f4a261';
        strengthText.textContent = 'Fair';
        strengthText.style.color = '#f4a261';
      } else if (strength <= 75) {
        strengthBar.style.background = '#2a9d8f';
        strengthText.textContent = 'Good';
        strengthText.style.color = '#2a9d8f';
      } else {
        strengthBar.style.background = '#009688';
        strengthText.textContent = 'Strong';
        strengthText.style.color = '#009688';
      }
    });
  }

  // ==========================================
  // LOGIN FORM VALIDATION
  // ==========================================
  const loginForm = document.getElementById('loginForm');
  if (loginForm) {
    loginForm.addEventListener('submit', function(e) {
      const usernameInput = document.getElementById('username');
      const passwordInput = document.getElementById('password');
      let hasError = false;

      // Clear previous errors
      loginForm.querySelectorAll('.auth-error').forEach(el => el.remove());
      loginForm.querySelectorAll('.auth-input-wrapper.error').forEach(el => el.classList.remove('error'));

      if (!usernameInput || !usernameInput.value.trim()) {
        e.preventDefault();
        if(usernameInput) showError(usernameInput, 'Username is required');
        hasError = true;
      }

      if (!passwordInput || !passwordInput.value) {
        e.preventDefault();
        if(passwordInput) showError(passwordInput, 'Password is required');
        hasError = true;
      }

      if (!hasError) {
        const submitBtn = loginForm.querySelector('.auth-submit');
        if (submitBtn) {
          submitBtn.classList.add('loading');
          submitBtn.innerHTML = '<i class="bx bx-loader-alt bx-spin"></i> Signing In...';
        }
      }
    });
  }

  // ==========================================
  // REGISTER FORM VALIDATION
  // ==========================================
  const registerForm = document.getElementById('registerForm');
  if (registerForm) {
    registerForm.addEventListener('submit', function(e) {
      const firstName = document.getElementById('firstName');
      const lastName = document.getElementById('lastName');
      const username = document.getElementById('username');
      const email = document.getElementById('regEmail');
      const phone = document.getElementById('phone');
      const password = document.getElementById('regPassword');
      const confirmPassword = document.getElementById('confirmPassword');
      const terms = registerForm.querySelector('input[name="terms"]');
      let hasError = false;

      // Clear previous errors
      document.querySelectorAll('.auth-error').forEach(el => el.remove());
      document.querySelectorAll('.auth-input-wrapper.error').forEach(el => el.classList.remove('error'));

      if (!firstName || !firstName.value.trim()) {
        e.preventDefault();
        if(firstName) showError(firstName, 'First name is required');
        hasError = true;
      }

      if (!lastName || !lastName.value.trim()) {
        e.preventDefault();
        if(lastName) showError(lastName, 'Last name is required');
        hasError = true;
      }

      if (!username || !username.value.trim()) {
        e.preventDefault();
        if(username) showError(username, 'Username is required');
        hasError = true;
      }

      if (!email || !email.value.trim()) {
        e.preventDefault();
        if(email) showError(email, 'Email is required');
        hasError = true;
      } else if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value)) {
        e.preventDefault();
        showError(email, 'Please enter a valid email');
        hasError = true;
      }

      if (!phone || !phone.value.trim()) {
        e.preventDefault();
        if(phone) showError(phone, 'Phone number is required');
        hasError = true;
      } else if (phone && phone.value.trim().length !== 11) {
        e.preventDefault();
        showError(phone, 'Phone number must be exactly 11 digits');
        hasError = true;
      }

      if (!password || !password.value) {
        e.preventDefault();
        if(password) showError(password, 'Password is required');
        hasError = true;
      } else if (password && password.value.length < 8) {
        e.preventDefault();
        showError(password, 'Password must be at least 8 characters');
        hasError = true;
      }

      if (!confirmPassword || !confirmPassword.value) {
        e.preventDefault();
        if(confirmPassword) showError(confirmPassword, 'Please confirm your password');
        hasError = true;
      } else if (password && confirmPassword && password.value !== confirmPassword.value) {
        e.preventDefault();
        showError(confirmPassword, 'Passwords do not match');
        hasError = true;
      }

      if (terms && !terms.checked) {
        e.preventDefault();
        alert('Please agree to the Terms of Service and Privacy Policy');
        hasError = true;
      }

      if (!hasError) {
        const submitBtn = registerForm.querySelector('.auth-submit');
        if (submitBtn) {
          submitBtn.classList.add('loading');
          submitBtn.innerHTML = '<i class="bx bx-loader-alt bx-spin"></i> Creating Account...';
        }
      }
    });
  }

  // ==========================================
  // UTILITY: SHOW ERROR
  // ==========================================
  function showError(input, message) {
    if (!input) return;
    const wrapper = input.closest('.auth-input-wrapper');
    if (wrapper) {
      wrapper.classList.add('error');
      const error = document.createElement('span');
      error.className = 'auth-error';
      error.textContent = message;
      wrapper.parentNode.appendChild(error);
    }
  }
});
