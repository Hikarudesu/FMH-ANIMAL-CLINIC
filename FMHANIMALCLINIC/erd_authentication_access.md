# Domain Entity Registry & Purpose

- **accounts.User** (`accounts_user`): Custom user model with role-based access control.
- **accounts.UserActivity** (`accounts_useractivity`): Logs recent actions performed by the user.
- **accounts.ActivityLog** (`accounts_activitylog`): Comprehensive activity logging for all system actions.
- **accounts.Module** (`accounts_module`): Represents a module/section in the system.
- **accounts.ModulePermission** (`accounts_modulepermission`): Represents a specific permission for a module.
- **accounts.Role** (`accounts_role`): Custom role with configurable permissions.
- **accounts.SpecialPermission** (`accounts_specialpermission`): Special permissions for edge cases not covered by module permissions.
- **accounts.RoleSpecialPermission** (`accounts_rolespecialpermission`): Links roles to special permissions.
- **accounts.PetOwner** (`accounts_petowner`): Profile model for Pet Owners (clients).
- **accounts.OTPToken** (`accounts_otptoken`): Stores one-time password tokens for password reset.
- **branches.Branch** (`branches_branch`): Represents a physical clinic location.

# Entity Attribute Specifications

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

## accounts.UserActivity

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `user` | FK | `user_id` | `BIGINT` |
| `action` | — | `action` | `VARCHAR` |
| `object_name` | — | `object_name` | `VARCHAR` |
| `timestamp` | — | `timestamp` | `TIMESTAMPTZ` |

## accounts.ActivityLog

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `user` | FK | `user_id` | `BIGINT` |
| `action` | — | `action` | `VARCHAR` |
| `category` | — | `category` | `VARCHAR` |
| `action_type` | — | `action_type` | `VARCHAR` |
| `branch` | FK | `branch_id` | `BIGINT` |
| `details` | — | `details` | `TEXT` |
| `object_type` | — | `object_type` | `VARCHAR` |
| `object_id` | — | `object_id` | `INTEGER` |
| `ip_address` | — | `ip_address` | `INET` |
| `timestamp` | — | `timestamp` | `TIMESTAMPTZ` |

## accounts.Module

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `code` | Unique | `code` | `VARCHAR` |
| `name` | — | `name` | `VARCHAR` |
| `description` | — | `description` | `TEXT` |
| `icon` | — | `icon` | `VARCHAR` |
| `url_name` | — | `url_name` | `VARCHAR` |
| `parent` | FK | `parent_id` | `BIGINT` |
| `display_order` | — | `display_order` | `INTEGER` |
| `is_active` | — | `is_active` | `BOOLEAN` |

## accounts.ModulePermission

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `role` | FK | `role_id` | `BIGINT` |
| `module` | FK | `module_id` | `BIGINT` |
| `permission_type` | Unique (composite) | `permission_type` | `VARCHAR` |
| `restrict_to_branch` | — | `restrict_to_branch` | `BOOLEAN` |

## accounts.Role

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `name` | Unique | `name` | `VARCHAR` |
| `code` | Unique | `code` | `VARCHAR` |
| `description` | — | `description` | `TEXT` |
| `hierarchy_level` | — | `hierarchy_level` | `INTEGER` |
| `is_staff_role` | — | `is_staff_role` | `BOOLEAN` |
| `is_system_role` | — | `is_system_role` | `BOOLEAN` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |
| `updated_at` | — | `updated_at` | `TIMESTAMPTZ` |

## accounts.SpecialPermission

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `code` | Unique | `code` | `VARCHAR` |
| `name` | — | `name` | `VARCHAR` |
| `description` | — | `description` | `TEXT` |

## accounts.RoleSpecialPermission

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `role` | FK | `role_id` | `BIGINT` |
| `permission` | FK | `permission_id` | `BIGINT` |

## accounts.PetOwner

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `user` | FK, Unique | `user_id` | `BIGINT` |
| `emergency_contact_name` | — | `emergency_contact_name` | `VARCHAR` |
| `emergency_contact_phone` | — | `emergency_contact_phone` | `VARCHAR` |
| `preferred_communication` | — | `preferred_communication` | `VARCHAR` |
| `notes` | — | `notes` | `TEXT` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |
| `updated_at` | — | `updated_at` | `TIMESTAMPTZ` |

## accounts.OTPToken

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `user` | FK | `user_id` | `BIGINT` |
| `otp_code` | — | `otp_code` | `VARCHAR` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |
| `expires_at` | — | `expires_at` | `TIMESTAMPTZ` |
| `is_used` | — | `is_used` | `BOOLEAN` |

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
