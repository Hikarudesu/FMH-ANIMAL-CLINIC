# Domain Entity Registry & Purpose

- **branches.Branch** (`branches_branch`): Represents a physical clinic location.
- **appointments.Appointment** (`appointments_appointment`): Represents a pet appointment / reservation.
- **inquiries.Inquiry** (`inquiries_inquiry`): Stores contact inquiries submitted via the landing page contact form.
- **accounts.User** (`accounts_user`): Custom user model with role-based access control.
- **patients.Pet** (`patients_pet`): A pet that may belong to a registered portal user (owner) or a walk-in guest.
- **employees.StaffMember** (`employees_staffmember`): Represents a staff member at the clinic.
- **settings.ReasonForVisit** (`settings_reasonforvisit`): Configurable reasons for appointment visits.
- **pos.Sale** (`pos_sale`): Represents a completed sale transaction.

# Entity Attribute Specifications

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

## inquiries.Inquiry

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `full_name` | — | `full_name` | `VARCHAR` |
| `email` | — | `email` | `VARCHAR` |
| `phone` | — | `phone` | `VARCHAR` |
| `branch` | FK | `branch_id` | `BIGINT` |
| `message` | — | `message` | `TEXT` |
| `status` | — | `status` | `VARCHAR` |
| `priority` | — | `priority` | `VARCHAR` |
| `responded_by` | FK | `responded_by_id` | `BIGINT` |
| `response` | — | `response` | `TEXT` |
| `response_date` | — | `response_date` | `TIMESTAMPTZ` |
| `internal_notes` | — | `internal_notes` | `TEXT` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |
| `updated_at` | — | `updated_at` | `TIMESTAMPTZ` |

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

## patients.Pet

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `owner` | FK | `owner_id` | `BIGINT` |
| `branch` | FK | `branch_id` | `BIGINT` |
| `guest_owner_name` | — | `guest_owner_name` | `VARCHAR` |
| `guest_owner_phone` | — | `guest_owner_phone` | `VARCHAR` |
| `guest_owner_email` | — | `guest_owner_email` | `VARCHAR` |
| `guest_owner_address` | — | `guest_owner_address` | `TEXT` |
| `source` | — | `source` | `VARCHAR` |
| `name` | — | `name` | `VARCHAR` |
| `species` | — | `species` | `VARCHAR` |
| `breed` | — | `breed` | `VARCHAR` |
| `date_of_birth` | — | `date_of_birth` | `DATE` |
| `sex` | — | `sex` | `VARCHAR` |
| `color` | — | `color` | `VARCHAR` |
| `photo` | — | `photo` | `VARCHAR` |
| `clinical_status` | FK | `clinical_status_id` | `BIGINT` |
| `is_active` | — | `is_active` | `BOOLEAN` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |

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

## settings.ReasonForVisit

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `name` | — | `name` | `VARCHAR` |
| `code` | Unique | `code` | `VARCHAR` |
| `description` | — | `description` | `TEXT` |
| `order` | — | `order` | `INTEGER` |
| `is_active` | — | `is_active` | `BOOLEAN` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |
| `updated_at` | — | `updated_at` | `TIMESTAMPTZ` |

## pos.Sale

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `transaction_id` | Unique | `transaction_id` | `VARCHAR` |
| `branch` | FK | `branch_id` | `BIGINT` |
| `customer_type` | — | `customer_type` | `VARCHAR` |
| `customer` | FK | `customer_id` | `BIGINT` |
| `pet` | FK | `pet_id` | `BIGINT` |
| `guest_name` | — | `guest_name` | `VARCHAR` |
| `guest_phone` | — | `guest_phone` | `VARCHAR` |
| `guest_email` | — | `guest_email` | `VARCHAR` |
| `guest_pet_name` | — | `guest_pet_name` | `VARCHAR` |
| `subtotal` | — | `subtotal` | `NUMERIC(12,2)` |
| `discount_percent` | — | `discount_percent` | `NUMERIC(5,2)` |
| `discount_reason` | — | `discount_reason` | `VARCHAR` |
| `tax_amount` | — | `tax_amount` | `NUMERIC(12,2)` |
| `total` | — | `total` | `NUMERIC(12,2)` |
| `amount_paid` | — | `amount_paid` | `NUMERIC(12,2)` |
| `change_due` | — | `change_due` | `NUMERIC(12,2)` |
| `status` | — | `status` | `VARCHAR` |
| `cashier` | FK | `cashier_id` | `BIGINT` |
| `voided_by` | FK | `voided_by_id` | `BIGINT` |
| `void_reason` | — | `void_reason` | `VARCHAR` |
| `notes` | — | `notes` | `TEXT` |
| `soa_data` | — | `soa_data` | `TEXT` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |
| `updated_at` | — | `updated_at` | `TIMESTAMPTZ` |
| `completed_at` | — | `completed_at` | `TIMESTAMPTZ` |
