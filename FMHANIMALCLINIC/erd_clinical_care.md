# Domain Entity Registry & Purpose

- **patients.Pet** (`patients_pet`): A pet that may belong to a registered portal user (owner) or a walk-in guest.
- **patients.ClinicalStatusLog** (`patients_clinicalstatuslog`): Tracks every time a pet's clinical status is updated.
- **records.MedicalRecord** (`records_medicalrecord`): Represents a specific medical record/visit history item attached to a Pet.
- **records.RecordEntry** (`records_recordentry`): Represents a single visit/consultation entry on a pet's medical record card.
- **records.MedicalFile** (`records_medicalfile`): Private laboratory, imaging, and external medical document.
- **records.MedicalFileAccessLog** (`records_medicalfileaccesslog`): Immutable audit trail for medical-file access attempts.
- **diagnostics.AIDiagnosis** (`diagnostics_aidiagnosis`): Stores AI-generated diagnostic suggestions for a pet.
- **accounts.User** (`accounts_user`): Custom user model with role-based access control.
- **branches.Branch** (`branches_branch`): Represents a physical clinic location.
- **employees.StaffMember** (`employees_staffmember`): Represents a staff member at the clinic.
- **settings.ClinicalStatus** (`settings_clinicalstatus`): Configurable clinical status options for pets/patients.

# Entity Attribute Specifications

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

## patients.ClinicalStatusLog

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `pet` | FK | `pet_id` | `BIGINT` |
| `status` | FK | `status_id` | `BIGINT` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |

## records.MedicalRecord

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `pet` | FK | `pet_id` | `BIGINT` |
| `vet` | FK | `vet_id` | `BIGINT` |
| `branch` | FK | `branch_id` | `BIGINT` |
| `weight` | — | `weight` | `NUMERIC(5,2)` |
| `temperature` | — | `temperature` | `NUMERIC(4,1)` |
| `history_clinical_signs` | — | `history_clinical_signs` | `TEXT` |
| `treatment` | — | `treatment` | `TEXT` |
| `rx` | — | `rx` | `TEXT` |
| `ff_up` | — | `ff_up` | `DATE` |
| `date_recorded` | — | `date_recorded` | `DATE` |
| `status` | — | `status` | `VARCHAR` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |
| `updated_at` | — | `updated_at` | `TIMESTAMPTZ` |

## records.RecordEntry

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `record` | FK | `record_id` | `BIGINT` |
| `vet` | FK | `vet_id` | `BIGINT` |
| `date_recorded` | — | `date_recorded` | `DATE` |
| `weight` | — | `weight` | `NUMERIC(5,2)` |
| `temperature` | — | `temperature` | `NUMERIC(4,1)` |
| `history_clinical_signs` | — | `history_clinical_signs` | `TEXT` |
| `treatment` | — | `treatment` | `TEXT` |
| `rx` | — | `rx` | `TEXT` |
| `ff_up` | — | `ff_up` | `DATE` |
| `action_required` | FK | `action_required_id` | `BIGINT` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |
| `updated_at` | — | `updated_at` | `TIMESTAMPTZ` |

## records.MedicalFile

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `record` | FK | `record_id` | `BIGINT` |
| `file` | — | `file` | `VARCHAR` |
| `original_name` | — | `original_name` | `VARCHAR` |
| `file_type` | — | `file_type` | `VARCHAR` |
| `uploaded_by` | FK | `uploaded_by_id` | `BIGINT` |
| `sha256` | — | `sha256` | `VARCHAR` |
| `uploaded_at` | — | `uploaded_at` | `TIMESTAMPTZ` |

## records.MedicalFileAccessLog

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `medical_file` | FK | `medical_file_id` | `BIGINT` |
| `user` | FK | `user_id` | `BIGINT` |
| `action` | — | `action` | `VARCHAR` |
| `success` | — | `success` | `BOOLEAN` |
| `ip_address` | — | `ip_address` | `INET` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |
| `detail` | — | `detail` | `VARCHAR` |

## diagnostics.AIDiagnosis

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `pet` | FK | `pet_id` | `BIGINT` |
| `requested_by` | FK | `requested_by_id` | `BIGINT` |
| `input_symptoms` | — | `input_symptoms` | `TEXT` |
| `input_history` | — | `input_history` | `TEXT` |
| `primary_condition` | — | `primary_condition` | `VARCHAR` |
| `primary_reasoning` | — | `primary_reasoning` | `TEXT` |
| `differential_diagnoses` | — | `differential_diagnoses` | `JSONB` |
| `recommended_tests` | — | `recommended_tests` | `JSONB` |
| `warning_signs` | — | `warning_signs` | `JSONB` |
| `summary` | — | `summary` | `TEXT` |
| `raw_response` | — | `raw_response` | `JSONB` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |
| `is_reviewed` | — | `is_reviewed` | `BOOLEAN` |
| `reviewed_by` | FK | `reviewed_by_id` | `BIGINT` |
| `reviewed_at` | — | `reviewed_at` | `TIMESTAMPTZ` |
| `selected_condition` | — | `selected_condition` | `VARCHAR` |
| `selected_tests` | — | `selected_tests` | `JSONB` |
| `vet_prescription` | — | `vet_prescription` | `TEXT` |
| `diagnosis_notes` | — | `diagnosis_notes` | `TEXT` |
| `test_notes` | — | `test_notes` | `TEXT` |
| `linked_record_entry` | FK | `linked_record_entry_id` | `BIGINT` |

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

## settings.ClinicalStatus

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `name` | — | `name` | `VARCHAR` |
| `code` | Unique | `code` | `VARCHAR` |
| `description` | — | `description` | `TEXT` |
| `color` | — | `color` | `VARCHAR` |
| `order` | — | `order` | `INTEGER` |
| `is_active` | — | `is_active` | `BOOLEAN` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |
| `updated_at` | — | `updated_at` | `TIMESTAMPTZ` |
