# Domain Entity Registry & Purpose

- **inventory.Product** (`inventory_product`): Represents a product or medication in the clinic's inventory.
- **inventory.StockAdjustment** (`inventory_stockadjustment`): Tracks history of stock changes.
- **inventory.Reservation** (`inventory_reservation`): A product reservation made by a user from the digital catalog.
- **inventory.StockTransfer** (`inventory_stocktransfer`): Tracks inventory transfers between branches.
- **billing.Service** (`billing_service`): Represents a clinic service (consultations, procedures, grooming, etc.).
- **billing.CustomerStatement** (`billing_customerstatement`): Stores Statement of Account created by admin staff.
- **pos.Sale** (`pos_sale`): Represents a completed sale transaction.
- **pos.SaleItem** (`pos_saleitem`): A line item in a sale - can be a service, product, or medication.
- **pos.Payment** (`pos_payment`): Payment record for a sale. Supports split payments across multiple methods.
- **pos.Refund** (`pos_refund`): Refund record for a sale or specific items.
- **pos.RefundItem** (`pos_refunditem`): Specific items being refunded (for partial refunds).
- **accounts.User** (`accounts_user`): Custom user model with role-based access control.
- **branches.Branch** (`branches_branch`): Represents a physical clinic location.
- **patients.Pet** (`patients_pet`): A pet that may belong to a registered portal user (owner) or a walk-in guest.

# Entity Attribute Specifications

## inventory.Product

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `is_deleted` | — | `is_deleted` | `BOOLEAN` |
| `deleted_at` | — | `deleted_at` | `TIMESTAMPTZ` |
| `name` | — | `name` | `VARCHAR` |
| `description` | — | `description` | `TEXT` |
| `item_type` | — | `item_type` | `VARCHAR` |
| `sku` | — | `sku` | `VARCHAR` |
| `manufacturer` | — | `manufacturer` | `VARCHAR` |
| `unit_cost` | — | `unit_cost` | `NUMERIC(10,2)` |
| `price` | — | `price` | `NUMERIC(10,2)` |
| `unit_of_measurement` | — | `unit_of_measurement` | `VARCHAR` |
| `sale_type` | — | `sale_type` | `VARCHAR` |
| `branch` | FK | `branch_id` | `BIGINT` |
| `is_available` | — | `is_available` | `BOOLEAN` |
| `stock_quantity` | — | `stock_quantity` | `INTEGER` |
| `min_stock_level` | — | `min_stock_level` | `INTEGER` |
| `is_consumable` | — | `is_consumable` | `BOOLEAN` |
| `expiration_date` | — | `expiration_date` | `DATE` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |
| `updated_at` | — | `updated_at` | `TIMESTAMPTZ` |

## inventory.StockAdjustment

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `branch` | FK | `branch_id` | `BIGINT` |
| `product` | FK | `product_id` | `BIGINT` |
| `adjustment_type` | — | `adjustment_type` | `VARCHAR` |
| `reference` | — | `reference` | `VARCHAR` |
| `date` | — | `date` | `DATE` |
| `quantity` | — | `quantity` | `INTEGER` |
| `cost_per_unit` | — | `cost_per_unit` | `NUMERIC(10,2)` |
| `reason` | — | `reason` | `VARCHAR` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |

## inventory.Reservation

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `user` | FK | `user_id` | `BIGINT` |
| `product` | FK | `product_id` | `BIGINT` |
| `quantity` | — | `quantity` | `INTEGER` |
| `status` | — | `status` | `VARCHAR` |
| `notes` | — | `notes` | `TEXT` |
| `pickup_date` | — | `pickup_date` | `DATE` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |
| `updated_at` | — | `updated_at` | `TIMESTAMPTZ` |

## inventory.StockTransfer

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `source_product` | FK | `source_product_id` | `BIGINT` |
| `destination_branch` | FK | `destination_branch_id` | `BIGINT` |
| `quantity` | — | `quantity` | `INTEGER` |
| `status` | — | `status` | `VARCHAR` |
| `notes` | — | `notes` | `TEXT` |
| `requested_by` | FK | `requested_by_id` | `BIGINT` |
| `processed_by` | FK | `processed_by_id` | `BIGINT` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |
| `updated_at` | — | `updated_at` | `TIMESTAMPTZ` |

## billing.Service

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `is_deleted` | — | `is_deleted` | `BOOLEAN` |
| `deleted_at` | — | `deleted_at` | `TIMESTAMPTZ` |
| `name` | — | `name` | `VARCHAR` |
| `cost` | — | `cost` | `NUMERIC(10,2)` |
| `price` | — | `price` | `NUMERIC(10,2)` |
| `category` | — | `category` | `VARCHAR` |
| `tax_rate` | — | `tax_rate` | `VARCHAR` |
| `duration` | — | `duration` | `INTEGER` |
| `description` | — | `description` | `TEXT` |
| `active` | — | `active` | `BOOLEAN` |
| `content` | — | `content` | `TEXT` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |
| `updated_at` | — | `updated_at` | `TIMESTAMPTZ` |

