# Domain Entity Registry & Purpose

- **employees.StaffMember** (`employees_staffmember`): Represents a staff member at the clinic.
- **employees.VetSchedule** (`employees_vetschedule`): Represents a vet/staff schedule entry for a specific day.
- **employees.RecurringSchedule** (`employees_recurringschedule`): Weekly recurring schedule template for automatic schedule generation.
- **attendance.DailyAttendance** (`attendance_dailyattendance`): Processed daily attendance for each staff (used by payroll).
- **attendance.MonthlyAttendanceSummary** (`attendance_monthlyattendancesummary`): Attendance totals exported by a biometric device for payroll.
- **attendance.AttendanceUpload** (`attendance_attendanceupload`): Original monthly attendance export and its import metadata.
- **notifications.FollowUp** (`notifications_followup`): Represents a follow-up visit scheduled by an admin for a pet.
- **notifications.Notification** (`notifications_notification`): User-facing notification record.
- **payroll.PayrollPeriod** (`payroll_payrollperiod`): Payroll period supporting first-half and second-half payrolls.
- **payroll.Payslip** (`payroll_payslip`): Individual payslip for an employee.
- **payroll.PayslipDeduction** (`payroll_payslipdeduction`): Custom line-item deduction attached to a payslip.
- **payroll.PayrollAuditLog** (`payroll_payrollauditlog`): Comprehensive audit trail for all payroll system actions.
- **payroll.StatutoryDeductionTable** (`payroll_statutorydeductiontable`): Philippine statutory deduction brackets for SSS, PhilHealth, PAG-IBIG, etc.
- **payroll.PayslipEmailLog** (`payroll_payslipemaillog`): Track email sends for audit and re-send capabilities.
- **accounts.User** (`accounts_user`): Custom user model with role-based access control.
- **branches.Branch** (`branches_branch`): Represents a physical clinic location.
- **appointments.Appointment** (`appointments_appointment`): Represents a pet appointment / reservation.

# Entity Attribute Specifications

## employees.StaffMember

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `is_deleted` | — | `is_deleted` | `BOOLEAN` |
| `deleted_at` | — | `deleted_at` | `TIMESTAMPTZ` |
| `first_name` | — | `first_name` | `VARCHAR` |
| `last_name` | — | `last_name` | `VARCHAR` |
| `email` | — | `email` | `VARCHAR` |
| `phone` | — | `phone` | `VARCHAR` |
| `biometric_id` | Unique | `biometric_id` | `VARCHAR` |
| `position` | — | `position` | `VARCHAR` |
| `salary` | — | `salary` | `NUMERIC(10,2)` |
| `branch` | FK | `branch_id` | `BIGINT` |
| `date_hired` | — | `date_hired` | `DATE` |
| `is_active` | — | `is_active` | `BOOLEAN` |
| `default_staff_allowance` | — | `default_staff_allowance` | `NUMERIC(10,2)` |
| `default_custom_deductions` | — | `default_custom_deductions` | `JSONB` |
| `default_days_worked` | — | `default_days_worked` | `INTEGER` |
| `license_number` | — | `license_number` | `VARCHAR` |
| `license_expiry` | — | `license_expiry` | `DATE` |
| `user` | FK, Unique | `user_id` | `BIGINT` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |
| `updated_at` | — | `updated_at` | `TIMESTAMPTZ` |

## employees.VetSchedule

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `staff` | FK | `staff_id` | `BIGINT` |
| `date` | Unique (composite) | `date` | `DATE` |
| `start_time` | Unique (composite) | `start_time` | `TIME` |
| `end_time` | — | `end_time` | `TIME` |
| `branch` | FK | `branch_id` | `BIGINT` |
| `is_available` | — | `is_available` | `BOOLEAN` |
| `shift_type` | — | `shift_type` | `VARCHAR` |
| `notes` | — | `notes` | `TEXT` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |

## employees.RecurringSchedule

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `staff` | FK | `staff_id` | `BIGINT` |
| `branch` | FK | `branch_id` | `BIGINT` |
| `day_of_week` | — | `day_of_week` | `INTEGER` |
| `start_time` | — | `start_time` | `TIME` |
| `end_time` | — | `end_time` | `TIME` |
| `shift_type` | — | `shift_type` | `VARCHAR` |
| `is_active` | — | `is_active` | `BOOLEAN` |
| `effective_from` | — | `effective_from` | `DATE` |
| `effective_until` | — | `effective_until` | `DATE` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |

