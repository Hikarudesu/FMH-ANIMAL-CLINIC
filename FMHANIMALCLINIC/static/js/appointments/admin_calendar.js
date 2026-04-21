/**
 * admin_calendar.js — Admin appointment calendar view
 * Renders Daily/Weekly/Monthly views with color-coding
 */

document.addEventListener("DOMContentLoaded", function () {
  const tableView = document.getElementById("tableView");
  const calendarView = document.getElementById("calendarView");
  const calContent = document.getElementById("calendarContent");
  const calLabel = document.getElementById("calLabel");
  const calPrev = document.getElementById("calPrev");
  const calNext = document.getElementById("calNext");
  const calToday = document.getElementById("calToday");
  const quickCreateModal = document.getElementById("quickCreateModal");
  const quickCreateBtn = document.getElementById("quickCreateBtn");
  const closeQuickCreate = document.getElementById("closeQuickCreate");
  const cancelQuickCreate = document.getElementById("cancelQuickCreate");

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
  const DAYS = [
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
  ];
  const DAYS_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  const STATUS_COLORS = {
    PENDING: "#f57c00",
    CONFIRMED: "#009688",
    CANCELLED: "#9e9e9e",
    COMPLETED: "#2e7d32",
  };

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

  function getVetColor(vetId) {
    if (!vetId) return "#9e9e9e";
    return VET_COLORS[vetId % VET_COLORS.length];
  }

  let currentView = "table";
  let currentDate = new Date();
  let events = [];

  // Get view from URL parameter (persisted across filter submissions)
  const urlParams = new URLSearchParams(window.location.search);
  const viewParam = urlParams.get('view') || 'table';
  currentView = viewParam;

  // ─── Show correct view on page load ───
  // Tabs navigate directly (onclick → window.location.href) so no click
  // listener is needed here.  We just read ?view= and show the right panel.
  if (currentView === "table") {
    if (tableView) tableView.style.display = "";
    if (calendarView) calendarView.style.display = "none";
  } else {
    if (tableView) tableView.style.display = "none";
    if (calendarView) calendarView.style.display = "";
    loadCalendarView();
  }

  // ─── Calendar Navigation ───
  if (calPrev) calPrev.addEventListener("click", () => navigateCal(-1));
  if (calNext) calNext.addEventListener("click", () => navigateCal(1));
  if (calToday)
    calToday.addEventListener("click", () => {
      currentDate = new Date();
      loadCalendarView();
    });

  function navigateCal(delta) {
    if (currentView === "daily") {
      currentDate.setDate(currentDate.getDate() + delta);
    } else if (currentView === "weekly") {
      currentDate.setDate(currentDate.getDate() + delta * 7);
    } else if (currentView === "monthly") {
      currentDate.setMonth(currentDate.getMonth() + delta);
    }
    loadCalendarView();
  }

  // ─── Load Calendar ───
  async function loadCalendarView() {
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth() + 1;

    // Get filter values from the main form
    const branchFilter = document.querySelector('[name="branch"]');
    const vetFilter = document.querySelector('[name="vet"]');
    const statusFilter = document.querySelector('[name="status"]');

    let url = `${CALENDAR_API}?year=${year}&month=${month}`;
    if (branchFilter && branchFilter.value)
      url += `&branch=${branchFilter.value}`;
    if (vetFilter && vetFilter.value) url += `&vet=${vetFilter.value}`;
    if (statusFilter && statusFilter.value)
      url += `&status=${statusFilter.value}`;

    try {
      const res = await fetch(url);
      const data = await res.json();
      events = data.events || [];
    } catch (e) {
      events = [];
    }

    if (currentView === "daily") renderDailyView();
    else if (currentView === "weekly") renderWeeklyView();
    else if (currentView === "monthly") renderMonthlyView();
  }

  // ─── Daily View ───
  function renderDailyView() {
    const dateStr = currentDate.toISOString().split("T")[0];
    const dayName = DAYS[currentDate.getDay()];
    calLabel.textContent = `${dayName}, ${MONTHS[currentDate.getMonth()]} ${currentDate.getDate()}, ${currentDate.getFullYear()}`;

    const dayEvents = events
      .filter((e) => e.date === dateStr)
      .sort((a, b) => a.time.localeCompare(b.time));

    if (dayEvents.length === 0) {
      calContent.innerHTML = `
        <div class="empty-state" style="padding: 30px 0;">
          <i class='bx bx-calendar-x' style="font-size: 2.5rem;"></i>
          <h4>No appointments for this day</h4>
          <p>Use "Quick Create" to add an appointment.</p>
        </div>
      `;
      return;
    }

    let html = '<div class="schedule-entries">';
    dayEvents.forEach((e) => {
      const vetCol = getVetColor(e.vetId);
      const statusCol = STATUS_COLORS[e.status] || "#9e9e9e";
      html += `
        <div onclick="openAppointmentDetail(${e.id})" class="schedule-entry" style="cursor: pointer; text-decoration: none; color: inherit;">
          <div class="schedule-entry-left">
            <div class="schedule-entry-avatar" style="background: var(--primary); overflow: hidden;">
              ${e.ownerProfilePicture ? `<img src="${e.ownerProfilePicture}" style="width: 100%; height: 100%; object-fit: cover;" alt="Profile">` : `${e.ownerName.charAt(0).toUpperCase()}`}
            </div>
            <div class="schedule-entry-info">
              <strong>${e.ownerName}</strong>
              <span>${e.petName}${e.petBreed ? " (" + e.petBreed + ")" : ""}</span>
            </div>
          </div>
          <div class="schedule-entry-details">
            <div class="schedule-entry-time">
              <i class='bx bx-time-five'></i> ${e.timeLabel}
            </div>
            <div class="schedule-entry-branch" style="display: flex; gap: 10px;">
              <span><i class='bx bx-user'></i> ${e.vetName}</span>
              ${e.branch ? `<span><i class='bx bx-building'></i> ${e.branch}</span>` : ''}
            </div>
            <div style="display: flex; gap: 6px; align-items: center; flex-wrap: wrap;">
              <span class="status-badge ${e.status.toLowerCase()}">${e.statusDisplay}</span>
              <span class="source-badge source-${e.source.toLowerCase()}">${e.source === 'PORTAL' ? '🌐 Portal' : '🚶 Walk-in'}</span>
            </div>
          </div>
        </div>
      `;
    });
    html += "</div>";
    calContent.innerHTML = html;
  }

  // ─── Weekly View ───
  function renderWeeklyView() {
    const weekStart = new Date(currentDate);
    weekStart.setDate(weekStart.getDate() - weekStart.getDay());
    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekEnd.getDate() + 6);

    calLabel.textContent = `${MONTHS[weekStart.getMonth()]} ${weekStart.getDate()} – ${MONTHS[weekEnd.getMonth()]} ${weekEnd.getDate()}, ${weekEnd.getFullYear()}`;

    let html = '<div class="weekly-grid">';
    for (let i = 0; i < 7; i++) {
      const day = new Date(weekStart);
      day.setDate(day.getDate() + i);
      const dateStr = day.toISOString().split("T")[0];
      const todayStr = new Date().toISOString().split("T")[0];
      const dayEvents = events
        .filter((e) => e.date === dateStr)
        .sort((a, b) => a.time.localeCompare(b.time));
      const isToday = dateStr === todayStr;

      html += `
        <div class="weekly-day ${isToday ? "today" : ""}" data-date="${dateStr}" style="cursor: pointer;">
          <div class="weekly-day-header">
            <span class="weekly-day-name">${DAYS_SHORT[i]}</span>
            <span class="weekly-day-num ${isToday ? "today-num" : ""}">${day.getDate()}</span>
          </div>
          <div class="weekly-day-events">
      `;
      const weeklyVisible = dayEvents.slice(0, 3);
      weeklyVisible.forEach((e) => {
        const vetCol = getVetColor(e.vetId);
        html += `
          <div class="weekly-event" onclick="openAppointmentDetail(${e.id})" style="cursor: pointer; display: flex; align-items: center; justify-content: space-between; padding: 6px 8px;">
            <div style="display: flex; flex-direction: column; overflow: hidden; white-space: nowrap; text-overflow: ellipsis;">
              <span class="weekly-event-time" style="font-size: 0.75rem; color: var(--text-2); margin-bottom: 2px;">${e.timeLabel}</span>
              <strong style="font-size: 0.85rem; color: var(--text-1); overflow: hidden; text-overflow: ellipsis;">${e.ownerName}</strong>
              ${e.branch ? `<span style="font-size: 0.68rem; color: var(--text-3); margin-top: 1px; overflow: hidden; text-overflow: ellipsis;"><i class='bx bx-building' style="vertical-align: middle;"></i> ${e.branch}</span>` : ''}
              <span class="source-badge source-${e.source.toLowerCase()}" style="font-size: 0.62rem; padding: 1px 5px; margin-top: 2px; white-space: nowrap;">${e.source === 'PORTAL' ? '🌐 Portal' : '🚶 Walk-in'}</span>
            </div>
            <span class="status-dot" style="background: ${STATUS_COLORS[e.status] || "#9e9e9e"}; width: 8px; height: 8px; flex-shrink: 0; margin-top: 2px; align-self: flex-start;"></span>
          </div>
        `;
      });
      if (dayEvents.length > 0) {
        html += `<div onclick="event.stopPropagation(); openMoreDetails('${dateStr}')" style="margin: 4px 4px 0; padding: 4px 6px; font-size: 0.72rem; text-align: center; background: var(--primary); color: #fff; border-radius: 4px; cursor: pointer; font-weight: 600;"><i class='bx bx-list-ul'></i> View All (${dayEvents.length})</div>`;
      }
      if (dayEvents.length === 0) {
        html += `<div class="weekly-empty">No appts</div>`;
      }
      html += `
          </div>
        </div>
      `;
    }
    html += "</div>";
    calContent.innerHTML = html;

    // Attach listener for clicking any weekly day column
    const weeklyDays = calContent.querySelectorAll(".weekly-day");
    weeklyDays.forEach((dayEl) => {
      dayEl.addEventListener("click", function (e) {
        // Prevent overriding if an explicit 'weekly-event' inside is clicked
        if (e.target.closest(".weekly-event")) return;

        calContent.querySelectorAll(".weekly-day").forEach((d) => {
          d.classList.remove("selected-day");
          d.style.background = "";
        });

        this.classList.add("selected-day");
        this.style.background = "var(--bg-hover)";

        const clickedDate = this.getAttribute("data-date");
        if (clickedDate) {
          window.openMoreDetails(clickedDate);
        }
      });
    });
  }

  // ─── Monthly View ───
  function renderMonthlyView() {
    const detailsContainer = document.getElementById(
      "calendarDetailsContainer",
    );
    if (detailsContainer) detailsContainer.style.display = "none";

    calLabel.textContent = `${MONTHS[currentDate.getMonth()]} ${currentDate.getFullYear()}`;

    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();
    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const todayStr = new Date().toISOString().split("T")[0];

    let html = '<div class="cal-weekdays">';
    DAYS_SHORT.forEach((d) => {
      html += `<div>${d}</div>`;
    });
    html += '</div><div class="cal-grid">';

    for (let i = 0; i < firstDay; i++) {
      html += '<div class="cal-day empty"></div>';
    }

    for (let d = 1; d <= daysInMonth; d++) {
      const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      const dayEvents = events.filter((e) => e.date === dateStr);
      const isToday = dateStr === todayStr;

      html += `
        <div class="cal-day ${isToday ? "today" : ""} ${dayEvents.length > 0 ? "has-events" : ""}" data-date="${dateStr}">
          <span class="cal-day-number">${d}</span>
          ${
            dayEvents.length > 0
              ? `
            <div class="cal-day-events">
              ${dayEvents
                .slice(0, 2)
                .map(
                  (e) => `
                <div class="weekly-event" onclick="openAppointmentDetail(${e.id})" style="cursor: pointer; display: flex; align-items: center; justify-content: space-between; padding: 5px 7px; margin-bottom: 3px; border-radius: 4px;">
                  <div style="display: flex; flex-direction: column; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; min-width: 0;">
                    <span style="font-size: 0.72rem; color: var(--text-2); margin-bottom: 1px;">${e.timeLabel}</span>
                    <strong style="font-size: 0.80rem; color: var(--text-1); overflow: hidden; text-overflow: ellipsis;">${e.ownerName}</strong>
                    ${e.branch ? `<span style="font-size: 0.65rem; color: var(--text-3); margin-top: 1px; overflow: hidden; text-overflow: ellipsis;"><i class='bx bx-building' style="vertical-align: middle;"></i> ${e.branch}</span>` : ''}
                    <span class="source-badge source-${e.source.toLowerCase()}" style="font-size: 0.58rem; padding: 1px 4px; margin-top: 2px; white-space: nowrap;">${e.source === 'PORTAL' ? '🌐 Portal' : '🚶 Walk-in'}</span>
                  </div>
                  <span style="background: ${STATUS_COLORS[e.status] || '#9e9e9e'}; width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; margin-top: 2px; align-self: flex-start;"></span>
                </div>
              `,
                )
                .join("")}
              ${dayEvents.length > 0 ? `<div class="cal-event more" onclick="event.stopPropagation(); openMoreDetails('${dateStr}')" style="cursor: pointer; font-size: 0.70rem; text-align: center; color: #fff; background: var(--primary); border-radius: 4px; padding: 2px 4px; margin-top: 2px; font-weight: 600;"><i class='bx bx-list-ul'></i> View All (${dayEvents.length})</div>` : ""}
            </div>
          `
              : ""
          }
        </div>
      `;
    }

    html += "</div>";
    calContent.innerHTML = html;

    // Attach listener for clicking any day
    const calDays = calContent.querySelectorAll(".cal-day:not(.empty)");
    calDays.forEach((dayEl) => {
      dayEl.addEventListener("click", function(e) {
        // Prevent overriding if an explicit 'cal-event' block inside is clicked
        if (e.target.closest('.cal-event:not(.more)')) return;
        
        const clickedDate = this.getAttribute("data-date");
        if (clickedDate) {
          window.openMoreDetails(clickedDate);
        }
      });
    });
  }

  // ─── Render See More Details (Monthly 'more' click) ───
  // Pagination state for calendar details
  let calendarDetailPage = 1;
  const ITEMS_PER_PAGE = 10;

  window.openMoreDetails = function (dateStr, page = 1) {
    calendarDetailPage = page;
    const detailsContainer = document.getElementById(
      "calendarDetailsContainer",
    );
    if (!detailsContainer) return;

    calContent.querySelectorAll(".cal-day").forEach((d) => {
      d.classList.remove("selected-day");
      d.style.border = "";
      if (d.getAttribute("data-date") === dateStr) {
        d.classList.add("selected-day");
        d.style.border = "2px solid var(--primary)";
      }
    });

    const dayEvents = events
      .filter((e) => e.date === dateStr)
      .sort((a, b) => a.time.localeCompare(b.time));

    // Pagination calculations
    const totalItems = dayEvents.length;
    const totalPages = Math.ceil(totalItems / ITEMS_PER_PAGE);
    const startIdx = (page - 1) * ITEMS_PER_PAGE;
    const endIdx = Math.min(startIdx + ITEMS_PER_PAGE, totalItems);
    const paginatedEvents = dayEvents.slice(startIdx, endIdx);

    // Convert YYYY-MM-DD to friendly format
    const [year, month, dayObj] = dateStr.split("-");
    const dateObj = new Date(year, month - 1, dayObj);
    const formattedDate = `${DAYS[dateObj.getDay()]}, ${MONTHS[dateObj.getMonth()]} ${dateObj.getDate()}, ${dateObj.getFullYear()}`;

    let html = `
      <div style="padding: 16px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center;">
        <h3 style="margin: 0; font-size: 1.1rem; color: var(--text-1);"><i class='bx bx-calendar-star' style="color: var(--primary);"></i> Appointments for ${formattedDate}</h3>
        <button class="btn-action outline" onclick="document.getElementById('calendarDetailsContainer').style.display='none'; document.querySelectorAll('.cal-day').forEach(d => { d.classList.remove('selected-day'); d.style.border=''; });" style="padding: 4px 10px; font-size: 0.8rem;"><i class='bx bx-x'></i> Close</button>
      </div>
      <div style="padding: 16px;">
        <div style="display: flex; flex-direction: column; gap: 12px;">
    `;

    paginatedEvents.forEach((e) => {
      const vetCol = getVetColor(e.vetId);
      html += `
        <div style="display: flex; align-items: center; border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; background: var(--surface); color: var(--text-1); box-shadow: 0 1px 3px rgba(0,0,0,0.05); cursor: pointer; transition: transform 0.2s, box-shadow 0.2s;" onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 4px 8px rgba(0,0,0,0.1)';" onmouseout="this.style.transform='none'; this.style.boxShadow='0 1px 3px rgba(0,0,0,0.05)';" onclick="openAppointmentDetail(${e.id})">

          <div style="display: flex; align-items: center; flex: 1;">
            <div style="width: 40px; height: 40px; border-radius: 8px; background: var(--primary); color: white; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 1.2rem; margin-right: 16px; overflow: hidden;">
              ${e.ownerProfilePicture ? `<img src="${e.ownerProfilePicture}" style="width: 100%; height: 100%; object-fit: cover;" alt="Profile">` : `${e.ownerName.charAt(0).toUpperCase()}`}
            </div>
            <div>
              <div style="font-weight: 600; color: var(--text-1); font-size: 0.95rem;">${e.ownerName}</div>
              <div style="color: var(--text-2); font-size: 0.8rem;">${e.petName} ${e.petBreed ? '('+e.petBreed+')' : ''}</div>
            </div>
          </div>

          <div style="display: flex; align-items: center; gap: 16px; font-size: 0.85rem; color: var(--text-2); flex-wrap: wrap;">
            <div style="display: flex; align-items: center; gap: 4px;"><i class='bx bx-time-five' style="color: var(--primary);"></i> ${e.timeLabel}</div>
            <div style="display: flex; align-items: center; gap: 4px;"><i class='bx bx-building' style="color: var(--primary);"></i> ${e.branch || "Standard"}</div>
            <span class="source-badge source-${e.source.toLowerCase()}">${e.source === 'PORTAL' ? '🌐 Portal' : '🚶 Walk-in'}</span>
            <span class="status-badge ${e.status.toLowerCase()}">${e.statusDisplay}</span>
          </div>

        </div>
      `;
    });

    html += `
        </div>
      </div>
    `;

    // Add pagination controls if more than one page
    if (totalPages > 1) {
      html += `
        <div class="calendar-pagination">
          <div class="pagination-info">
            <span class="pagination-text">Showing <strong>${startIdx + 1}</strong> to <strong>${endIdx}</strong> of <strong>${totalItems}</strong> appointments</span>
          </div>
          <div class="pagination-controls">
            ${page > 1 ? `
              <button class="pagination-btn" onclick="openMoreDetails('${dateStr}', 1)" title="First Page"><i class='bx bx-chevrons-left'></i></button>
              <button class="pagination-btn" onclick="openMoreDetails('${dateStr}', ${page - 1})" title="Previous"><i class='bx bx-chevron-left'></i></button>
            ` : `
              <span class="pagination-btn pagination-btn-disabled"><i class='bx bx-chevrons-left'></i></span>
              <span class="pagination-btn pagination-btn-disabled"><i class='bx bx-chevron-left'></i></span>
            `}
            <div class="pagination-pages">
      `;

      // Page numbers (show current page and 2 pages around it)
      for (let i = 1; i <= totalPages; i++) {
        if (i === page) {
          html += `<span class="pagination-page active">${i}</span>`;
        } else if (i > page - 3 && i < page + 3) {
          html += `<button class="pagination-page" onclick="openMoreDetails('${dateStr}', ${i})">${i}</button>`;
        }
      }

      html += `
            </div>
            ${page < totalPages ? `
              <button class="pagination-btn" onclick="openMoreDetails('${dateStr}', ${page + 1})" title="Next"><i class='bx bx-chevron-right'></i></button>
              <button class="pagination-btn" onclick="openMoreDetails('${dateStr}', ${totalPages})" title="Last Page"><i class='bx bx-chevrons-right'></i></button>
            ` : `
              <span class="pagination-btn pagination-btn-disabled"><i class='bx bx-chevron-right'></i></span>
              <span class="pagination-btn pagination-btn-disabled"><i class='bx bx-chevrons-right'></i></span>
            `}
          </div>
        </div>
      `;
    }

    detailsContainer.innerHTML = html;
    detailsContainer.style.display = "block";
    detailsContainer.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  // ─── Modal Detail Logic ───
  window.openAppointmentDetail = function (apptId) {
    const eventData = events.find((e) => e.id === apptId);
    if (!eventData) return;

    const modal = document.getElementById("appointmentDetailModal");
    if (!modal) return;

    // Set styling colors based on vet
    const vetCol = getVetColor(eventData.vetId);

    // Owner avatar — show profile picture or first letter of owner name
    const ownerAv = document.getElementById("detailOwnerAvatar");
    if (ownerAv) {
      if (eventData.ownerProfilePicture) {
        ownerAv.innerHTML = `<img src="${eventData.ownerProfilePicture}" alt="${eventData.ownerName}" style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%;">`;
      } else {
        ownerAv.innerHTML = '';
        ownerAv.textContent = (eventData.ownerName || "?").charAt(0).toUpperCase();
      }
    }

    // Setup Top Text - Pet Name with Clinical Status
    document.getElementById("detailOwnerName").textContent = eventData.ownerName;
    document.getElementById("detailPetNameText").textContent = `${eventData.petName} (${eventData.petBreed || eventData.petSpecies})`;

    // Show pet clinical status if available
    const petClinicicalBadge = document.getElementById("detailPetClinicalStatus");
    if (eventData.petClinicalStatus && eventData.petClinicalDisplay) {
      petClinicicalBadge.textContent = eventData.petClinicalDisplay;
      petClinicicalBadge.className = `dm-clinical-badge ${eventData.petClinicalStatus.toLowerCase()}`;
      petClinicicalBadge.style.display = "inline-flex";
    } else {
      petClinicicalBadge.style.display = "none";
    }

    // Show clinical alert if pet is not healthy
    const clinicalAlert = document.getElementById("detailClinicalAlert");
    const alertText = document.getElementById("detailClinicalAlertText");
    if (eventData.petClinicalStatus && eventData.petClinicalStatus !== 'HEALTHY') {
      clinicalAlert.style.display = "flex";
      let alertIcon = 'bx-info-circle';
      let alertColor = '#ff9800';

      if (eventData.petClinicalStatus === 'CRITICAL') {
        alertIcon = 'bx-error';
        alertColor = '#d32f2f';
        clinicalAlert.style.borderLeftColor = alertColor;
        clinicalAlert.style.color = alertColor;
        clinicalAlert.style.background = '#ffebee';
      } else if (eventData.petClinicalStatus === 'SURGERY') {
        alertIcon = 'bx-plus-medical';
        alertColor = '#c62828';
        clinicalAlert.style.borderLeftColor = alertColor;
        clinicalAlert.style.color = alertColor;
        clinicalAlert.style.background = '#fce4ec';
      } else if (eventData.petClinicalStatus === 'TREATMENT') {
        alertIcon = 'bx-pulse';
        alertColor = '#1565c0';
        clinicalAlert.style.borderLeftColor = alertColor;
        clinicalAlert.style.color = alertColor;
        clinicalAlert.style.background = '#e3f2fd';
      } else if (eventData.petClinicalStatus === 'MONITOR') {
        alertIcon = 'bx-show';
        alertColor = '#e65100';
        clinicalAlert.style.borderLeftColor = alertColor;
        clinicalAlert.style.color = alertColor;
        clinicalAlert.style.background = '#fff3e0';
      } else if (eventData.petClinicalStatus === 'DIAGNOSTICS') {
        alertIcon = 'bx-test-tube';
        alertColor = '#6a1b9a';
        clinicalAlert.style.borderLeftColor = alertColor;
        clinicalAlert.style.color = alertColor;
        clinicalAlert.style.background = '#f3e5f5';
      }

      clinicalAlert.querySelector('i').className = `bx ${alertIcon}`;
      alertText.textContent = `⚠ Clinical Status: ${eventData.petClinicalDisplay}`;
    } else {
      clinicalAlert.style.display = "none";
    }

    // Status Badge (Appointment Status)
    const statusB = document.getElementById("detailStatusBadge");
    statusB.className = `dm-status dm-status--${eventData.status.toLowerCase()}`;
    statusB.textContent = eventData.statusDisplay;

    // Timings
    document.getElementById("detailTime").textContent = eventData.timeLabel;
    const dObj = new Date(eventData.date);
    document.getElementById("detailDate").textContent =
      `${MONTHS[dObj.getMonth()]} ${dObj.getDate()}, ${dObj.getFullYear()}`;

    // Vet
    document.getElementById("detailVetName").textContent =
      eventData.vetName || "Any Available Vet";

    // Branch in top bar
    document.getElementById("detailBranchBar").textContent = eventData.branch || "—";

    // Info Grid Details
    document.getElementById("detailReason").textContent = eventData.reason || "—";
    document.getElementById("detailSourceBadge").className =
      `dm-source dm-source--${eventData.source.toLowerCase()}`;
    document.getElementById("detailSourceBadge").textContent =
      eventData.source === "PORTAL" ? "🌐 Portal" : "🚶 Walk-in";
    document.getElementById("detailSourceDisplay").textContent =
      eventData.source === "PORTAL" ? "Portal (Registered User)" : "Walk-in (Guest)";

    // Owner details
    document.getElementById("detailOwnerNameDetail").textContent = eventData.ownerName || "—";
    document.getElementById("detailPhone").textContent = eventData.ownerPhone || "—";
    document.getElementById("detailEmail").textContent = eventData.ownerEmail || "—";
    document.getElementById("detailCreatedAt").textContent = eventData.createdAt || "—";

    // Medical Records Link (if pet is linked and has records)
    const medicalRecordsLink = document.getElementById("detailMedicalRecordsLink");
    if (eventData.latestRecordId && eventData.hasMedicalRecords) {
      document.getElementById("detailMedicalRecordsBtn").href = `/records/admin/${eventData.latestRecordId}/`;
      medicalRecordsLink.style.display = "block";
    } else {
      medicalRecordsLink.style.display = "none";
    }

    // Pet Details
    document.getElementById("detailPetName").textContent = eventData.petName || "—";
    document.getElementById("detailSpecies").textContent = eventData.petSpecies || "—";
    document.getElementById("detailBreed").textContent = eventData.petBreed || "—";
    document.getElementById("detailDOB").textContent = eventData.petDOB ? new Date(eventData.petDOB).toLocaleDateString() : "—";
    document.getElementById("detailSex").textContent = eventData.petSex || "—";
    document.getElementById("detailColor").textContent = eventData.petColor || "—";

    // Notes
    const notesContainer = document.getElementById("detailNotesContainer");
    if (eventData.notes) {
      document.getElementById("detailNotes").textContent = eventData.notes;
      notesContainer.style.display = "block";
    } else {
      notesContainer.style.display = "none";
    }

    // Set Edit Link Path (if button exists / user has edit permissions)
    const detailEditBtn = document.getElementById("detailEditBtn");
    if (detailEditBtn) {
      detailEditBtn.href = `/appointments/admin/${eventData.id}/edit/`;
    }

    // Open Modal
    modal.classList.add("active");
  };

  // Modal Close Logic
  const closeDetailBtn = document.getElementById("closeDetailModal");
  if (closeDetailBtn) {
    closeDetailBtn.addEventListener("click", () => {
      document
        .getElementById("appointmentDetailModal")
        .classList.remove("active");
    });
  }
  const apptModalOverlay = document.getElementById("appointmentDetailModal");
  if (apptModalOverlay) {
    apptModalOverlay.addEventListener("click", (e) => {
      if (e.target === apptModalOverlay) {
        apptModalOverlay.classList.remove("active");
      }
    });
  }

  // ─── Quick Create Modal ───
  function openModal(el) {
    el.classList.add("active");
  }
  function closeModal(el) {
    el.classList.remove("active");
  }

  if (quickCreateBtn)
    quickCreateBtn.addEventListener("click", () => openModal(quickCreateModal));
  if (closeQuickCreate)
    closeQuickCreate.addEventListener("click", () =>
      closeModal(quickCreateModal),
    );
  if (cancelQuickCreate)
    cancelQuickCreate.addEventListener("click", () =>
      closeModal(quickCreateModal),
    );
  if (quickCreateModal)
    quickCreateModal.addEventListener("click", (e) => {
      if (e.target === quickCreateModal) closeModal(quickCreateModal);
    });

  // ─── Follow-up Toggle for Quick Create ───
  const quickFollowUpEnabled = document.getElementById("quickFollowUpEnabled");
  const quickFollowUpFields = document.getElementById("quickFollowUpFields");
  const quickFollowUpDate = document.getElementById("quickFollowUpDate");

  if (quickFollowUpEnabled && quickFollowUpFields) {
    quickFollowUpEnabled.addEventListener("change", function () {
      if (this.checked) {
        quickFollowUpFields.style.display = "grid";
        quickFollowUpFields.style.gridColumn = "1 / -1";
        if (quickFollowUpDate) quickFollowUpDate.required = true;
      } else {
        quickFollowUpFields.style.display = "none";
        if (quickFollowUpDate) quickFollowUpDate.required = false;
      }
    });
  }

  // ─── Quick Create Dynamic Dropdowns ───
  const qcBranch = document.querySelector('#quickCreateModal [name="branch"]');
  const qcVet = document.querySelector(
    '#quickCreateModal [name="preferred_vet"]',
  );
  const qcDate = document.querySelector(
    '#quickCreateModal [name="appointment_date"]',
  );
  const qcTime = document.querySelector("#id_quick_appointment_time");
  const qcTimeHint = document.getElementById("quickTimeHint");

  // Helper to show hints
  function showQCHint(msg, color = "#666") {
    if (qcTimeHint) {
      qcTimeHint.innerHTML = '<i class="bx bx-info-circle"></i> ' + msg;
      qcTimeHint.style.color = color;
    }
  }

  // Fetch Vets when Branch changes
  function fetchQCVets() {
    if (!qcBranch || !qcVet) return;
    const branchId = qcBranch.value;
    const dateVal = qcDate ? qcDate.value : "";

    qcVet.innerHTML = '<option value="">Loading...</option>';

    if (!branchId) {
      qcVet.innerHTML = '<option value="">-- Select branch first --</option>';
      return;
    }

    let url = `/appointments/api/vets/?branch=${branchId}`;
    if (dateVal) url += `&date=${dateVal}`;

    fetch(url)
      .then((r) => r.json())
      .then((data) => {
        qcVet.innerHTML = '<option value="">-- Any Available Vet --</option>';
        
        // Show warning if no vets scheduled on the selected date
        if (dateVal && !data.has_vets) {
          showQCHint(
            "⚠ No vets scheduled for this date. Booking will be pending vet assignment.",
            "#e65100"
          );
        } else if (dateVal && data.has_vets) {
          showQCHint(
            `${data.vets.length} vet(s) available on this date.`,
            "#388e3c"
          );
        }
        
        data.vets.forEach((v) => {
          const opt = document.createElement("option");
          opt.value = v.id;
          opt.textContent = v.name;
          qcVet.appendChild(opt);
        });
      })
      .catch(() => {
        qcVet.innerHTML = '<option value="">-- Error loading vets --</option>';
      });
  }

  // Fetch Times when Vet, Branch, or Date changes
  function fetchQCTimes() {
    if (!qcBranch || !qcVet || !qcDate || !qcTime) return;

    const branchId = qcBranch.value;
    const vetId = qcVet.value;
    const dateVal = qcDate.value;

    qcTime.innerHTML = '<option value="">Loading times...</option>';

    if (!branchId || !dateVal) {
      qcTime.innerHTML =
        '<option value="">-- Select date and branch --</option>';
      showQCHint("Select a branch and date to load available times.");
      return;
    }

    let url = `/appointments/api/times/?branch=${branchId}&date=${dateVal}`;
    if (vetId) url += `&vet=${vetId}`;

    showQCHint("Checking availability...", "#1976d2");

    fetch(url)
      .then((r) => r.json())
      .then((data) => {
        qcTime.innerHTML = '<option value="">-- Select Time --</option>';
        if (data.times.length === 0) {
          // Distinguish between no vets scheduled vs all slots booked
          if (!data.has_scheduled_vets) {
            showQCHint("⚠ No vets scheduled for this date. Booking will be pending vet assignment.", "#e65100");
          } else {
            showQCHint("⚠ No available slots for this date. All vets are fully booked.", "#d32f2f");
          }
          return;
        }

        let availableCount = 0;
        let bookedCount = 0;

        if (!vetId) {
          const amSlots = [];
          const pmSlots = [];

          data.times.forEach((t) => {
            const [hours] = t.time.split(':').map(Number);
            if (t.available) {
              if (hours < 12) {
                amSlots.push(t);
              } else {
                pmSlots.push(t);
              }
              availableCount++;
            } else {
              bookedCount++;
            }
          });

          if (availableCount === 0) {
            qcTime.innerHTML = '<option value="">-- All slots booked --</option>';
            showQCHint("⚠ All slots are booked for this selection.", "#d32f2f");
            return;
          }

          if (amSlots.length > 0) {
            const opt = document.createElement("option");
            opt.value = "MORNING";
            opt.textContent = "Morning (08:00 AM - 12:00 PM)";
            qcTime.appendChild(opt);
          }

          if (pmSlots.length > 0) {
            const opt = document.createElement("option");
            opt.value = "AFTERNOON";
            opt.textContent = "Afternoon (01:00 PM - 05:00 PM)";
            qcTime.appendChild(opt);
          }

          showQCHint(
            '<strong>Flexible Timing:</strong> When you select "Morning" or "Afternoon", any available veterinarian will be assigned.',
            '#388e3c'
          );
        } else {
          data.times.forEach((t) => {
            const opt = document.createElement("option");
            opt.value = t.time;

            let label = `${t.label}`;

            if (t.available) {
              opt.disabled = false;
              availableCount++;
            } else {
              label += ' (Booked)';
              opt.disabled = true;
              opt.style.color = '#999';
              opt.style.fontStyle = 'italic';
              bookedCount++;
            }

            opt.textContent = label;
            qcTime.appendChild(opt);
          });

          if (availableCount === 0) {
            showQCHint("⚠ All slots are booked for this selection.", "#d32f2f");
          } else if (bookedCount > 0) {
            showQCHint(
              `✓ Found ${availableCount} available slot(s). ${bookedCount} slot(s) already booked.`,
              "#388e3c",
            );
          } else {
            showQCHint(
              `✓ Found ${availableCount} available time slot(s).`,
              "#388e3c",
            );
          }
        }
      })
      .catch(() => {
        qcTime.innerHTML = '<option value="">-- Error --</option>';
        showQCHint("Failed to load time slots.", "#d32f2f");
      });
  }

  // Bind Listeners
  if (qcBranch) {
    qcBranch.addEventListener("change", () => {
      fetchQCVets();
      fetchQCTimes();
    });
  }
  if (qcDate) {
    qcDate.addEventListener("change", () => {
      fetchQCVets();
      fetchQCTimes();
    });
  }
  if (qcVet) {
    qcVet.addEventListener("change", () => {
      fetchQCTimes();
    });
  }

  // ═══════════════════════════════════════════════════════════════
  // OWNER / PET AUTO-FILL LOGIC (Mirroring Medical Records Form)
  // ═══════════════════════════════════════════════════════════════
  const clientSourceSelect = document.getElementById("qc-client-source");
  const sourceHiddenField = document.getElementById("qc-source-hidden");
  const ownerSelect = document.getElementById("ownerSelect");
  const petSelect = document.getElementById("petSelect");
  const selectedUserIdField = document.querySelector('#quickCreateModal input[name="selected_user_id"]');
  const selectedPetIdField = document.querySelector('#quickCreateModal input[name="selected_pet_id"]');

  // Owner groups
  const ownerPortalGroup = document.getElementById("qc-owner-portal-group");
  const ownerNameGroup = document.getElementById("qc-owner-name-group");

  // Pet groups
  const petPortalGroup = document.getElementById("qc-pet-portal-group");
  const petNameGroup = document.getElementById("qc-pet-name-group");
  const petManualToggle = document.getElementById("qc-pet-manual-toggle");
  const petManualToggleLabel = document.getElementById("qc-pet-manual-toggle-label");

  // Form fields for auto-fill
  const ownerNameField = document.querySelector('#quickCreateModal input[name="owner_name"]');
  const ownerPhoneField = document.querySelector('#quickCreateModal input[name="owner_phone"]');
  const ownerEmailField = document.querySelector('#quickCreateModal input[name="owner_email"]');
  const ownerAddressField = document.querySelector('#quickCreateModal textarea[name="owner_address"]');
  const petNameField = document.querySelector('#quickCreateModal input[name="pet_name"]');
  const petSpeciesField = document.querySelector('#quickCreateModal input[name="pet_species"]');
  const petBreedField = document.querySelector('#quickCreateModal input[name="pet_breed"]');
  const petDobField = document.querySelector('#quickCreateModal input[name="pet_dob"]');
  const petSexField = document.querySelector('#quickCreateModal select[name="pet_sex"]');
  const petColorField = document.querySelector('#quickCreateModal input[name="pet_color"]');

  let ownersCache = [];
  let petsCache = [];

  // Toggle between Portal and Walk-in modes
  function toggleClientSource() {
    const isPortal = clientSourceSelect && clientSourceSelect.value === "PORTAL";

    // Update hidden source field
    if (sourceHiddenField) sourceHiddenField.value = isPortal ? "PORTAL" : "WALKIN";

    if (isPortal) {
      // Portal Mode: Show owner dropdown, hide manual owner name input
      if (ownerPortalGroup) ownerPortalGroup.style.display = "";
      if (ownerNameGroup) ownerNameGroup.style.display = "none";
      if (petPortalGroup) petPortalGroup.style.display = "";

      // Pet name initially hidden in portal mode (dropdown used instead)
      if (petNameGroup && !petManualToggle?.checked) {
        petNameGroup.style.display = "none";
      }

      // Reset pet dropdown state
      if (petSelect && !ownerSelect?.value) {
        petSelect.innerHTML = '<option value="">— Select owner first —</option>';
        petSelect.disabled = true;
      }
    } else {
      // Walk-in Mode: Hide owner dropdown, show manual owner name input
      if (ownerPortalGroup) ownerPortalGroup.style.display = "none";
      if (ownerNameGroup) ownerNameGroup.style.display = "";
      if (petPortalGroup) petPortalGroup.style.display = "none";

      // Clear portal selections
      if (ownerSelect) ownerSelect.value = "";
      if (selectedUserIdField) selectedUserIdField.value = "";

      // Pet name always shown in walk-in mode
      if (petNameGroup) petNameGroup.style.display = "";

      // Clear all fields for fresh walk-in entry
      if (ownerNameField) ownerNameField.value = "";
      if (ownerPhoneField) ownerPhoneField.value = "";
      if (ownerEmailField) ownerEmailField.value = "";
      if (ownerAddressField) ownerAddressField.value = "";

      // Reset pet dropdown
      if (petSelect) {
        petSelect.innerHTML = '<option value="">— Select owner first —</option>';
        petSelect.disabled = true;
      }
      if (petManualToggleLabel) petManualToggleLabel.style.display = "none";
      if (petManualToggle) petManualToggle.checked = false;

      clearPetFields();
    }
  }

  // Load owners for portal mode
  function loadOwners() {
    if (ownersCache.length > 0) return;
    fetch("/appointments/api/owners/")
      .then((r) => r.json())
      .then((data) => {
        ownersCache = data.owners || [];
        if (ownerSelect) {
          ownerSelect.innerHTML = '<option value="">— Select Owner —</option>';
          ownersCache.forEach((owner) => {
            const opt = document.createElement("option");
            opt.value = owner.id;
            opt.textContent = owner.name + (owner.phone ? " (" + owner.phone + ")" : "");
            opt.dataset.name = owner.name;
            opt.dataset.email = owner.email;
            opt.dataset.phone = owner.phone;
            opt.dataset.address = owner.address;
            ownerSelect.appendChild(opt);
          });
        }
      })
      .catch(() => {
        console.error("Failed to load owners");
      });
  }

  // When owner is selected (Portal mode), auto-fill owner fields and load pets
  if (ownerSelect) {
    ownerSelect.addEventListener("change", function () {
      const ownerId = this.value;
      if (selectedUserIdField) selectedUserIdField.value = ownerId || "";

      if (ownerId) {
        // Find owner data from dropdown option
        const selectedOpt = this.options[this.selectedIndex];

        // Auto-fill the owner_name field (hidden in Portal mode but still submitted)
        if (ownerNameField) ownerNameField.value = selectedOpt.dataset.name || "";
        if (ownerEmailField) ownerEmailField.value = selectedOpt.dataset.email || "";
        if (ownerPhoneField) ownerPhoneField.value = selectedOpt.dataset.phone || "";
        if (ownerAddressField) ownerAddressField.value = selectedOpt.dataset.address || "";

        // Load pets for this owner
        if (petSelect) {
          petSelect.disabled = true;
          petSelect.innerHTML = '<option value="">Loading pets...</option>';
        }

        fetch(`/appointments/api/pets/?owner_id=${ownerId}`)
          .then((r) => r.json())
          .then((data) => {
            petsCache = data.pets || [];
            if (petSelect) {
              petSelect.innerHTML = '<option value="">— Select Pet —</option>';
              if (petsCache.length === 0) {
                petSelect.innerHTML = '<option value="">— No pets registered —</option>';
                // Show manual pet input for new pet
                if (petManualToggleLabel) petManualToggleLabel.style.display = "";
                if (petNameGroup) petNameGroup.style.display = "";
              } else {
                petsCache.forEach((pet) => {
                  const opt = document.createElement("option");
                  opt.value = pet.id;
                  opt.textContent = `${pet.name} (${pet.species || "Unknown"})`;
                  opt.dataset.name = pet.name;
                  opt.dataset.species = pet.species;
                  opt.dataset.breed = pet.breed;
                  opt.dataset.dob = pet.dob;
                  opt.dataset.sex = pet.sex;
                  opt.dataset.color = pet.color;
                  petSelect.appendChild(opt);
                });
                // Show manual toggle option
                if (petManualToggleLabel) petManualToggleLabel.style.display = "";
                // Hide pet name field initially (dropdown active)
                if (petNameGroup && !petManualToggle?.checked) petNameGroup.style.display = "none";
              }
              petSelect.disabled = false;
            }
          })
          .catch(() => {
            if (petSelect) {
              petSelect.innerHTML = '<option value="">— Error loading pets —</option>';
              petSelect.disabled = false;
            }
          });
      } else {
        // No owner selected: reset
        if (ownerNameField) ownerNameField.value = "";
        if (ownerEmailField) ownerEmailField.value = "";
        if (ownerPhoneField) ownerPhoneField.value = "";
        if (ownerAddressField) ownerAddressField.value = "";
        if (petSelect) {
          petSelect.innerHTML = '<option value="">— Select owner first —</option>';
          petSelect.disabled = true;
        }
        if (petManualToggleLabel) petManualToggleLabel.style.display = "none";
        if (petManualToggle) petManualToggle.checked = false;
        if (petNameGroup) petNameGroup.style.display = "none";
        clearPetFields();
      }
    });
  }

  // When pet is selected from dropdown, auto-fill pet fields
  if (petSelect) {
    petSelect.addEventListener("change", function () {
      const petId = this.value;
      if (selectedPetIdField) selectedPetIdField.value = petId || "";

      if (petId) {
        const selectedOpt = this.options[this.selectedIndex];
        if (petNameField) petNameField.value = selectedOpt.dataset.name || "";
        if (petSpeciesField) petSpeciesField.value = selectedOpt.dataset.species || "";
        if (petBreedField) petBreedField.value = selectedOpt.dataset.breed || "";
        if (petDobField) petDobField.value = selectedOpt.dataset.dob || "";
        if (petSexField) petSexField.value = selectedOpt.dataset.sex || "";
        if (petColorField) petColorField.value = selectedOpt.dataset.color || "";
      } else {
        clearPetFields();
      }
    });
  }

  // Manual pet name toggle (for Portal mode when typing new pet)
  if (petManualToggle) {
    petManualToggle.addEventListener("change", function () {
      if (this.checked) {
        // Show manual pet name input, hide dropdown selection
        if (petNameGroup) petNameGroup.style.display = "";
        if (petSelect) {
          petSelect.style.display = "none";
          petSelect.value = "";
        }
        if (selectedPetIdField) selectedPetIdField.value = "";
        clearPetFields();
      } else {
        // Show dropdown, hide manual input if owner has pets
        if (petSelect) petSelect.style.display = "";
        if (petNameGroup && petsCache.length > 0) petNameGroup.style.display = "none";
      }
    });
  }

  function clearPetFields() {
    if (petNameField) petNameField.value = "";
    if (petSpeciesField) petSpeciesField.value = "";
    if (petBreedField) petBreedField.value = "";
    if (petDobField) petDobField.value = "";
    if (petSexField) petSexField.value = "";
    if (petColorField) petColorField.value = "";
    if (selectedPetIdField) selectedPetIdField.value = "";
  }

  // Client source toggle listener
  if (clientSourceSelect) {
    clientSourceSelect.addEventListener("change", toggleClientSource);
  }

  // Load owners and set initial state when quick create modal opens
  if (quickCreateBtn) {
    quickCreateBtn.addEventListener("click", function () {
      loadOwners();
      // Reset to initial Portal state
      if (clientSourceSelect) clientSourceSelect.value = "PORTAL";
      toggleClientSource();
    });
  }

  // ═══════════════════════════════════════════════════════════════
  // AUTO-POPULATE QUICK CREATE FROM URL (From Patient Profile)
  // ═══════════════════════════════════════════════════════════════
  const autoQc = urlParams.get('auto_qc');
  if (autoQc === '1' && quickCreateModal) {
    // Open modal
    openModal(quickCreateModal);
    
    const source = urlParams.get('qc_source');
    if (clientSourceSelect && source) {
      clientSourceSelect.value = source;
      toggleClientSource();
    }
    
    // Helper to extract and fill text parameters
    const fillField = (name, urlParamName) => {
        const val = urlParams.get(urlParamName);
        if (val) {
            const el = document.querySelector(`#quickCreateModal [name="${name}"]`);
            if (el) el.value = val;
        }
    };
    
    fillField("owner_name", "qc_owner_name");
    fillField("owner_phone", "qc_owner_phone");
    fillField("owner_email", "qc_owner_email");
    fillField("owner_address", "qc_owner_address");
    fillField("pet_name", "qc_pet_name");
    fillField("pet_species", "qc_pet_species");
    fillField("pet_breed", "qc_pet_breed");
    fillField("pet_dob", "qc_pet_dob");
    fillField("pet_sex", "qc_pet_sex");
    fillField("pet_color", "qc_pet_color");

    if (source === 'PORTAL') {
      const ownerId = urlParams.get('qc_owner_id');
      const petId = urlParams.get('qc_pet_id');
      
      loadOwners();
      let attempts = 0;
      const interval = setInterval(() => {
        if (ownerSelect && ownerSelect.options.length > 1) {
          clearInterval(interval);
          if (ownerId) {
             ownerSelect.value = ownerId;
             // Trigger change to load pets
             ownerSelect.dispatchEvent(new Event("change"));
             
             let petAttempts = 0;
             const petInterval = setInterval(() => {
               if (petSelect && !petSelect.disabled && petSelect.options.length > 1) {
                 clearInterval(petInterval);
                 if (petId) {
                   petSelect.value = petId;
                   petSelect.dispatchEvent(new Event("change"));
                 }
               } else if (petAttempts++ > 30) {
                 clearInterval(petInterval);
               }
             }, 100);
          }
        } else if (attempts++ > 30) {
          clearInterval(interval);
        }
      }, 100);
    } else {
        // Walkin sets values directly; link the pet ID for DB consistency
        if (selectedPetIdField && urlParams.get("qc_pet_id")) {
             selectedPetIdField.value = urlParams.get("qc_pet_id");
        }
    }
  }

});

