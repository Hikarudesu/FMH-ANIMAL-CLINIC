document.addEventListener('DOMContentLoaded', function() {
  // Auto-dismiss Django Messages (Toasts) after 5 seconds
  const portalMessages = document.querySelectorAll('.portal-message');
  if (portalMessages.length > 0) {
    setTimeout(() => {
      portalMessages.forEach(msg => {
        msg.style.opacity = '0';
        msg.style.transform = 'translateY(20px) scale(0.95)';
        msg.style.transition = 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)';
        setTimeout(() => msg.remove(), 400); // Wait for transition to finish
      });
    }, 5000);
  }
});