## attendance.DailyAttendance

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `staff` | FK | `staff_id` | `BIGINT` |
| `attendance_date` | Unique (composite) | `attendance_date` | `DATE` |
| `expected_start` | — | `expected_start` | `TIME` |
| `expected_end` | — | `expected_end` | `TIME` |
| `expected_hours` | — | `expected_hours` | `NUMERIC(5,2)` |
| `check_in` | — | `check_in` | `TIME` |
| `check_out` | — | `check_out` | `TIME` |
| `morning_in` | — | `morning_in` | `TIME` |
| `morning_out` | — | `morning_out` | `TIME` |
| `afternoon_in` | — | `afternoon_in` | `TIME` |
| `afternoon_out` | — | `afternoon_out` | `TIME` |
| `ot_in` | — | `ot_in` | `TIME` |
| `ot_out` | — | `ot_out` | `TIME` |
| `ot_hours_calculated` | — | `ot_hours_calculated` | `NUMERIC(5,2)` |
| `total_work_minutes` | — | `total_work_minutes` | `INTEGER` |
| `late_minutes` | — | `late_minutes` | `INTEGER` |
| `overtime_minutes` | — | `overtime_minutes` | `INTEGER` |
| `four_punch_complete` | — | `four_punch_complete` | `BOOLEAN` |
| `punch_validation_status` | — | `punch_validation_status` | `VARCHAR` |
| `punch_validation_error` | — | `punch_validation_error` | `TEXT` |
| `status` | — | `status` | `VARCHAR` |
| `is_present` | — | `is_present` | `BOOLEAN` |
| `is_manually_adjusted` | — | `is_manually_adjusted` | `BOOLEAN` |
| `adjustment_notes` | — | `adjustment_notes` | `TEXT` |
| `adjusted_by` | FK | `adjusted_by_id` | `BIGINT` |
| `is_approved` | — | `is_approved` | `BOOLEAN` |
| `approved_by` | FK | `approved_by_id` | `BIGINT` |
| `approved_at` | — | `approved_at` | `TIMESTAMPTZ` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |
| `updated_at` | — | `updated_at` | `TIMESTAMPTZ` |

## attendance.MonthlyAttendanceSummary

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `staff` | FK | `staff_id` | `BIGINT` |
| `period_start` | Unique (composite) | `period_start` | `DATE` |
| `period_end` | Unique (composite) | `period_end` | `DATE` |
| `working_days` | — | `working_days` | `INTEGER` |
| `attendance_days` | — | `attendance_days` | `INTEGER` |
| `absence_days` | — | `absence_days` | `INTEGER` |
| `late_days` | — | `late_days` | `INTEGER` |
| `required_working_days` | — | `required_working_days` | `INTEGER` |
| `required_working_days_first_half` | — | `required_working_days_first_half` | `INTEGER` |
| `required_working_days_second_half` | — | `required_working_days_second_half` | `INTEGER` |
| `four_punch_validation_status` | — | `four_punch_validation_status` | `VARCHAR` |
| `four_punch_violations_count` | — | `four_punch_violations_count` | `INTEGER` |
| `four_punch_violations` | — | `four_punch_violations` | `JSONB` |
| `overtime_hours` | — | `overtime_hours` | `NUMERIC(7,2)` |
| `sick_hours` | — | `sick_hours` | `NUMERIC(7,2)` |
| `leave_hours` | — | `leave_hours` | `NUMERIC(7,2)` |
| `daily_salary` | — | `daily_salary` | `NUMERIC(12,2)` |
| `overtime_pay` | — | `overtime_pay` | `NUMERIC(12,2)` |
| `charges` | — | `charges` | `NUMERIC(12,2)` |
| `real_pay` | — | `real_pay` | `NUMERIC(12,2)` |
| `review_status` | — | `review_status` | `VARCHAR` |
| `source_filename` | — | `source_filename` | `VARCHAR` |
| `uploaded_by` | FK | `uploaded_by_id` | `BIGINT` |
| `approved_by` | FK | `approved_by_id` | `BIGINT` |
| `approved_at` | — | `approved_at` | `TIMESTAMPTZ` |
| `imported_at` | — | `imported_at` | `TIMESTAMPTZ` |

