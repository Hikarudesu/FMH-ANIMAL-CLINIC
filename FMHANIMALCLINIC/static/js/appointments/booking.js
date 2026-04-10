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

  /**
   * Fetch available vets when branch or date changes
   */
  function fetchVets() {
    const branch = branchSelect.value;
    const dt = dateInput ? dateInput.value : "";

    vetSelect.innerHTML = '<option value="">Loading...</option>';

    if (!branch) {
      vetSelect.innerHTML = '<option value="">— Select branch first —</option>';
      return;
    }

    let url = API_VETS + "?branch=" + branch;
    if (dt) url += "&date=" + dt;

    fetch(url)
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
    const vet = vetSelect.value;
    const dt = dateInput ? dateInput.value : "";
    const branch = branchSelect.value;

    timeSelect.innerHTML = '<option value="">Loading times...</option>';

    if (!dt || !branch) {
      timeSelect.innerHTML = '<option value="">— Select branch and date first —</option>';
      showTimeHint("Select a branch and date to load available times.");
      return;
    }

    // If vet-specific dates are loaded and this date is not available
    if (vet && vetAvailableDates && !vetAvailableDates.includes(dt)) {
      timeSelect.innerHTML = '<option value="">— No slots available —</option>';
      showTimeHint(
        "This vet is not scheduled on this date. Please pick another date or vet.",
        "#e65100"
      );
      return;
    }

    let url = API_TIMES + "?date=" + dt + "&branch=" + branch;
    if (vet) url += "&vet=" + vet;

    showTimeHint("Checking availability...", "#1976d2");

    fetch(url)
      .then((r) => r.json())
      .then((data) => {
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
  function updateDateAvailability() {
    const vet = vetSelect.value;
    const branch = branchSelect.value;

    if (!vet || !dateInput || !branch) {
      vetAvailableDates = null;
      return;
    }

    // Calculate month/year based on current date input or now
    const currentVal = dateInput.value;
    const refDate = currentVal
      ? new Date(currentVal + "T00:00:00")
      : new Date();
    const year = refDate.getFullYear();
    const month = refDate.getMonth() + 1;

    const url = `${API_DATES}?vet=${vet}&year=${year}&month=${month}&branch=${branch}`;

    fetch(url)
      .then((r) => r.json())
      .then((data) => {
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

        // If current date is selected but not available, clear it
        if (currentVal && !vetAvailableDates.includes(currentVal)) {
          dateInput.value = "";
          timeSelect.innerHTML = '<option value="">— Select date first —</option>';
          showTimeHint(
            "Your selected date is not in this vet's schedule. Please pick an available date.",
            "#e65100"
          );
        }
      })
      .catch(() => {
        vetAvailableDates = null;
      });
  }

  // ─── Event Listeners ───

  branchSelect.addEventListener("change", function () {
    // Store current vet selection state before fetching new vets
    const currentVetValue = vetSelect.value;
    const currentTimeValue = timeSelect.value;
    const isAnyVetMode = !currentVetValue; // True if "any available vet" was selected
    
    fetchVets();
    vetAvailableDates = null;
    
    // If user had "any available vet" selected and a date is set, re-fetch time slots
    // This preserves the AM/PM mode instead of resetting to "specific time"
    if (isAnyVetMode && dateInput && dateInput.value) {
      // Short delay to allow vets to load first
      setTimeout(() => {
        fetchTimeSlots();
        // Try to restore previous time selection (MORNING/AFTERNOON)
        if (currentTimeValue === "MORNING" || currentTimeValue === "AFTERNOON") {
          setTimeout(() => {
            if (timeSelect.querySelector(`option[value="${currentTimeValue}"]`)) {
              timeSelect.value = currentTimeValue;
            }
          }, 100);
        }
      }, 200);
    } else {
      timeSelect.innerHTML = '<option value="">— Select branch and date first —</option>';
      showTimeHint("Select a date to see available time slots.");
    }
  });

  if (dateInput) {
    // Listen to both 'input' and 'change' to handle both date picker and manual input
    dateInput.addEventListener("input", function () {
      fetchVets();
      fetchTimeSlots();
    });
    dateInput.addEventListener("change", function () {
      fetchVets();
      fetchTimeSlots();
    });
  }

  vetSelect.addEventListener("change", function () {
    if (this.value) {
      updateDateAvailability();
    } else {
      vetAvailableDates = null;
      showTimeHint("Select a date to see all available time slots.");
    }
    if (dateInput && dateInput.value) {
      fetchTimeSlots();
    }
  });

  // ─── Auto-initialize if branch is pre-filled (e.g., user's preferred branch) ───
  if (branchSelect.value) {
    fetchVets();
  }
});
