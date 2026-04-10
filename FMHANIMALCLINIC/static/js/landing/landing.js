/* ============================================
   FMHSYNC Landing Page — JavaScript (Enhanced)
   ============================================ */

// Disable browser's automatic scroll restoration
if (history.scrollRestoration) {
  history.scrollRestoration = "manual";
}

// Force scroll to top before DOMContentLoaded
window.scrollTo(0, 0);

document.addEventListener("DOMContentLoaded", () => {
  // Scroll to top on page load (double check)
  window.scrollTo(0, 0);

  /* ---------- NAVBAR SCROLL EFFECT ---------- */
  const navbar = document.querySelector(".navbar");
  const bottomNav = document.getElementById("bottomNav");
  let lastScrollY = 0;

  window.addEventListener("scroll", () => {
    const currentScrollY = window.scrollY;

    if (currentScrollY > 50) {
      navbar.classList.add("scrolled");
    } else {
      navbar.classList.remove("scrolled");
    }

    // Bottom nav: hide on scroll down, show on scroll up
    if (bottomNav) {
      if (currentScrollY > lastScrollY && currentScrollY > 100) {
        bottomNav.classList.add("hidden");
      } else {
        bottomNav.classList.remove("hidden");
      }
    }

    lastScrollY = currentScrollY;
  });

  /* ---------- MOBILE NAVIGATION ---------- */
  const navToggle = document.querySelector(".nav-toggle");
  const navMobile = document.querySelector(".nav-mobile");
  const navOverlay = document.querySelector(".nav-overlay");
  const mobileClose = document.querySelector(".mobile-close");

  function openMobileNav() {
    if (navMobile) navMobile.classList.add("active");
    if (navOverlay) navOverlay.classList.add("active");
    if (navToggle) {
      navToggle.classList.add("active");
      navToggle.setAttribute("aria-expanded", "true");
      navToggle.setAttribute("aria-label", "Close navigation menu");
    }
    document.body.style.overflow = "hidden";
  }

  function closeMobileNav() {
    if (navMobile) navMobile.classList.remove("active");
    if (navOverlay) navOverlay.classList.remove("active");
    if (navToggle) {
      navToggle.classList.remove("active");
      navToggle.setAttribute("aria-expanded", "false");
      navToggle.setAttribute("aria-label", "Open navigation menu");
    }
    document.body.style.overflow = "";
  }

  // Toggle button logic
  if (navToggle) {
    navToggle.addEventListener("click", () => {
      const isActive = navMobile.classList.contains("active");
      if (isActive) {
        closeMobileNav();
      } else {
        openMobileNav();
      }
    });
  }

  // Only wire mobile nav events if the elements exist
  if (navOverlay) {
    navOverlay.addEventListener("click", closeMobileNav);
  }

  // Close on mobile close button if present
  if (mobileClose) {
    mobileClose.addEventListener("click", closeMobileNav);
  }

  // Close mobile nav on link click
  const mobileLinks = document.querySelectorAll(".nav-mobile a");
  mobileLinks.forEach((link) => {
    link.addEventListener("click", closeMobileNav);
  });

  /* ---------- SMOOTH SCROLL ---------- */
  document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
    anchor.addEventListener("click", function (e) {
      const href = this.getAttribute("href");
      if (href === "#") return;
      const target = document.querySelector(href);
      if (target) {
        e.preventDefault();
        const navHeight = navbar.offsetHeight;
        const targetPosition = target.offsetTop - navHeight;
        window.scrollTo({
          top: targetPosition,
          behavior: "smooth",
        });
      }
    });
  });

  /* ---------- SCROLL SPY (Active Links) ---------- */
  const sections = document.querySelectorAll("section[id]");
  const navLinksList = document.querySelectorAll(
    ".nav-links a, .mobile-links a",
  );

  function scrollSpy() {
    let currentId = "";
    const scrollPos = window.scrollY;
    // Increased offset for better detection as you scroll into a section
    const offset = navbar.offsetHeight + 150;

    sections.forEach((section) => {
      const top = section.offsetTop - offset;
      const bottom = top + section.offsetHeight;

      if (scrollPos >= top && scrollPos < bottom) {
        currentId = section.getAttribute("id");
      }
    });

    if (currentId) {
      navLinksList.forEach((link) => {
        const href = link.getAttribute("href");

        // Remove active from any hash links specifically
        if (href.startsWith("#")) {
          link.classList.remove("active");
        }

        // Check if link points to the current section
        if (
          href === "#" + currentId ||
          (currentId === "home" &&
            (href === "/" || href.includes("landing_page")))
        ) {
          link.classList.add("active");
        }
      });
    }
  }

  window.addEventListener("scroll", scrollSpy);
  scrollSpy(); // Initialize on load

  /* ---------- HERO TEXT ANIMATION (Typewriter) ---------- */
  const heroTitle = document.querySelector(".hero-text h1");
  if (heroTitle) {
    // Text is already animated via CSS, but we add typing cursor effect
    const heroDescription = document.querySelector(".hero-text > p");
    if (heroDescription) {
      const originalText = heroDescription.textContent;
      heroDescription.textContent = "";
      heroDescription.style.opacity = "1";
      heroDescription.style.animation = "none";

      let charIndex = 0;
      const typingSpeed = 25;

      function typeText() {
        if (charIndex < originalText.length) {
          heroDescription.textContent += originalText.charAt(charIndex);
          charIndex++;
          setTimeout(typeText, typingSpeed);
        } else {
          // Add cursor after typing is complete
          const cursor = document.createElement("span");
          cursor.classList.add("typing-cursor");
          heroDescription.appendChild(cursor);

          // Remove cursor after a delay
          setTimeout(() => {
            cursor.style.animation = "none";
            cursor.style.opacity = "0";
          }, 3000);
        }
      }

      // Start typing after hero animations complete
      setTimeout(typeText, 1200);
    }
  }

  /* ---------- SCROLL ANIMATIONS ---------- */
  const fadeElements = document.querySelectorAll(".fade-in");

  const observerOptions = {
    root: null,
    threshold: 0.15,
    rootMargin: "0px 0px -80px 0px",
  };

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("visible");
        observer.unobserve(entry.target);
      }
    });
  }, observerOptions);

  fadeElements.forEach((el) => observer.observe(el));

  /* ---------- APPOINTMENT BUTTON ---------- */
  /* Button now uses a standard href link — no JS interception needed */

  /* ---------- PARALLAX EFFECT FOR FLOATING ELEMENTS ---------- */
  const floatElements = document.querySelectorAll(".float-element");

  if (floatElements.length > 0) {
    window.addEventListener("mousemove", (e) => {
      const x = (e.clientX / window.innerWidth - 0.5) * 20;
      const y = (e.clientY / window.innerHeight - 0.5) * 20;

      floatElements.forEach((el, index) => {
        const factor = (index + 1) * 0.5;
        el.style.setProperty("--parallax-x", `${x * factor}px`);
        el.style.setProperty("--parallax-y", `${y * factor}px`);
      });
    });
  }

  /* ---------- CONTACT PAGE - PREMIUM BRANCH SWITCHER ---------- */
  // Use dynamic branch data injected from Django template, or empty array
  const branchData = window.branchData || [];

  let currentBranchIdx = 0;

  function switchBranch(direction) {
    if (direction === "next") {
      currentBranchIdx = (currentBranchIdx + 1) % branchData.length;
    } else {
      currentBranchIdx =
        (currentBranchIdx - 1 + branchData.length) % branchData.length;
    }
    updateBranchUI();
  }

  function updateBranchUI() {
    const data = branchData[currentBranchIdx];

    // Update Text Elements
    const badge = document.getElementById("branch-badge");
    const title = document.getElementById("branch-title");
    const address = document.getElementById("branch-address");
    const phone = document.getElementById("branch-phone");
    const hours = document.getElementById("branch-hours");
    const email = document.getElementById("branch-email");
    const mapFrame = document.getElementById("main-branch-map");

    if (badge) badge.textContent = data.badge;
    if (title) title.textContent = data.title;
    if (address) address.textContent = data.address;
    if (phone) phone.textContent = data.phone;
    if (hours) hours.textContent = data.hours;
    if (email) email.textContent = data.email;
    if (mapFrame) mapFrame.src = data.map;

    // Update Social Links for Branch using both ID and Class selectors to ensure coverage
    const fbLinks = document.querySelectorAll("#branch-fb, .connect-icon.fb");
    const igLinks = document.querySelectorAll("#branch-ig, .connect-icon.ig");
    const msLinks = document.querySelectorAll("#branch-ms, .connect-icon.ms");
    const tkLinks = document.querySelectorAll("#branch-tk, .connect-icon.tk");

    fbLinks.forEach((link) => {
      if (link) link.href = data.socials.fb;
    });
    igLinks.forEach((link) => {
      if (link) link.href = data.socials.ig;
    });
    msLinks.forEach((link) => {
      if (link) link.href = data.socials.ms;
    });
    tkLinks.forEach((link) => {
      if (link) link.href = data.socials.tk;
    });

    // Optional: Add a small fade animation to the text
    const infoCol = document.querySelector(".branch-info-col");
    if (infoCol) {
      infoCol.style.opacity = "0";
      setTimeout(() => {
        infoCol.style.opacity = "1";
        infoCol.style.transition = "opacity 0.4s ease";
      }, 50);
    }
  }

  // Expose to window for inline onclick handlers
  window.switchBranch = switchBranch;

  /* ---------- CONTACT FORM HANDLING ---------- */
  const contactForm = document.getElementById("contactForm");
  if (contactForm) {
    // Helper: show inline error on a field
    function showFieldError(field, message) {
      clearFieldError(field);
      field.classList.add("input-error");
      const errorEl = document.createElement("span");
      errorEl.className = "field-error-msg";
      errorEl.textContent = message;
      errorEl.style.cssText =
        "color: #e63946; font-size: 0.8rem; margin-top: 4px; display: block; font-weight: 500;";
      field.parentNode.appendChild(errorEl);
    }

    function clearFieldError(field) {
      field.classList.remove("input-error");
      const existing = field.parentNode.querySelector(".field-error-msg");
      if (existing) existing.remove();
    }

    // Clear errors on input
    contactForm.querySelectorAll("input, select, textarea").forEach((field) => {
      field.addEventListener("input", () => clearFieldError(field));
      field.addEventListener("change", () => clearFieldError(field));
    });

    contactForm.addEventListener("submit", function (e) {
      e.preventDefault();

      // Get form values
      const fullName = document.getElementById("fullName");
      const email = document.getElementById("email");
      const phone = document.getElementById("phone");
      const branch = document.getElementById("branch");
      const petName = document.getElementById("petName");
      const message = document.getElementById("message");

      let hasError = false;

      // Validation
      if (!fullName.value.trim()) {
        showFieldError(fullName, "Please enter your name");
        hasError = true;
      }

      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!email.value.trim()) {
        showFieldError(email, "Please enter your email");
        hasError = true;
      } else if (!emailRegex.test(email.value.trim())) {
        showFieldError(email, "Please enter a valid email");
        hasError = true;
      }

      const phoneRegex = /^\d{11}$/;
      if (!phone.value.trim()) {
        showFieldError(phone, "Please enter your phone number");
        hasError = true;
      } else if (!phoneRegex.test(phone.value.trim())) {
        showFieldError(phone, "Phone number must be exactly 11 digits");
        hasError = true;
      }


      if (!branch.value) {
        showFieldError(branch, "Please select a branch");
        hasError = true;
      }
      if (!message.value.trim()) {
        showFieldError(message, "Please enter your message");
        hasError = true;
      }

      if (hasError) return;

      // Get CSRF token
      const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

      // Prepare form data
      const formData = {
        fullName: fullName.value.trim(),
        email: email.value.trim(),
        phone: phone.value.trim(),
        branch: branch.value,
        message: message.value.trim(),
      };

      // Debug logging
      console.log('Submitting inquiry:', formData);
      console.log('CSRF Token:', csrfToken);

      // Disable submit button
      const submitBtn = contactForm.querySelector('button[type="submit"]');
      const originalText = submitBtn.innerHTML;
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<i class="bx bx-loader-alt bx-spin"></i> Sending...';

      // Submit to backend
      fetch('/inquiries/submit/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify(formData),
      })
        .then(response => {
          console.log('Response status:', response.status);
          return response.json();
        })
        .then(data => {
          console.log('Response data:', data);
          if (data.success) {
            // Show success message
            const formSuccess = document.getElementById("formSuccess");
            formSuccess.style.display = "flex";

            // Reset form
            contactForm.reset();

            // Hide success message after 4 seconds
            setTimeout(() => {
              formSuccess.style.display = "none";
            }, 4000);
          } else {
            // Show error
            alert('Failed to send message: ' + (data.error || JSON.stringify(data.errors)));
            console.error('Form submission error:', data.errors || data.error);
          }
        })
        .catch(error => {
          console.error('Network error:', error);
          alert('Network error. Please check your connection and try again. Error: ' + error.message);
        })
        .finally(() => {
          // Re-enable submit button
          submitBtn.disabled = false;
          submitBtn.innerHTML = originalText;
        });
    });
  }

  /* ---------- SATISFIED CUSTOMERS CAROUSEL ---------- */
  const carouselTrack = document.getElementById("carouselTrack");
  const carouselPrevBtn = document.getElementById("carouselPrevBtn");
  const carouselNextBtn = document.getElementById("carouselNextBtn");
  const carouselContainer = document.querySelector(".carousel-container");

  // Helper to check if on mobile
  const isMobile = () => window.innerWidth <= 768;

  if (carouselTrack) {
    let cardCount = carouselTrack.children.length;
    if (cardCount > 0) {
      // Only clone cards for desktop (transform-based scroll)
      if (!isMobile()) {
        const cards = Array.from(carouselTrack.children);
        cards.forEach((card) => {
          const clone = card.cloneNode(true);
          carouselTrack.appendChild(clone);
        });
      }

      let currentScroll = 0;
      let isTransitioning = false;
      let autoScrollInterval;

      const getDims = () => {
        const card = carouselTrack.children[0];
        const trackStyle = window.getComputedStyle(carouselTrack);
        const gap = parseFloat(trackStyle.gap) || 0;
        const step = card.offsetWidth + gap;
        const totalWidth = step * cardCount;
        return { step, totalWidth };
      };

      function updatePosition() {
        carouselTrack.style.transform = `translateX(-${currentScroll}px)`;
      }

      function startAutoScroll() {
        clearInterval(autoScrollInterval);
        autoScrollInterval = setInterval(() => {
          const { totalWidth } = getDims();
          currentScroll += 0.5; // Smooth scroll speed

          if (currentScroll >= totalWidth) {
            currentScroll = 0;
          }
          updatePosition();
        }, 20);
      }

      function scrollByStep(direction) {
        if (isTransitioning) return;
        isTransitioning = true;
        clearInterval(autoScrollInterval);

        const { step, totalWidth } = getDims();

        // Use transition for button clicks
        carouselTrack.style.transition =
          "transform 0.5s cubic-bezier(0.4, 0, 0.2, 1)";

        if (direction === "next") {
          currentScroll += step;
        } else {
          currentScroll -= step;
        }

        updatePosition();

        setTimeout(() => {
          carouselTrack.style.transition = "none";
          const { totalWidth: latestWidth } = getDims();

          // Reset to start/end clone if needed for seamless appearance
          if (currentScroll >= latestWidth) currentScroll = 0;
          if (currentScroll < 0) currentScroll = latestWidth - step;

          updatePosition();
          isTransitioning = false;
          startAutoScroll();
        }, 500);
      }

      if (carouselPrevBtn)
        carouselPrevBtn.addEventListener("click", () => scrollByStep("prev"));
      if (carouselNextBtn)
        carouselNextBtn.addEventListener("click", () => scrollByStep("next"));

      // Desktop: auto-scroll and hover pause
      if (!isMobile()) {
        carouselTrack.addEventListener("mouseenter", () =>
          clearInterval(autoScrollInterval),
        );
        carouselTrack.addEventListener("mouseleave", () => startAutoScroll());
        startAutoScroll();
      } else {
        // Mobile: auto-scroll using native scrollLeft + manual swipe
        let mobileAutoInterval;
        const container = carouselContainer || carouselTrack.parentElement;

        function startMobileAutoScroll() {
          clearInterval(mobileAutoInterval);
          mobileAutoInterval = setInterval(() => {
            const maxScroll = container.scrollWidth - container.clientWidth;
            if (container.scrollLeft >= maxScroll - 2) {
              container.scrollTo({ left: 0, behavior: "smooth" });
            } else {
              const card = carouselTrack.children[0];
              const gap = parseFloat(window.getComputedStyle(carouselTrack).gap) || 0;
              const step = card.offsetWidth + gap;
              container.scrollBy({ left: step, behavior: "smooth" });
            }
          }, 3000);
        }

        // Pause on touch, resume after
        container.addEventListener("touchstart", () => clearInterval(mobileAutoInterval), { passive: true });
        container.addEventListener("touchend", () => {
          setTimeout(startMobileAutoScroll, 2000);
        }, { passive: true });

        startMobileAutoScroll();
      }
    }
  }

  /* ================================================================
     14. GLOBAL MESSAGES (TOASTS) AUTO-DISMISS
     ================================================================ */
  const globalMessages = document.querySelectorAll(".portal-message");
  if (globalMessages.length > 0) {
    setTimeout(() => {
      globalMessages.forEach((msg) => {
        msg.style.opacity = "0";
        msg.style.transform = "translateX(50px)";
        msg.style.transition = "all 0.4s ease";
        setTimeout(() => msg.remove(), 400);
      });
    }, 5000);
  }
});

/* ================================================================
   15. BOOKING TYPE MODAL FUNCTIONALITY
   ================================================================ */
function openBookingSelectionModal(event) {
  if (event) {
    event.preventDefault();
  }
  const modal = document.getElementById("bookingSelectionModal");
  if (modal) {
    modal.classList.add("active");
  }
}

function closeBookingSelectionModal() {
  const modal = document.getElementById("bookingSelectionModal");
  if (modal) {
    modal.classList.remove("active");
  }
}

// Close modal when clicking outside of it
document.addEventListener("click", (e) => {
  const modal = document.getElementById("bookingSelectionModal");
  if (modal && e.target === modal) {
    closeBookingSelectionModal();
  }
});
