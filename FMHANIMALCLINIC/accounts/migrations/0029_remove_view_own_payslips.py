from django.db import migrations


def delete_view_own_payslips_permission(apps, schema_editor):
    SpecialPermission = apps.get_model('accounts', 'SpecialPermission')
    RoleSpecialPermission = apps.get_model('accounts', 'RoleSpecialPermission')

    try:
        permission = SpecialPermission.objects.get(code='can_view_own_payslips')
    except SpecialPermission.DoesNotExist:
        return

    RoleSpecialPermission.objects.filter(permission=permission).delete()
    permission.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0028_add_manage_others_schedule_special_permission'),
    ]

    operations = [
        migrations.RunPython(delete_view_own_payslips_permission, reverse_code=migrations.RunPython.noop),
    ]
