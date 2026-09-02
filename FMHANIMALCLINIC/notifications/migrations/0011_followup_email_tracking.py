from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('notifications', '0010_alter_notification_notification_type')]

    operations = [
        migrations.AddField(model_name='followup', name='email_sent_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='followup', name='email_attempts', field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='followup', name='email_last_error', field=models.TextField(blank=True)),
    ]