from django.db import migrations


def clone_pilar_inventory(apps, schema_editor):
    Branch = apps.get_model('branches', 'Branch')
    Product = apps.get_model('inventory', 'Product')

    source_branch = Branch.objects.filter(name__iexact='Pilar').first()
    if not source_branch:
        return

    target_branches = Branch.objects.filter(name__in=['Molino', 'Queensrow'])
    source_products = Product.objects.filter(branch=source_branch)

    for target_branch in target_branches:
        for source in source_products:
            # Idempotency: prefer SKU identity when available; otherwise use a stable field tuple.
            if source.sku:
                exists = Product.objects.filter(
                    branch=target_branch,
                    sku=source.sku,
                ).exists()
            else:
                exists = Product.objects.filter(
                    branch=target_branch,
                    name=source.name,
                    item_type=source.item_type,
                    manufacturer=source.manufacturer,
                    unit_cost=source.unit_cost,
                    price=source.price,
                ).exists()

            if exists:
                continue

            Product.objects.create(
                name=source.name,
                description=source.description,
                item_type=source.item_type,
                sku=source.sku,
                barcode=source.barcode,
                manufacturer=source.manufacturer,
                unit_cost=source.unit_cost,
                price=source.price,
                branch=target_branch,
                is_available=source.is_available,
                stock_quantity=source.stock_quantity,
                min_stock_level=source.min_stock_level,
                is_consumable=source.is_consumable,
                expiration_date=source.expiration_date,
                is_deleted=source.is_deleted,
                deleted_at=source.deleted_at,
            )


def noop_reverse(apps, schema_editor):
    # Intentionally no reverse operation: this is a one-time baseline seeding.
    return


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0016_alter_stockadjustment_adjustment_type_and_more'),
        ('branches', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(clone_pilar_inventory, noop_reverse),
    ]
