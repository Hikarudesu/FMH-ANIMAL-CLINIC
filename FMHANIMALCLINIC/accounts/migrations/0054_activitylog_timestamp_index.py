from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0053_remove_otptoken_accounts_ot_otp_cod_858793_idx_and_more'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='activitylog',
            index=models.Index(fields=['-timestamp'], name='acct_actlog_ts_desc_idx'),
        ),
    ]