from django.db import migrations
from django.db.models import Q


def _find_branch(Branch, keyword):
    return Branch.objects.filter(
        Q(name__icontains=keyword) | Q(branch_code__icontains=keyword)
    ).first()


def clone_inventory_with_flexible_matching(apps, schema_editor):
    Branch = apps.get_model('branches', 'Branch')
    Product = apps.get_model('inventory', 'Product')

    source_branch = _find_branch(Branch, 'pilar')
    if not source_branch:
        return

    target_branches = []
    for keyword in ('molino', 'queensrow'):
        target_branch = _find_branch(Branch, keyword)
        if target_branch:
            target_branches.append(target_branch)

    source_products = Product.objects.filter(branch=source_branch)

    for target_branch in target_branches:
        for source in source_products:
            # Idempotency: use SKU when available, else a stable fallback tuple.
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
    return


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0017_clone_pilar_inventory_to_molino_queensrow'),
    ]

    operations = [
        migrations.RunPython(clone_inventory_with_flexible_matching, noop_reverse),
    ]
