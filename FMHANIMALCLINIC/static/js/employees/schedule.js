/**
 * FMHSYNC Schedule Calendar
 * Vanilla JS — renders monthly calendar, fetches events from API
 * Updated: shift types, recurring schedule modals, color-coding
 */

document.addEventListener("DOMContentLoaded", function () {
function getLocalYMD(d) {
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

  const calGrid = document.getElementById("calGrid");
  const monthLabel = document.getElementById("monthLabel");
  const prevBtn = document.getElementById("prevMonth");
  const nextBtn = document.getElementById("nextMonth");
  const todayBtn = document.getElementById("todayBtn");
  const branchFilterWrap = document.querySelector('[data-sd="branchFilter"]') || document.getElementById('branchFilter');
  function getBranchValue() {
    const hidden = document.querySelector('input[name="branchFilter"]');
    return hidden ? hidden.value : (branchFilterWrap ? branchFilterWrap.value : '');
  }
  const dayDetailPanel = document.getElementById("dayDetailPanel");
  const dayDetailTitle = document.getElementById("dayDetailTitle");
  const dayDetailBody = document.getElementById("dayDetailBody");
  const closeDayDetail = document.getElementById("closeDayDetail");

  // Add Schedule Modal
  const modal = document.getElementById("scheduleModal");
  const addBtn = document.getElementById("addScheduleBtn");
  const closeModal = document.getElementById("closeModal");
  const cancelModal = document.getElementById("cancelModal");

  // Recurring Modal
  const recurringModal = document.getElementById("recurringModal");
  const recurringBtn = document.getElementById("recurringBtn");
  const closeRecurringModal = document.getElementById("closeRecurringModal");
  const cancelRecurringModal = document.getElementById("cancelRecurringModal");

  // Edit Modal
  const editModal = document.getElementById("editScheduleModal");
  const closeEditModal = document.getElementById("closeEditModal");
  const cancelEditModal = document.getElementById("cancelEditModal");
  const editScheduleForm = document.getElementById("editScheduleForm");

  // Edit Fields
  const editStaffName = document.getElementById("editStaffName");
  const editDateLabel = document.getElementById("editDateLabel");
  const editShiftType = document.getElementById("editShiftType");
  const editStartTime = document.getElementById("editStartTime");
  const editEndTime = document.getElementById("editEndTime");
  const editIsAvailable = document.getElementById("editIsAvailable");
  const editNotes = document.getElementById("editNotes");

  // Recurring Toggle
  const isRecurring = document.getElementById("id_is_recurring");
  const singleDateGroup = document.getElementById("singleDateGroup");
  const recurringGroups = document.querySelectorAll(".recurring-group");

  // Clear All Modal
  const clearAllModal = document.getElementById("clearAllModal");
  const clearAllSchedulesBtn = document.getElementById("clearAllSchedulesBtn");
  const closeClearAllModal = document.getElementById("closeClearAllModal");
  const cancelClearAllModal = document.getElementById("cancelClearAllModal");

  // Clear All Recurring Modal
  const clearAllRecurringModal = document.getElementById("clearAllRecurringModal");
  const clearAllTemplatesBtn = document.getElementById("clearAllTemplatesBtn");
  const closeClearAllRecurringModal = document.getElementById("closeClearAllRecurringModal");
  const cancelClearAllRecurringModal = document.getElementById("cancelClearAllRecurringModal");

  const MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
  ];

  // Shift type color mapping
  const SHIFT_COLORS = {
    GENERAL: "#009688",
    SURGERY: "#e63946",
    TELEHEALTH: "#1e88e5",
    BREAK: "#9e9e9e",
    CHECKUP: "#f57c00",
  };

  // Vet color palette for distinguishing multiple vets
  const VET_COLORS = [
    "#009688",
    "#e63946",
    "#1e88e5",
    "#f57c00",
    "#8e24aa",
    "#2e7d32",
    "#d81b60",
    "#5c6bc0",
    "#00897b",
    "#f4511e",
  ];

  function getVetColor(staffId) {
    return VET_COLORS[staffId % VET_COLORS.length];
  }

  const API_STAFF_URL = '/employees/schedule/available-staff/';

  let currentYear = new Date().getFullYear();
  let currentMonth = new Date().getMonth(); // 0-indexed
  let isLoadingCalendar = false; // Prevent concurrent loads
  let events = [];

  // ─── Dependent Branch => Vet Select Logic ───
  function setupDependentVetSelect(modalEl) {
    if (!modalEl) return;
    const branchSelect = modalEl.querySelector('select[name="branch"]');
    const staffSelect = modalEl.querySelector('select[name="staff"]');

    if (!branchSelect || !staffSelect) return;

    const updateStaffDropdown = async () => {
      const branchId = branchSelect.value;

      if (!branchId) {
        staffSelect.innerHTML = '<option value="">Select branch first</option>';
        staffSelect.disabled = true;
        return;
      }

      const currentStaffId = staffSelect.value;
      staffSelect.innerHTML = '<option value="">Loading vets...</option>';
      staffSelect.disabled = true;

      try {
        const res = await fetch(`${API_STAFF_URL}?branch_id=${branchId}`);
        const data = await res.json();

        staffSelect.innerHTML = '<option value="">---------</option>';
        if (data.staff && data.staff.length > 0) {
          data.staff.forEach((s) => {
            const opt = document.createElement("option");
            opt.value = s.id;
            opt.textContent = `${s.name} (${s.position})`;
            if (currentStaffId === String(s.id)) opt.selected = true;
            staffSelect.appendChild(opt);
          });
          staffSelect.disabled = false;
        } else {
          staffSelect.innerHTML = '<option value="">No staff available</option>';
        }
      } catch (err) {
        console.error("Failed to fetch staff:", err);
        staffSelect.innerHTML = '<option value="">Error loading</option>';
      }
    };

    branchSelect.addEventListener("change", updateStaffDropdown);

    // Only fetch automatically if a branch is already pre-selected
    if (branchSelect.value) {
      updateStaffDropdown();
    } else {
      staffSelect.innerHTML = '<option value="">Select branch first</option>';
      staffSelect.disabled = true;
    }
  }

  // Apply to Modals
  setupDependentVetSelect(modal);
  setupDependentVetSelect(recurringModal);

  // ─── Calendar Navigation ───
  prevBtn.addEventListener("click", () => {
    changeMonth(-1);
  });
  nextBtn.addEventListener("click", () => {
    changeMonth(1);
  });
  todayBtn.addEventListener("click", () => {
    currentYear = new Date().getFullYear();
    currentMonth = new Date().getMonth();
    loadCalendar();
  });
  // Listen for searchable-dropdown change event (bubbles up)
  document.addEventListener('sd-change', (e) => {
    if (e.detail && e.detail.name === 'branchFilter') loadCalendar();
  });
  // Fallback for native select change
  if (branchFilterWrap && branchFilterWrap.tagName === 'SELECT') {
    branchFilterWrap.addEventListener('change', () => loadCalendar());
  }

  function changeMonth(delta) {
    currentMonth += delta;
    if (currentMonth < 0) {
      currentMonth = 11;
      currentYear--;
    }
    if (currentMonth > 11) {
      currentMonth = 0;
      currentYear++;
    }
    loadCalendar();
  }

  // ─── Load Calendar ───
  function loadCalendar() {
    if (isLoadingCalendar) {
      return; // Skip if already loading
    }
    
    isLoadingCalendar = true;
    monthLabel.textContent = `${MONTHS[currentMonth]} ${currentYear}`;
    calGrid.innerHTML = '<div style="text-align: center; padding: 40px; color: var(--text-2);"><i class="bx bx-loader-alt bx-spin"></i> Loading...</div>';
    
    fetchEvents()
      .then(() => renderGrid())
      .catch((err) => {
        console.error("Calendar error:", err);
        calGrid.innerHTML = '<div style="text-align: center; padding: 40px; color: #e63946;"><i class="bx bx-error"></i> Error loading schedule</div>';
      })
      .finally(() => {
        isLoadingCalendar = false;
      });
    dayDetailPanel.style.display = "none";
  }

  async function fetchEvents() {
    const branch = getBranchValue();
    const url = `/employees/schedule/api/?year=${currentYear}&month=${currentMonth + 1}&branch=${encodeURIComponent(branch)}`;
    console.log("Fetching from:", url);
    
    try {
      const res = await fetch(url);
      console.log("Response status:", res.status);
      
      if (!res.ok) {
        const errorText = await res.text();
        console.error("Response error:", errorText);
        throw new Error(`API returned ${res.status}: ${res.statusText}`);
      }
      
      const data = await res.json();
      console.log("Response data:", data);
      
      if (!data || !Array.isArray(data.events)) {
        throw new Error("Invalid API response format");
      }
      
      events = data.events;
      console.log(`Loaded ${events.length} schedule events`);
    } catch (error) {
      console.error("Fetch error:", error);
      throw error;
    }
  }

  // ─── Render Grid ───
  function renderGrid() {
    calGrid.innerHTML = "";

    const firstDay = new Date(currentYear, currentMonth, 1).getDay(); // 0=Sun
    const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
    const todayStr = getLocalYMD(new Date());

    // Empty cells before first day
    for (let i = 0; i < firstDay; i++) {
      const empty = document.createElement("div");
      empty.className = "cal-day empty";
      calGrid.appendChild(empty);
    }

    // Day cells
    for (let d = 1; d <= daysInMonth; d++) {
      const dateStr = `${currentYear}-${String(currentMonth + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      const dayEvents = events.filter((e) => e.date === dateStr);

      const cell = document.createElement("div");
      cell.className = "cal-day";
      if (dateStr === todayStr) cell.classList.add("today");
      if (dayEvents.length > 0) cell.classList.add("has-events");

      cell.innerHTML = `
        <span class="cal-day-number">${d}</span>
        ${
          dayEvents.length > 0
            ? `
          <div class="cal-day-events">
            ${dayEvents
              .slice(0, 3)
              .map(
                (e) => `
              <div class="cal-event ${e.isAvailable ? "available" : "unavailable"}" style="border-left: 3px solid ${getVetColor(e.staffId)};">
                <span class="cal-event-name">${e.staffName}</span>
                <span class="cal-shift-badge" style="background: ${SHIFT_COLORS[e.shiftType] || "#009688"}20; color: ${SHIFT_COLORS[e.shiftType] || "#009688"};">${e.shiftTypeDisplay || "General"}</span>
              </div>
            `,
              )
              .join("")}
            ${dayEvents.length > 3 ? `<div class="cal-event more">+${dayEvents.length - 3} more</div>` : ""}
          </div>
        `
            : ""
        }
      `;

      cell.addEventListener("click", () => showDayDetail(dateStr, dayEvents));
      calGrid.appendChild(cell);
    }
  }

  // ─── Day Detail ───
  function showDayDetail(dateStr, dayEvents) {
    const dateObj = new Date(dateStr + "T00:00:00");
    const options = {
      weekday: "long",
      year: "numeric",
      month: "long",
      day: "numeric",
    };
    dayDetailTitle.textContent = dateObj.toLocaleDateString("en-US", options);
    dayDetailPanel.style.display = "block";

    if (dayEvents.length === 0) {
      dayDetailBody.innerHTML = `
        <div class="empty-state" style="padding: 18px 0;">
          <i class='bx bx-calendar-x'></i>
          <h4>No schedules for this day</h4>
          <p>Click "Add Schedule" to assign a vet to this day.</p>
        </div>
      `;
      return;
    }

    let html = '<div class="schedule-entries">';
    dayEvents.forEach((e) => {
      const vetColor = getVetColor(e.staffId);
      const shiftColor = SHIFT_COLORS[e.shiftType] || "#009688";
      html += `
        <div class="schedule-entry ${e.isAvailable ? "" : "unavailable"}" style="border-left: 4px solid ${vetColor};">
          <div class="schedule-entry-left">
            <div class="schedule-entry-avatar" style="background: ${vetColor};">${e.staffName.charAt(0).toUpperCase()}</div>
            <div class="schedule-entry-info">
              <strong>${e.staffName}</strong>
              <span>${e.staffPosition}</span>
            </div>
          </div>
          <div class="schedule-entry-details">
            <div class="schedule-entry-time">
              <i class='bx bx-time-five'></i> ${e.startTime} – ${e.endTime}
            </div>
            <div class="schedule-entry-branch">
              <i class='bx bx-map-pin'></i> ${e.branch}
            </div>
            <span class="shift-badge" style="background: ${shiftColor}20; color: ${shiftColor};">${e.shiftTypeDisplay || "General"}</span>
            <span class="status-badge ${e.isAvailable ? "confirmed" : "pending"}">
              ${e.isAvailable ? "Available" : "Unavailable"}
            </span>
          </div>
          ${e.canEdit ? `
          <div class="schedule-actions" style="display: flex; gap: 8px; margin: 0; align-items: center;">
            <button type="button" class="pet-action-btn outline btn-edit-schedule" title="Edit schedule" data-events='${JSON.stringify(e).replace(/'/g, "&#39;")}'>
              <i class='bx bx-pencil'></i>
            </button>
            <button type="button" class="pet-action-btn danger" title="Delete schedule" onclick="openDeleteModal('/employees/schedule/${e.id}/delete/', '${e.staffName.replace(/'/g, "\\'")}', 'Are you sure you want to delete this schedule entry?')">
              <i class='bx bx-trash-alt'></i>
            </button>
          </div>
          ` : ''}
        </div>
      `;
    });
    html += "</div>";
    dayDetailBody.innerHTML = html;

    // Bind Edit buttons
    const editBtns = dayDetailBody.querySelectorAll(".btn-edit-schedule");
    editBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        const ev = JSON.parse(btn.getAttribute("data-events"));

        editStaffName.textContent = ev.staffName;
        const dObj = new Date(ev.date + "T00:00:00");
        editDateLabel.textContent = dObj.toLocaleDateString("en-US", {
          weekday: "long",
          year: "numeric",
          month: "long",
          day: "numeric",
        });

        editShiftType.value = ev.shiftType;
        editStartTime.value = ev.startTime;
        editEndTime.value = ev.endTime;
        editIsAvailable.checked = ev.isAvailable;
        editNotes.value = ev.notes || "";

        editScheduleForm.action = `/employees/schedule/${ev.id}/edit/`;
        openModal(editModal);
      });
    });

    dayDetailPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  closeDayDetail.addEventListener("click", () => {
    dayDetailPanel.style.display = "none";
  });

  // ─── Generic Modal Helper ───
  function openModal(el) {
    el.classList.add("active");
  }
  function closeModalEl(el) {
    el.classList.remove("active");
  }

  function showScheduleToast(message, type = 'success') {
    let container = document.getElementById('portalMessages');
    if (!container) {
      container = document.createElement('div');
      container.className = 'portal-messages';
      container.id = 'portalMessages';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `portal-message ${type}`;
    const icon = type === 'success' ? 'bx-check-circle' : (type === 'warning' ? 'bx-error-alt' : 'bx-error-circle');
    const title = type === 'success' ? 'Success' : (type === 'warning' ? 'Warning' : 'Error');
    toast.innerHTML = `
      <i class="bx ${icon}"></i>
      <div>
        <strong>${title}</strong>
        <span>${message}</span>
      </div>
      <button class="portal-message-close" onclick="this.parentElement.remove()"><i class="bx bx-x"></i></button>
    `;
    container.appendChild(toast);
  }

  window.openDeleteModal = function(url, name, note) {
    const modal = document.getElementById('deleteScheduleModal');
    const form = document.getElementById('deleteScheduleForm');
    const nameEl = document.getElementById('deleteScheduleName');
    const noteEl = document.getElementById('deleteScheduleNote');
    if (!modal || !form || !nameEl || !noteEl) return;
    form.action = url;
    modal.dataset.ajaxDelete = url.includes('/recurring/') ? '1' : '0';
    const match = url.match(/\/recurring\/(\d+)\/delete\//);
    modal.dataset.recurringId = match ? match[1] : '';
    nameEl.textContent = name;
    noteEl.textContent = note || 'This action cannot be undone.';
    modal.classList.add('active');
  };

  window.closeDeleteModal = function() {
    const modal = document.getElementById('deleteScheduleModal');
    if (modal) modal.classList.remove('active');
  };

  const closeDeleteScheduleModalBtn = document.getElementById('closeDeleteScheduleModal');
  const cancelDeleteScheduleModalBtn = document.getElementById('cancelDeleteScheduleModal');
  const deleteScheduleForm = document.getElementById('deleteScheduleForm');
  if (closeDeleteScheduleModalBtn) {
    closeDeleteScheduleModalBtn.addEventListener('click', closeDeleteModal);
  }
  if (cancelDeleteScheduleModalBtn) {
    cancelDeleteScheduleModalBtn.addEventListener('click', closeDeleteModal);
  }

  const deleteScheduleModal = document.getElementById('deleteScheduleModal');
  if (deleteScheduleModal) {
    deleteScheduleModal.addEventListener('click', (event) => {
      if (event.target === deleteScheduleModal) {
        closeDeleteModal();
      }
    });
  }

  if (deleteScheduleForm) {
    deleteScheduleForm.addEventListener('submit', async (event) => {
      if (deleteScheduleModal && deleteScheduleModal.dataset.ajaxDelete !== '1') {
        return;
      }

      event.preventDefault();
      const form = event.currentTarget;
      const formData = new FormData(form);
      const submitBtn = form.querySelector('button[type="submit"]');
      const originalHtml = submitBtn ? submitBtn.innerHTML : '';

      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="bx bx-loader-alt bx-spin"></i> Deleting...';
      }

      try {
        const response = await fetch(form.action, {
          method: 'POST',
          body: formData,
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
          },
        });

        const data = await response.json();
        if (!response.ok || !data.success) {
          throw new Error(data.message || 'Delete failed');
        }

        const recurringId = deleteScheduleModal.dataset.recurringId;
        if (recurringId) {
          const row = document.querySelector(`.schedule-entry[data-recurring-id="${recurringId}"]`);
          if (row) {
            row.remove();
          }
        }

        showScheduleToast(data.message || 'Recurring template removed.', 'success');
        closeDeleteModal();
      } catch (error) {
        console.error('Recurring delete failed:', error);
        showScheduleToast(error.message || 'Could not delete recurring template.', 'error');
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = originalHtml;
        }
      }
    });
  }

  // Add Schedule Modal
  if (addBtn) {
    addBtn.addEventListener("click", () => openModal(modal));
  }
  if (closeModal) {
    closeModal.addEventListener("click", () => closeModalEl(modal));
  }
  if (cancelModal) {
    cancelModal.addEventListener("click", () => closeModalEl(modal));
  }
  if (modal) {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) closeModalEl(modal);
    });
  }

  // Recurring Modal
  if (recurringBtn) {
    recurringBtn.addEventListener("click", () => openModal(recurringModal));
    if (closeRecurringModal) {
      closeRecurringModal.addEventListener("click", () =>
        closeModalEl(recurringModal),
      );
    }
    if (cancelRecurringModal) {
      cancelRecurringModal.addEventListener("click", () =>
        closeModalEl(recurringModal),
      );
    }
    if (recurringModal) {
      recurringModal.addEventListener("click", (e) => {
        if (e.target === recurringModal) closeModalEl(recurringModal);
      });
    }
  }

  // Recurring Toggle Logic
  if (isRecurring) {
    isRecurring.addEventListener("change", (e) => {
      if (e.target.checked) {
        if (singleDateGroup) singleDateGroup.style.display = "none";
        recurringGroups.forEach((el) => (el.style.display = "block"));
      } else {
        if (singleDateGroup) singleDateGroup.style.display = "block";
        recurringGroups.forEach((el) => (el.style.display = "none"));
      }
    });
  }

  // Edit Modal
  if (editModal) {
    closeEditModal.addEventListener("click", () => closeModalEl(editModal));
    cancelEditModal.addEventListener("click", () => closeModalEl(editModal));
    editModal.addEventListener("click", (e) => {
      if (e.target === editModal) closeModalEl(editModal);
    });
  }

  // Clear All Modal
  if (clearAllSchedulesBtn) {
    clearAllSchedulesBtn.addEventListener("click", () => openModal(clearAllModal));
    closeClearAllModal.addEventListener("click", () =>
      closeModalEl(clearAllModal),
    );
    cancelClearAllModal.addEventListener("click", () =>
      closeModalEl(clearAllModal),
    );
    clearAllModal.addEventListener("click", (e) => {
      if (e.target === clearAllModal) closeModalEl(clearAllModal);
    });
  }

  // Clear All Recurring Modal
  if (clearAllTemplatesBtn) {
    clearAllTemplatesBtn.addEventListener("click", () => openModal(clearAllRecurringModal));
    closeClearAllRecurringModal.addEventListener("click", () =>
      closeModalEl(clearAllRecurringModal),
    );
    cancelClearAllRecurringModal.addEventListener("click", () =>
      closeModalEl(clearAllRecurringModal),
    );
    clearAllRecurringModal.addEventListener("click", (e) => {
      if (e.target === clearAllRecurringModal) closeModalEl(clearAllRecurringModal);
    });
  }

  // ─── Helpers ───
  function getCSRF() {
    const cookie = document.cookie
      .split(";")
      .find((c) => c.trim().startsWith("csrftoken="));
    return cookie ? cookie.split("=")[1] : "";
  }

  // ─── Init ───
  // Small delay to ensure DOM is fully ready
  setTimeout(() => {
    if (calGrid && monthLabel) {
      loadCalendar();
    } else {
      console.error("Calendar elements not found");
    }
  }, 100);

  // Expose loadCalendar globally for debugging
  window.loadCalendar = loadCalendar;
});
