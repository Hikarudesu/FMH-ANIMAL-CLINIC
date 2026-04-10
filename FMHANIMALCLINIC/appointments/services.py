"""
Service layer for appointment business logic.

This module contains the core business logic for appointment management,
extracted from views for better separation of concerns and testability.
"""
import logging
from datetime import datetime, timedelta, time
from typing import List, Dict, Optional

from django.db.models import Q

from branches.models import Branch
from employees.models import StaffMember, VetSchedule
from .models import Appointment

logger = logging.getLogger('fmh')


class AppointmentService:
    """Service class for appointment-related operations."""

    # System-wide lunch break
    LUNCH_START = time(12, 0)
    LUNCH_END = time(13, 0)
    SLOT_DURATION_MINUTES = 30

    @staticmethod
    def get_available_slots(
        vet_id: Optional[int] = None,
        target_date=None,
        branch_id: Optional[int] = None,
        exclude_appointment_id: Optional[int] = None
    ) -> List[Dict]:
        """
        Core availability engine.
        
        Returns a list of available time slots checking both VetSchedule 
        and existing Appointments.

        Args:
            vet_id: If provided, returns slots for that specific vet.
                   If None, returns all slots across any scheduled vet.
            target_date: The date to check availability for.
            branch_id: Filter by branch.
            exclude_appointment_id: Exclude this appointment from booking check 
                                   (useful for editing).

        Returns:
            List of slot dictionaries with time, availability, and vet info.
        """
        if not target_date:
            return []

        # Get schedule entries for this date
        filters = {
            'date': target_date,
            'is_available': True,
        }
        if vet_id:
            filters['staff_id'] = vet_id
        if branch_id:
            filters['branch_id'] = branch_id

        schedules = VetSchedule.objects.filter(
            **filters
        ).select_related('staff', 'branch')

        # Get existing appointments for this date (optimized query)
        appt_filters = {'appointment_date': target_date}
        if branch_id:
            appt_filters['branch_id'] = branch_id

        existing_appointments = Appointment.objects.filter(
            **appt_filters
        ).exclude(
            status__in=['CANCELLED']
        ).select_related('preferred_vet')

        # Exclude specific appointment if provided (for editing)
        if exclude_appointment_id:
            existing_appointments = existing_appointments.exclude(pk=exclude_appointment_id)

        slots = []
        slot_duration = timedelta(minutes=AppointmentService.SLOT_DURATION_MINUTES)

        for sched in schedules:
            # Generate 30-minute slots within the schedule window
            current = datetime.combine(target_date, sched.start_time)
            end = datetime.combine(target_date, sched.end_time)

            while current + slot_duration <= end:
                slot_time = current.time()
                slot_end_time = (current + slot_duration).time()

                # Skip lunch break
                if AppointmentService.LUNCH_START <= slot_time < AppointmentService.LUNCH_END:
                    current += slot_duration
                    continue

                # Check if this slot is already booked
                slot_booked = existing_appointments.filter(
                    Q(preferred_vet=sched.staff, appointment_time=slot_time) |
                    Q(preferred_vet__isnull=True, appointment_time=slot_time)
                ).exists()

                slots.append({
                    'time': slot_time.strftime('%H:%M'),
                    'label': f"{slot_time.strftime('%I:%M %p')} – {slot_end_time.strftime('%I:%M %p')}",
                    'start_label': slot_time.strftime('%I:%M %p'),
                    'end_label': slot_end_time.strftime('%I:%M %p'),
                    'vet_id': sched.staff.id,
                    'vet_name': sched.staff.full_name,
                    'shift_type': sched.get_shift_type_display(),
                    'available': not slot_booked,
                    'booked_label': 'Appointed already' if slot_booked else '',
                })

                current += slot_duration

        # Deduplicate by time if no specific vet (any vet available)
        if not vet_id:
            time_map = {}
            for slot in slots:
                t = slot['time']
                if t not in time_map:
                    time_map[t] = slot
                else:
                    # If ANY vet is available at this time, mark the slot as available
                    if slot['available']:
                        time_map[t] = slot
            slots = sorted(time_map.values(), key=lambda s: s['time'])
        else:
            slots = sorted(slots, key=lambda s: s['time'])

        return slots

    @staticmethod
    def get_available_dates(
        branch_id: int,
        vet_id: Optional[int] = None,
        days_ahead: int = 60
    ) -> List[str]:
        """
        Get list of dates that have available vet schedules.
        
        Args:
            branch_id: The branch to check.
            vet_id: Optional specific vet to check.
            days_ahead: Number of days to look ahead.
            
        Returns:
            List of date strings in YYYY-MM-DD format.
        """
        from datetime import date as date_type
        from django.utils import timezone
        
        today = timezone.localdate()
        end_date = today + timedelta(days=days_ahead)
        
        filters = {
            'branch_id': branch_id,
            'is_available': True,
            'date__gte': today,
            'date__lte': end_date,
        }
        if vet_id:
            filters['staff_id'] = vet_id
            
        available_dates = VetSchedule.objects.filter(
            **filters
        ).values_list('date', flat=True).distinct().order_by('date')
        
        return [d.isoformat() for d in available_dates]

    @staticmethod
    def get_available_vets(branch_id: int, appointment_date=None) -> List[StaffMember]:
        """
        Get veterinarians available at a branch on a specific date.
        
        Args:
            branch_id: The branch to check.
            appointment_date: The date to check availability.
            
        Returns:
            QuerySet of available StaffMember objects.
        """
        if appointment_date:
            # Get vets who have a schedule on this date
            scheduled_staff_ids = VetSchedule.objects.filter(
                branch_id=branch_id,
                date=appointment_date,
                is_available=True,
            ).values_list('staff_id', flat=True).distinct()

            return StaffMember.objects.filter(
                id__in=scheduled_staff_ids,
                user__assigned_role__code='veterinarian',
                is_active=True,
            ).select_related('user', 'user__assigned_role')
        else:
            # Return all vets assigned to this branch
            return StaffMember.objects.filter(
                user__assigned_role__code='veterinarian',
                is_active=True,
                branch_id=branch_id,
            ).select_related('user', 'user__assigned_role')

    @staticmethod
    def auto_assign_vet(appointment: Appointment) -> Optional[StaffMember]:
        """
        Auto-assign an available vet to an appointment if none was selected.
        
        Args:
            appointment: The appointment to assign a vet to.
            
        Returns:
            The assigned StaffMember or None if no vet available.
        """
        if appointment.preferred_vet:
            return appointment.preferred_vet
            
        if not (appointment.branch and appointment.appointment_date and appointment.appointment_time):
            return None
            
        # Get vets scheduled at this branch on this date
        scheduled_vets = VetSchedule.objects.filter(
            branch=appointment.branch,
            date=appointment.appointment_date,
            is_available=True,
        ).values_list('staff_id', flat=True).distinct()

        # Find a vet who is NOT already booked at this time
        for vet_id in scheduled_vets:
            is_booked = Appointment.objects.filter(
                preferred_vet_id=vet_id,
                appointment_date=appointment.appointment_date,
                appointment_time=appointment.appointment_time,
            ).exclude(status='CANCELLED').exists()

            if not is_booked:
                try:
                    vet = StaffMember.objects.get(pk=vet_id)
                    appointment.preferred_vet = vet
                    logger.info(
                        "Auto-assigned vet %s to appointment %s",
                        vet.full_name, appointment.pk
                    )
                    return vet
                except StaffMember.DoesNotExist:
                    continue
                    
        return None

    @staticmethod
    def cleanup_expired_appointments() -> int:
        """
        Clean up expired pending appointments.
        
        Returns:
            Number of appointments cleaned up.
        """
        return Appointment.cleanup_expired()

    @staticmethod
    def check_slot_availability(
        branch_id: int,
        appointment_date,
        appointment_time,
        vet_id: Optional[int] = None,
        exclude_appointment_id: Optional[int] = None
    ) -> bool:
        """
        Check if a specific slot is available.
        
        Args:
            branch_id: The branch to check.
            appointment_date: The date.
            appointment_time: The time.
            vet_id: Optional specific vet.
            exclude_appointment_id: Exclude this appointment from the check.
            
        Returns:
            True if the slot is available, False otherwise.
        """
        # Check if time is in lunch break
        if AppointmentService.LUNCH_START <= appointment_time < AppointmentService.LUNCH_END:
            return False
            
        # Check if vet is scheduled
        schedule_filter = {
            'branch_id': branch_id,
            'date': appointment_date,
            'is_available': True,
        }
        if vet_id:
            schedule_filter['staff_id'] = vet_id
            
        if not VetSchedule.objects.filter(**schedule_filter).exists():
            return False
            
        # Check for existing appointments
        appt_filter = {
            'branch_id': branch_id,
            'appointment_date': appointment_date,
            'appointment_time': appointment_time,
        }
        if vet_id:
            appt_filter['preferred_vet_id'] = vet_id
            
        appointments = Appointment.objects.filter(**appt_filter).exclude(status='CANCELLED')
        
        if exclude_appointment_id:
            appointments = appointments.exclude(pk=exclude_appointment_id)
            
        return not appointments.exists()