## billing.CustomerStatement

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `statement_number` | Unique | `statement_number` | `VARCHAR` |
| `patient_name` | — | `patient_name` | `VARCHAR` |
| `owner_name` | — | `owner_name` | `VARCHAR` |
| `date` | — | `date` | `DATE` |
| `customer` | FK | `customer_id` | `BIGINT` |
| `sale` | FK | `sale_id` | `BIGINT` |
| `consultation_fee` | — | `consultation_fee` | `NUMERIC(10,2)` |
| `consultation_description` | — | `consultation_description` | `TEXT` |
| `treatment` | — | `treatment` | `NUMERIC(10,2)` |
| `treatment_description` | — | `treatment_description` | `TEXT` |
| `boarding` | — | `boarding` | `NUMERIC(10,2)` |
| `boarding_description` | — | `boarding_description` | `TEXT` |
| `vaccination` | — | `vaccination` | `NUMERIC(10,2)` |
| `vaccination_description` | — | `vaccination_description` | `TEXT` |
| `surgery` | — | `surgery` | `NUMERIC(10,2)` |
| `surgery_description` | — | `surgery_description` | `TEXT` |
| `laboratory` | — | `laboratory` | `NUMERIC(10,2)` |
| `laboratory_description` | — | `laboratory_description` | `TEXT` |
| `grooming` | — | `grooming` | `NUMERIC(10,2)` |
| `grooming_description` | — | `grooming_description` | `TEXT` |
| `others` | — | `others` | `NUMERIC(10,2)` |
| `others_description` | — | `others_description` | `TEXT` |
| `total_amount` | — | `total_amount` | `NUMERIC(10,2)` |
| `deposit` | — | `deposit` | `NUMERIC(10,2)` |
| `balance` | — | `balance` | `NUMERIC(10,2)` |
| `status` | — | `status` | `VARCHAR` |
| `notes` | — | `notes` | `TEXT` |
| `created_by` | FK | `created_by_id` | `BIGINT` |
| `branch` | FK | `branch_id` | `BIGINT` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |
| `updated_at` | — | `updated_at` | `TIMESTAMPTZ` |
| `released_at` | — | `released_at` | `TIMESTAMPTZ` |
| `sent_at` | — | `sent_at` | `TIMESTAMPTZ` |

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

## pos.SaleItem

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `sale` | FK | `sale_id` | `BIGINT` |
| `item_type` | — | `item_type` | `VARCHAR` |
| `service` | FK | `service_id` | `BIGINT` |
| `product` | FK | `product_id` | `BIGINT` |
| `name` | — | `name` | `VARCHAR` |
| `description` | — | `description` | `TEXT` |
| `unit_price` | — | `unit_price` | `NUMERIC(10,2)` |
| `quantity` | — | `quantity` | `INTEGER` |
| `discount` | — | `discount` | `NUMERIC(10,2)` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |

## pos.Payment

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `sale` | FK | `sale_id` | `BIGINT` |
| `method` | — | `method` | `VARCHAR` |
| `amount` | — | `amount` | `NUMERIC(12,2)` |
| `status` | — | `status` | `VARCHAR` |
| `reference_number` | — | `reference_number` | `VARCHAR` |
| `received_by` | FK | `received_by_id` | `BIGINT` |
| `notes` | — | `notes` | `TEXT` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |

## pos.Refund

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `refund_id` | Unique | `refund_id` | `VARCHAR` |
| `sale` | FK | `sale_id` | `BIGINT` |
| `refund_type` | — | `refund_type` | `VARCHAR` |
| `amount` | — | `amount` | `NUMERIC(12,2)` |
| `reason` | — | `reason` | `TEXT` |
| `status` | — | `status` | `VARCHAR` |
| `requested_by` | FK | `requested_by_id` | `BIGINT` |
| `approved_by` | FK | `approved_by_id` | `BIGINT` |
| `processed_by` | FK | `processed_by_id` | `BIGINT` |
| `refund_method` | — | `refund_method` | `VARCHAR` |
| `reference_number` | — | `reference_number` | `VARCHAR` |
| `notes` | — | `notes` | `TEXT` |
| `created_at` | — | `created_at` | `TIMESTAMPTZ` |
| `completed_at` | — | `completed_at` | `TIMESTAMPTZ` |

## pos.RefundItem

| Attribute Name | Key | Field | Type |
|---|---|---|---|
| `id` | PK | `id` | `BIGINT` |
| `refund` | FK | `refund_id` | `BIGINT` |
| `sale_item` | FK | `sale_item_id` | `BIGINT` |
| `quantity` | — | `quantity` | `INTEGER` |
| `amount` | — | `amount` | `NUMERIC(10,2)` |

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