## attendance.AttendanceUpload

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `period_start` | Unique (composite) | `period_start` | `DATE` |
| `period_end` | Unique (composite) | `period_end` | `DATE` |
| `source_file` | — | `source_file` | `VARCHAR` |
| `source_filename` | — | `source_filename` | `VARCHAR` |
| `unmatched_biometric_ids` | — | `unmatched_biometric_ids` | `JSONB` |
| `uploaded_by` | FK | `uploaded_by_id` | `BIGINT` |
| `imported_at` | — | `imported_at` | `TIMESTAMPTZ` |

## notifications.FollowUp

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `appointment` | FK | `appointment_id` | `BIGINT` |
| `pet_name` | — | `pet_name` | `VARCHAR` |
| `follow_up_date` | — | `follow_up_date` | `DATE` |
| `follow_up_end_date` | — | `follow_up_end_date` | `DATE` |
| `reason` | — | `reason` | `TEXT` |
| `created_by` | FK | `created_by_id` | `BIGINT` |
| `is_completed` | — | `is_completed` | `BOOLEAN` |
| `email_sent_at` | — | `email_sent_at` | `TIMESTAMPTZ` |
| `email_attempts` | — | `email_attempts` | `INTEGER` |
| `email_last_error` | — | `email_last_error` | `TEXT` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |

## notifications.Notification

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `user` | FK | `user_id` | `BIGINT` |
| `title` | — | `title` | `VARCHAR` |
| `message` | — | `message` | `TEXT` |
| `notification_type` | — | `notification_type` | `VARCHAR` |
| `module_context` | — | `module_context` | `VARCHAR` |
| `related_follow_up` | FK | `related_follow_up_id` | `BIGINT` |
| `related_object_id` | — | `related_object_id` | `INTEGER` |
| `is_read` | — | `is_read` | `BOOLEAN` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |

## payroll.PayrollPeriod

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `month` | Unique (composite) | `month` | `INTEGER` |
| `year` | Unique (composite) | `year` | `INTEGER` |
| `period_type` | Unique (composite) | `period_type` | `VARCHAR` |
| `branch` | FK | `branch_id` | `BIGINT` |
| `status` | — | `status` | `VARCHAR` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |
| `edited_at` | — | `edited_at` | `TIMESTAMPTZ` |
| `generated_at` | — | `generated_at` | `TIMESTAMPTZ` |
| `released_at` | — | `released_at` | `TIMESTAMPTZ` |
| `released_by` | FK | `released_by_id` | `BIGINT` |
| `total_gross` | — | `total_gross` | `NUMERIC(14,2)` |
| `total_deductions` | — | `total_deductions` | `NUMERIC(14,2)` |
| `total_net` | — | `total_net` | `NUMERIC(14,2)` |
| `employee_count` | — | `employee_count` | `INTEGER` |
| `notes` | — | `notes` | `TEXT` |

