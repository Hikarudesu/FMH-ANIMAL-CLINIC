"""Align legacy product unit/sale values with configured specific options."""

import json

from django.db import migrations
from django.utils.text import slugify


FALLBACK_UOM_OPTIONS = [
    '1 tablet',
    '1 capsule',
    '1 chewable tablet',
    '1 sachet',
    '1 ampule',
    '1 vial',
    '2 mL vial',
    '5 mL vial',
    '10 mL vial',
    '20 mL vial',
    '50 mL vial',
    '100 mL vial',
    '250 mL bottle',
    '500 mL bottle',
    '1 L bottle',
    '1 strip (10 tablets)',
    '1 strip (15 tablets)',
    '1 strip (20 tablets)',
    '1 box',
    '1 pack',
    '1 can',
    '1 tub',
    '1 syringe',
    '1 pair',
    '1 set',
    '1 piece',
    '1 g sachet',
    '5 g sachet',
    '10 g sachet',
    '100 g pack',
    '250 g pack',
    '500 g pack',
    '1 kg sack',
]


FALLBACK_SALE_LABELS = [
    'Per Piece',
    'Per Tablet',
    'Per Capsule',
    'Per Sachet',
    'Per Ampule',
    'Per Vial',
    'Per Bottle',
    'Per Strip',
    'Per Box',
    'Per Pack',
    'Per Can',
    'Per Tub',
    'Per Syringe',
    'Per Pair',
    'Per Set',
    'Per Gram Pack',
    'Per Kilogram Sack',
]


LEGACY_UNIT_MAP = {
    'piece': '1 piece',
    'set': '1 set',
    'box': '1 box',
    'pack': '1 pack',
    'can': '1 can',
    'bottle': '250 mL bottle',
    'vial': '1 vial',
    'tablet': '1 tablet',
    'capsule': '1 capsule',
    'sachet': '1 sachet',
    'ampule': '1 ampule',
    'strip': '1 strip (10 tablets)',
    'tube': '1 tub',
}


def _load_setting_list(SystemSetting, key, fallback):
    setting = SystemSetting.objects.filter(key=key).first()
    if not setting:
        return list(fallback)

    raw_value = setting.value
    try:
        parsed = json.loads(raw_value)
    except Exception:
        parsed = raw_value

    if isinstance(parsed, str):
        parsed = [line.strip() for line in parsed.splitlines() if line.strip()]

    if not isinstance(parsed, list):
        return list(fallback)

    options = [str(item).strip() for item in parsed if str(item).strip()]
    return options or list(fallback)


def _sale_slug_from_unit(unit_label):
    unit = (unit_label or '').strip().lower()

    if 'kg sack' in unit or 'kilogram sack' in unit:
        return 'per-kilogram-sack'
    if (' g pack' in unit) or ('gram pack' in unit):
        return 'per-gram-pack'
    if 'strip' in unit:
        return 'per-strip'
    if 'tablet' in unit:
        return 'per-tablet'
    if 'capsule' in unit:
        return 'per-capsule'
    if 'sachet' in unit:
        return 'per-sachet'
    if 'ampule' in unit:
        return 'per-ampule'
    if 'vial' in unit:
        return 'per-vial'
    if 'bottle' in unit:
        return 'per-bottle'
    if 'box' in unit:
        return 'per-box'
    if 'pack' in unit:
        return 'per-pack'
    if 'can' in unit:
        return 'per-can'
    if 'tub' in unit:
        return 'per-tub'
    if 'syringe' in unit:
        return 'per-syringe'
    if 'pair' in unit:
        return 'per-pair'
    if 'set' in unit:
        return 'per-set'
    return 'per-piece'


def align_inventory_units_and_sale_types(apps, schema_editor):
    Product = apps.get_model('inventory', 'Product')
    SystemSetting = apps.get_model('settings', 'SystemSetting')

    configured_uom = _load_setting_list(
        SystemSetting,
        'inventory_uom_options',
        FALLBACK_UOM_OPTIONS,
    )
    configured_sales = _load_setting_list(
        SystemSetting,
        'inventory_sale_type_options',
        FALLBACK_SALE_LABELS,
    )

    allowed_uom = {value.lower(): value for value in configured_uom}
    allowed_sale_slugs = {slugify(label) for label in configured_sales}

    for product in Product.objects.all():
        current_uom_raw = (product.unit_of_measurement or '').strip()
        current_uom_key = current_uom_raw.lower()

        if current_uom_key in allowed_uom:
            normalized_uom = allowed_uom[current_uom_key]
        else:
            mapped_uom = LEGACY_UNIT_MAP.get(current_uom_key)
            normalized_uom = mapped_uom if mapped_uom in configured_uom else current_uom_raw

        target_sale_slug = _sale_slug_from_unit(normalized_uom)
        if target_sale_slug not in allowed_sale_slugs:
            # Fallback when the preferred slug is not enabled in settings.
            target_sale_slug = 'per-piece' if 'per-piece' in allowed_sale_slugs else (product.sale_type or 'per-piece')

        changed_fields = []
        if normalized_uom and product.unit_of_measurement != normalized_uom:
            product.unit_of_measurement = normalized_uom
            changed_fields.append('unit_of_measurement')

        if target_sale_slug and product.sale_type != target_sale_slug:
            product.sale_type = target_sale_slug
            changed_fields.append('sale_type')

        if changed_fields:
            product.save(update_fields=changed_fields)


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0026_seed_inventory_item_type_options'),
        ('inventory', '0029_normalize_product_uom_casing'),
    ]

    operations = [
        migrations.RunPython(align_inventory_units_and_sale_types, migrations.RunPython.noop),
    ]
