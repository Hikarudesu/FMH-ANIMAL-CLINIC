/**
 * booking.js — Smart booking with availability engine
 * Consistent with admin portal scheduling logic
 * Uses dropdown-based time selection populated dynamically
 */
document.addEventListener("DOMContentLoaded", function () {
  const branchSelect = document.querySelector('[name="branch"]');
  const dateInput = document.querySelector('[name="appointment_date"]');
  const vetSelect = document.querySelector('[name="preferred_vet"]');
  const timeSelect = document.querySelector('[name="appointment_time"]');
  const timeHint = document.getElementById("timeHint");

  if (!branchSelect || !vetSelect || !timeSelect) return;

  // Set min date to today
  if (dateInput) {
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, "0");
    const dd = String(today.getDate()).padStart(2, "0");
    dateInput.setAttribute("min", yyyy + "-" + mm + "-" + dd);
  }

  // Store available dates for vet-specific filtering
  let vetAvailableDates = null;
  let scheduledDates = null;
  let timeRequestId = 0;
  let dateAvailabilityRequestId = 0;
  let scheduleDaysRequestId = 0;
  let datePicker = null;

  if (dateInput && typeof window.flatpickr === "function") {
    datePicker = window.flatpickr(dateInput, {
      dateFormat: "Y-m-d",
      minDate: "today",
      disableMobile: true,
      onOpen: (_selectedDates, _dateString, instance) => {
        fetchScheduleDays(instance.currentYear, instance.currentMonth + 1);
      },
      onMonthChange: (_selectedDates, _dateString, instance) => {
        fetchScheduleDays(instance.currentYear, instance.currentMonth + 1);
        if (vetSelect.value) updateDateAvailability(instance.currentYear, instance.currentMonth + 1);
      },
      onYearChange: (_selectedDates, _dateString, instance) => {
        fetchScheduleDays(instance.currentYear, instance.currentMonth + 1);
        if (vetSelect.value) updateDateAvailability(instance.currentYear, instance.currentMonth + 1);
      },
      onDayCreate: (_selectedDates, _dateString, _instance, dayElement) => {
        if (scheduledDates === null) return;
        const dayDate = dayElement.dateObj;
        const dateKey = [
          dayDate.getFullYear(),
          String(dayDate.getMonth() + 1).padStart(2, "0"),
          String(dayDate.getDate()).padStart(2, "0"),
        ].join("-");
        const indicator = document.createElement("span");
        indicator.className = "schedule-day-dot " +
          (scheduledDates.has(dateKey) ? "has-schedule" : "no-schedule");
        indicator.setAttribute("aria-hidden", "true");
        dayElement.appendChild(indicator);
      },
    });
  }

  function fetchScheduleDays(year, month) {
    const branch = branchSelect.value;
    const vet = vetSelect.value;
    const requestId = ++scheduleDaysRequestId;

    if (!branch || !datePicker) {
      scheduledDates = null;
      if (datePicker) datePicker.redraw();
      return;
    }

    scheduledDates = null;
    const params = new URLSearchParams({ year, month, branch });
    if (vet) params.set("vet", vet);

    fetch(`${API_DATES}?${params.toString()}`)
      .then((response) => response.json())
      .then((data) => {
        if (
          requestId !== scheduleDaysRequestId ||
          branchSelect.value !== branch ||
          vetSelect.value !== vet ||
          datePicker.currentYear !== Number(year) ||
          datePicker.currentMonth + 1 !== Number(month)
        ) return;

        scheduledDates = new Set(data.dates || []);
        datePicker.redraw();
      })
      .catch(() => {
        if (requestId === scheduleDaysRequestId) {
          scheduledDates = null;
          datePicker.redraw();
        }
      });
  }

  /**
   * Fetch available vets when branch or date changes
   */
  function fetchVets() {
    const branch = branchSelect.value;
    const dt = dateInput ? dateInput.value : "";
    const selectedVet = vetSelect.value;

    vetSelect.innerHTML = '<option value="">Loading...</option>';

    if (!branch) {
      vetSelect.innerHTML = '<option value="">— Select branch first —</option>';
      return Promise.resolve();
    }

    let url = API_VETS + "?branch=" + branch;
    if (dt) url += "&date=" + dt;

    return fetch(url)
      .then((r) => r.json())
      .then((data) => {
        vetSelect.innerHTML =
          '<option value="">— No preferred vet (any available) —</option>';
        
        // Show warning if no vets scheduled on the selected date
        if (dt && !data.has_vets) {
          showTimeHint(
            "⚠ No vets scheduled for this date. Your booking will be pending vet assignment.",
            "#e65100"
          );
        } else if (dt && data.has_vets) {
          showTimeHint(
            `${data.vets.length} vet(s) available on this date. Select your preferred vet or leave blank for any available.`,
            "#388e3c"
          );
        }
        
        data.vets.forEach((v) => {
          const opt = document.createElement("option");
          opt.value = v.id;
          opt.textContent = v.name;
          vetSelect.appendChild(opt);
        });

        // Date/branch reloads must not silently discard a vet selected while
        // the availability request was in flight.
        if (
          selectedVet &&
          Array.from(vetSelect.options).some(
            (option) => option.value === selectedVet
          )
        ) {
          vetSelect.value = selectedVet;
        }
      })
      .catch(() => {
        vetSelect.innerHTML =
          '<option value="">— Could not load vets —</option>';
      });
  }

  /**
   * Fetch and populate available time slots in dropdown
   * When no vet selected: show AM/PM options
   * When vet selected: show detailed time slots
   */
  function fetchTimeSlots() {
    const requestId = ++timeRequestId;
    const vet = vetSelect.value;
    const dt = dateInput ? dateInput.value : "";
    const branch = branchSelect.value;

    timeSelect.innerHTML = '<option value="">Loading times...</option>';

    if (!dt || !branch) {
      timeSelect.innerHTML = '<option value="">— Select branch and date first —</option>';
      showTimeHint("Select a branch and date to load available times.");
      return;
    }

    let url = API_TIMES + "?date=" + dt + "&branch=" + branch;
    if (vet) url += "&vet=" + vet;

    showTimeHint("Checking availability...", "#1976d2");

    fetch(url)
      .then((r) => r.json())
      .then((data) => {
        if (requestId !== timeRequestId) return;

        timeSelect.innerHTML = '<option value="">— Select Time —</option>';

        if (data.times.length === 0) {
          timeSelect.innerHTML = '<option value="">— No available slots —</option>';
          if (vet) {
            showTimeHint(
              "No available slots for this vet on this date. Try another date or vet.",
              "#e65100"
            );
          } else {
            showTimeHint(
              "No scheduled vets on this date. Please select another date.",
              "#e65100"
            );
          }
          return;
        }

        let availableCount = 0;
        let bookedCount = 0;

        // If NO vet selected, group by AM/PM
        if (!vet) {
          const amSlots = [];
          const pmSlots = [];

          data.times.forEach((slot) => {
            const [hours] = slot.time.split(':').map(Number);
            if (slot.available) {
              if (hours < 12) {
                amSlots.push(slot);
              } else {
                pmSlots.push(slot);
              }
              availableCount++;
            } else {
              bookedCount++;
            }
          });

          if (availableCount === 0) {
            timeSelect.innerHTML = '<option value="">— All slots booked —</option>';
            showTimeHint(
              "All time slots are booked for this selection. Try another date or vet.",
              "#e65100"
            );
            return;
          }

          // Add AM option if available - use "MORNING" marker instead of specific time
          if (amSlots.length > 0) {
            const opt = document.createElement("option");
            opt.value = "MORNING"; // Use marker, backend will assign first available slot
            opt.textContent = `Morning (08:00 AM - 12:00 PM)`;
            timeSelect.appendChild(opt);
          }

          // Add PM option if available - use "AFTERNOON" marker instead of specific time
          if (pmSlots.length > 0) {
            const opt = document.createElement("option");
            opt.value = "AFTERNOON"; // Use marker, backend will assign first available slot
            opt.textContent = `Afternoon (01:00 PM - 05:00 PM)`;
            timeSelect.appendChild(opt);
          }

          // Show helpful hint for any available vet
          showTimeHint(
            `<strong>Flexible Timing:</strong> When you select "Morning" or "Afternoon", any available veterinarian will be assigned. You can expect to be called within your selected time window. ${amSlots.length > 0 && pmSlots.length > 0 ? 'Both morning and afternoon slots are available.' : ''}`,
            "#388e3c"
          );
        } else {
          // Specific vet selected - show detailed time slots
          data.times.forEach((slot) => {
            const opt = document.createElement("option");
            opt.value = slot.time;

            // Format: "09:00 AM – 09:30 AM"
            let label = slot.label;
            if (slot.shift_type) {
              label += ` (${slot.shift_type})`;
            }

            if (slot.available) {
              // Available slot
              opt.disabled = false;
              availableCount++;
            } else {
              // Booked slot - show but disable it
              label += ' (Booked)';
              opt.disabled = true;
              opt.style.color = '#999';
              opt.style.fontStyle = 'italic';
              bookedCount++;
            }

            opt.textContent = label;
            timeSelect.appendChild(opt);
          });

          if (availableCount === 0) {
            timeSelect.innerHTML = '<option value="">— All slots booked —</option>';
            showTimeHint(
              "All time slots are booked for this selection. Try another date or vet.",
              "#e65100"
            );
          } else {
            if (bookedCount > 0) {
              showTimeHint(
                `Found ${availableCount} available slot(s). ${bookedCount} slot(s) already booked for ${vetSelect.options[vetSelect.selectedIndex].text}.`,
                "#388e3c"
              );
            } else {
              showTimeHint(
                `Found ${availableCount} available time slot(s) for ${vetSelect.options[vetSelect.selectedIndex].text}.`,
                "#388e3c"
              );
            }
          }
        }
      })
      .catch(() => {
        timeSelect.innerHTML = '<option value="">— Error loading times —</option>';
        showTimeHint("Failed to load time slots. Please try again.", "#e65100");
      });
  }

  /**
   * Show hint message below time field
   */
  function showTimeHint(text, color) {
    if (timeHint) {
      timeHint.innerHTML = "<i class='bx bx-info-circle'></i> " + text;
      timeHint.style.color = color || "var(--text-3)";
    }
  }

  /**
   * If vet is selected, fetch available dates for that vet
   */
  function updateDateAvailability(targetYear, targetMonth) {
    const vet = vetSelect.value;
    const branch = branchSelect.value;
    const requestId = ++dateAvailabilityRequestId;

    if (!vet || !dateInput || !branch) {
      vetAvailableDates = null;
      return;
    }

    // Use the visible calendar month, or fall back to the selected date.
    const currentVal = dateInput.value;
    const refDate = currentVal
      ? new Date(currentVal + "T00:00:00")
      : new Date();
    const year = targetYear || refDate.getFullYear();
    const month = targetMonth || refDate.getMonth() + 1;

    const url = `${API_DATES}?vet=${vet}&year=${year}&month=${month}&branch=${branch}`;

    fetch(url)
      .then((r) => r.json())
      .then((data) => {
        if (
          requestId !== dateAvailabilityRequestId ||
          vetSelect.value !== vet ||
          dateInput.value !== currentVal
        ) {
          return;
        }

        vetAvailableDates = data.dates || [];
        if (vetAvailableDates.length === 0) {
          showTimeHint(
            "This vet has no scheduled dates this month. Try a different vet or month.",
            "#e65100"
          );
        } else {
          showTimeHint(
            `This vet is available on ${vetAvailableDates.length} date(s) this month. Select a date.`,
            "#009688"
          );
        }

      })
      .catch(() => {
        vetAvailableDates = null;
      });
  }

  // ─── Event Listeners ───

  branchSelect.addEventListener("change", function () {
    vetAvailableDates = null;
    fetchVets().then(() => {
      if (datePicker) {
        fetchScheduleDays(datePicker.currentYear, datePicker.currentMonth + 1);
      }
      if (dateInput && dateInput.value) {
        fetchTimeSlots();
      } else {
        timeSelect.innerHTML = '<option value="">— Select branch and date first —</option>';
        showTimeHint("Select a date to see available time slots.");
      }
    });
  });

  if (dateInput) {
    // Listen to both 'input' and 'change' to handle both date picker and manual input
    dateInput.addEventListener("input", function () {
      fetchVets().then(fetchTimeSlots);
    });
    dateInput.addEventListener("change", function () {
      fetchVets().then(fetchTimeSlots);
    });
  }

  vetSelect.addEventListener("change", function () {
    // Do not use the previous vet's schedule while loading the new one.
    vetAvailableDates = null;
    if (datePicker) {
      fetchScheduleDays(datePicker.currentYear, datePicker.currentMonth + 1);
    }
    if (this.value) {
      updateDateAvailability();
    } else {
      dateAvailabilityRequestId += 1;
      showTimeHint("Select a date to see all available time slots.");
    }
    if (dateInput && dateInput.value) {
      fetchTimeSlots();
    }
  });

  // ─── Auto-initialize if branch is pre-filled (e.g., user's preferred branch) ───
  if (branchSelect.value) {
    fetchVets().then(() => {
      if (datePicker) {
        fetchScheduleDays(datePicker.currentYear, datePicker.currentMonth + 1);
      }
    });
  }
});