## payroll.Payslip

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `payroll_period` | FK | `payroll_period_id` | `BIGINT` |
| `employee` | FK | `employee_id` | `BIGINT` |
| `base_salary` | — | `base_salary` | `NUMERIC(12,2)` |
| `days_worked` | — | `days_worked` | `INTEGER` |
| `days_absent` | — | `days_absent` | `INTEGER` |
| `working_days` | — | `working_days` | `INTEGER` |
| `sick_hours` | — | `sick_hours` | `NUMERIC(7,2)` |
| `leave_hours` | — | `leave_hours` | `NUMERIC(7,2)` |
| `daily_salary` | — | `daily_salary` | `NUMERIC(12,2)` |
| `rest_days_mandatory` | — | `rest_days_mandatory` | `INTEGER` |
| `paid_leave_type` | — | `paid_leave_type` | `VARCHAR` |
| `paid_leave_days` | — | `paid_leave_days` | `NUMERIC(5,2)` |
| `rest_days_actual` | — | `rest_days_actual` | `INTEGER` |
| `sick_leave_days` | — | `sick_leave_days` | `NUMERIC(5,2)` |
| `regular_leave_days` | — | `regular_leave_days` | `NUMERIC(5,2)` |
| `excess_leave_days` | — | `excess_leave_days` | `NUMERIC(5,2)` |
| `rest_days_exceeded_deduction` | — | `rest_days_exceeded_deduction` | `NUMERIC(12,2)` |
| `overtime_hours` | — | `overtime_hours` | `NUMERIC(5,2)` |
| `overtime_pay` | — | `overtime_pay` | `NUMERIC(10,2)` |
| `holiday_pay` | — | `holiday_pay` | `NUMERIC(10,2)` |
| `bonus` | — | `bonus` | `NUMERIC(10,2)` |
| `staff_allowance` | — | `staff_allowance` | `NUMERIC(10,2)` |
| `thirteenth_month_pay` | — | `thirteenth_month_pay` | `NUMERIC(10,2)` |
| `sss` | — | `sss` | `NUMERIC(10,2)` |
| `philhealth` | — | `philhealth` | `NUMERIC(10,2)` |
| `pagibig` | — | `pagibig` | `NUMERIC(10,2)` |
| `tax` | — | `tax` | `NUMERIC(10,2)` |
| `cash_advance` | — | `cash_advance` | `NUMERIC(10,2)` |
| `late_deduction` | — | `late_deduction` | `NUMERIC(10,2)` |
| `absent_deduction` | — | `absent_deduction` | `NUMERIC(10,2)` |
| `other_deductions` | — | `other_deductions` | `NUMERIC(10,2)` |
| `custom_deductions_total` | — | `custom_deductions_total` | `NUMERIC(12,2)` |
| `clinic_sss` | — | `clinic_sss` | `NUMERIC(10,2)` |
| `clinic_philhealth` | — | `clinic_philhealth` | `NUMERIC(10,2)` |
| `clinic_pagibig` | — | `clinic_pagibig` | `NUMERIC(10,2)` |
| `gross_pay` | — | `gross_pay` | `NUMERIC(12,2)` |
| `total_allowances` | — | `total_allowances` | `NUMERIC(12,2)` |
| `total_deductions` | — | `total_deductions` | `NUMERIC(12,2)` |
| `total_clinic_contributions` | — | `total_clinic_contributions` | `NUMERIC(12,2)` |
| `net_pay` | — | `net_pay` | `NUMERIC(12,2)` |
| `status` | — | `status` | `VARCHAR` |
| `released_at` | — | `released_at` | `TIMESTAMPTZ` |
| `received_by_employee` | — | `received_by_employee` | `BOOLEAN` |
| `notes` | — | `notes` | `TEXT` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |
| `updated_at` | — | `updated_at` | `TIMESTAMPTZ` |

## payroll.PayslipDeduction

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `payslip` | FK | `payslip_id` | `BIGINT` |
| `reason` | — | `reason` | `VARCHAR` |
| `amount` | — | `amount` | `NUMERIC(12,2)` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |

## payroll.PayrollAuditLog

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `user` | FK | `user_id` | `BIGINT` |
| `action_type` | — | `action_type` | `VARCHAR` |
| `description` | — | `description` | `TEXT` |
| `payroll_period` | FK | `payroll_period_id` | `BIGINT` |
| `payslip` | FK | `payslip_id` | `BIGINT` |
| `staff_member` | FK | `staff_member_id` | `BIGINT` |
| `metadata` | — | `metadata` | `JSONB` |
| `ip_address` | — | `ip_address` | `INET` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |

## payroll.StatutoryDeductionTable

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `deduction_type` | — | `deduction_type` | `VARCHAR` |
| `min_salary` | — | `min_salary` | `NUMERIC(12,2)` |
| `max_salary` | — | `max_salary` | `NUMERIC(12,2)` |
| `employee_rate` | — | `employee_rate` | `NUMERIC(5,4)` |
| `employer_rate` | — | `employer_rate` | `NUMERIC(5,4)` |
| `fixed_amount` | — | `fixed_amount` | `NUMERIC(10,2)` |
| `effective_date` | — | `effective_date` | `DATE` |
| `end_date` | — | `end_date` | `DATE` |

## payroll.PayslipEmailLog

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `payslip` | FK | `payslip_id` | `BIGINT` |
| `recipient_email` | — | `recipient_email` | `VARCHAR` |
| `sent_at` | — | `sent_at` | `TIMESTAMPTZ` |
| `status` | — | `status` | `VARCHAR` |
| `error_message` | — | `error_message` | `TEXT` |

