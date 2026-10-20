"""Operating hours shared by scheduling and appointment availability."""
from datetime import time


CLINIC_OPEN_TIME = time(8, 0)
CLINIC_CLOSE_TIME = time(19, 0)
APPOINTMENT_SLOT_MINUTES = 30


def is_valid_clinic_schedule(start_time, end_time):
    """Return whether a staff schedule fits within clinic operating hours."""
    return (
        start_time is not None
        and end_time is not None
        and CLINIC_OPEN_TIME <= start_time < end_time <= CLINIC_CLOSE_TIME
    )
