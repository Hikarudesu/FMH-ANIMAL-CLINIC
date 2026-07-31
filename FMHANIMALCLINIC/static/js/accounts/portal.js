document.addEventListener("DOMContentLoaded", function () {
  // Mobile Sidebar Toggle
  const wrapper = document.getElementById("portalWrapper");
  const toggle = document.getElementById("sidebarToggle");
  const overlay = document.getElementById("mobileOverlay");

  if (toggle) {
    toggle.addEventListener("click", () =>
      wrapper.classList.toggle("mobile-open"),
    );
  }
  if (overlay) {
    overlay.addEventListener("click", () =>
      wrapper.classList.remove("mobile-open"),
    );
  }

  // Profile Dropdown Toggle
  const profileBtn = document.getElementById("profileDropdownBtn");
  const profileContainer = profileBtn ? profileBtn.parentElement : null;

  if (profileBtn && profileContainer) {
    profileBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      profileContainer.classList.toggle("active");
    });

    // Close dropdown when clicking outside
    document.addEventListener("click", (e) => {
      if (!profileContainer.contains(e.target)) {
        profileContainer.classList.remove("active");
      }
    });
  }

  // Notification Dropdown Toggle
  const notifBtn = document.getElementById("notifDropdownBtn");
  const notifContainer = notifBtn ? notifBtn.parentElement : null;

  if (notifBtn && notifContainer) {
    notifBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      notifContainer.classList.toggle("active");
      // Close profile dropdown if open
      if (profileContainer) profileContainer.classList.remove("active");
    });

    // Close dropdown when clicking outside
    document.addEventListener("click", (e) => {
      if (!notifContainer.contains(e.target)) {
        notifContainer.classList.remove("active");
      }
    });
  }

  // ========== SIDEBAR SUBMENU TOGGLES ==========
  const toggleSubmenu = (toggleId, submenuId) => {
    const toggleBtn = document.getElementById(toggleId);
    const submenu = document.getElementById(submenuId);

    if (toggleBtn && submenu) {
      toggleBtn.addEventListener("click", (e) => {
        e.preventDefault();
        toggleBtn.classList.toggle("open");
        submenu.classList.toggle("active");
      });
      
      // Automatically open if a child link is active
      if (toggleBtn.classList.contains("active")) {
        toggleBtn.classList.add("open");
        submenu.classList.add("active");
      }
    }
  };

  toggleSubmenu("financeDropdownToggle", "financeSubmenu");
  toggleSubmenu("staffDropdownToggle", "staffSubmenu");
  toggleSubmenu("inventoryDropdownToggle", "inventorySubmenu");
  toggleSubmenu("reportsDropdownToggle", "reportsSubmenu");
  toggleSubmenu("oversightDropdownToggle", "oversightSubmenu");
  toggleSubmenu("governanceDropdownToggle", "governanceSubmenu");
  toggleSubmenu("operationsDropdownToggle", "operationsSubmenu");

  // ========== SEARCH FILTERING ==========
  const petSearch = document.getElementById("petSearch");
  const petCardsGrid = document.getElementById("petCardsGrid");

  if (petSearch && petCardsGrid) {
    petSearch.addEventListener("input", function () {
      const query = this.value.toLowerCase().trim();
      const cards = petCardsGrid.querySelectorAll(".pet-card");

      cards.forEach((card) => {
        const name = card.getAttribute("data-name") || "";
        const text = card.textContent.toLowerCase();
        const matches = name.includes(query) || text.includes(query);
        card.style.display = matches ? "" : "none";
      });
    });
  }

  // ========== MODAL TOGGLING ==========
  const editProfileBtn = document.getElementById('editProfileBtn');
  const editProfileModal = document.getElementById('editProfileModal');
  const closeProfileModal = document.getElementById('closeProfileModal');
  const cancelProfileModal = document.getElementById('cancelProfileModal');

  if (editProfileBtn && editProfileModal) {
    const openModal = () => editProfileModal.classList.add('active');
    const closeModal = () => editProfileModal.classList.remove('active');

    editProfileBtn.addEventListener('click', openModal);

    if (closeProfileModal) closeProfileModal.addEventListener('click', closeModal);
    if (cancelProfileModal) cancelProfileModal.addEventListener('click', closeModal);

    // Close when clicking outside of modal content
    editProfileModal.addEventListener('click', (e) => {
      if (e.target === editProfileModal) {
        closeModal();
      }
    });
  }

  // ========== THEME TOGGLING ==========
  const themeToggleBtn = document.getElementById("themeToggleBtn");
  if (themeToggleBtn) {
    const icon = themeToggleBtn.querySelector("i");
    
    // Check saved preference
    const currentTheme = localStorage.getItem("theme");
    if (currentTheme === "dark") {
      document.body.setAttribute("data-theme", "dark");
      if (icon) {
        icon.classList.remove("bx-sun");
        icon.classList.add("bx-moon");
      }
    }

    themeToggleBtn.addEventListener("click", () => {
      let theme = "light";
      if (document.body.getAttribute("data-theme") !== "dark") {
        document.body.setAttribute("data-theme", "dark");
        theme = "dark";
        if (icon) {
          icon.classList.remove("bx-sun");
          icon.classList.add("bx-moon");
        }
      } else {
        document.body.removeAttribute("data-theme");
        if (icon) {
          icon.classList.remove("bx-moon");
          icon.classList.add("bx-sun");
        }
      }
      localStorage.setItem("theme", theme);
    });
  }

});

// ========== TAB SWITCHING LOGIC ==========
function switchTab(tabId) {
  // Hide all tab contents
  const contents = document.querySelectorAll('.tab-content');
  contents.forEach(content => content.classList.remove('active'));

  // Remove active class from all buttons
  const buttons = document.querySelectorAll('.tab-item');
  buttons.forEach(btn => btn.classList.remove('active'));

  // Show the selected tab content
  const selectedTab = document.getElementById(`tab-${tabId}`);
  if (selectedTab) {
    selectedTab.classList.add('active');
  }

  // Highlight the clicked button
  // We find the button by checking its onclick attribute
  const activeBtn = Array.from(buttons).find(btn => btn.getAttribute('onclick') === `switchTab('${tabId}')`);
  if (activeBtn) {
    activeBtn.classList.add('active');
  }
}