## accounts.User

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `password` | — | `password` | `VARCHAR` |
| `last_login` | — | `last_login` | `TIMESTAMPTZ` |
| `is_superuser` | — | `is_superuser` | `BOOLEAN` |
| `username` | Unique | `username` | `VARCHAR` |
| `first_name` | — | `first_name` | `VARCHAR` |
| `last_name` | — | `last_name` | `VARCHAR` |
| `email` | — | `email` | `VARCHAR` |
| `is_staff` | — | `is_staff` | `BOOLEAN` |
| `is_active` | — | `is_active` | `BOOLEAN` |
| `date_joined` | — | `date_joined` | `TIMESTAMPTZ` |
| `assigned_role` | FK | `assigned_role_id` | `BIGINT` |
| `branch` | FK | `branch_id` | `BIGINT` |
| `profile_picture` | — | `profile_picture` | `VARCHAR` |
| `phone_number` | — | `phone_number` | `VARCHAR` |
| `address` | — | `address` | `TEXT` |

## branches.Branch

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `name` | Unique | `name` | `VARCHAR` |
| `branch_code` | Unique | `branch_code` | `VARCHAR` |
| `phone_number` | — | `phone_number` | `VARCHAR` |
| `email` | — | `email` | `VARCHAR` |
| `address` | — | `address` | `VARCHAR` |
| `city` | — | `city` | `VARCHAR` |
| `state` | — | `state` | `VARCHAR` |
| `zip_code` | — | `zip_code` | `VARCHAR` |
| `clinic_license_number` | — | `clinic_license_number` | `VARCHAR` |
| `operating_hours` | — | `operating_hours` | `TEXT` |
| `is_active` | — | `is_active` | `BOOLEAN` |
| `google_maps_embed_url` | — | `google_maps_embed_url` | `VARCHAR` |
| `google_maps_link` | — | `google_maps_link` | `VARCHAR` |
| `facebook_url` | — | `facebook_url` | `VARCHAR` |
| `instagram_url` | — | `instagram_url` | `VARCHAR` |
| `messenger_url` | — | `messenger_url` | `VARCHAR` |
| `tiktok_url` | — | `tiktok_url` | `VARCHAR` |
| `display_order` | — | `display_order` | `INTEGER` |
| `badge_label` | — | `badge_label` | `VARCHAR` |
| `is_main_source` | — | `is_main_source` | `BOOLEAN` |
| `logo` | — | `logo` | `VARCHAR` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |
| `updated_at` | — | `updated_at` | `TIMESTAMPTZ` |

## appointments.Appointment

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `owner_name` | — | `owner_name` | `VARCHAR` |
| `owner_email` | — | `owner_email` | `VARCHAR` |
| `owner_phone` | — | `owner_phone` | `VARCHAR` |
| `owner_address` | — | `owner_address` | `TEXT` |
| `pet_name` | — | `pet_name` | `VARCHAR` |
| `pet_species` | — | `pet_species` | `VARCHAR` |
| `pet_breed` | — | `pet_breed` | `VARCHAR` |
| `pet_dob` | — | `pet_dob` | `VARCHAR` |
| `pet_sex` | — | `pet_sex` | `VARCHAR` |
| `pet_color` | — | `pet_color` | `VARCHAR` |
| `pet_symptoms` | — | `pet_symptoms` | `TEXT` |
| `pet` | FK | `pet_id` | `BIGINT` |
| `branch` | FK | `branch_id` | `BIGINT` |
| `preferred_vet` | FK | `preferred_vet_id` | `BIGINT` |
| `appointment_date` | — | `appointment_date` | `DATE` |
| `appointment_time` | — | `appointment_time` | `TIME` |
| `reason_for_visit` | FK | `reason_for_visit_id` | `BIGINT` |
| `source` | — | `source` | `VARCHAR` |
| `status` | — | `status` | `VARCHAR` |
| `is_returning_customer` | — | `is_returning_customer` | `BOOLEAN` |
| `user` | FK | `user_id` | `BIGINT` |
| `sale` | FK | `sale_id` | `BIGINT` |
| `notes` | — | `notes` | `TEXT` |
| `reminder_1_sent_at` | — | `reminder_1_sent_at` | `TIMESTAMPTZ` |
| `reminder_2_sent_at` | — | `reminder_2_sent_at` | `TIMESTAMPTZ` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |
| `updated_at` | — | `updated_at` | `TIMESTAMPTZ` |
