from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_existing_appointments(apps, schema_editor):
    Appointment = apps.get_model('appointments', 'Appointment')
    AppointmentHistory = apps.get_model('appointments', 'AppointmentHistory')
    database = schema_editor.connection.alias

    for appointment in Appointment.objects.using(database).only(
        'pk', 'created_at',
    ).iterator(chunk_size=500):
        entry = AppointmentHistory.objects.using(database).create(
            appointment_id=appointment.pk,
            event_type='BOOKED',
            summary='Appointment booked',
            changes=[],
            owner_visible=True,
        )
        AppointmentHistory.objects.using(database).filter(
            pk=entry.pk,
        ).update(created_at=appointment.created_at)


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0018_appointment_cancellation_reason_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AppointmentHistory',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'event_type',
                    models.CharField(
                        choices=[
                            ('BOOKED', 'Booked'),
                            ('STATUS_CHANGED', 'Status changed'),
                            ('UPDATED', 'Updated'),
                        ],
                        max_length=20,
                    ),
                ),
                ('summary', models.CharField(max_length=200)),
                ('changes', models.JSONField(blank=True, default=list)),
                ('owner_visible', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'actor',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='appointment_history_entries',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'appointment',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='history_entries',
                        to='appointments.appointment',
                    ),
                ),
            ],
            options={
                'ordering': ['-created_at', '-pk'],
                'indexes': [
                    models.Index(
                        fields=['appointment', '-created_at'],
                        name='appointmen_appoint_7ad0bd_idx',
                    ),
                    models.Index(
                        fields=['owner_visible', '-created_at'],
                        name='appointmen_owner_v_00c4f7_idx',
                    ),
                ],
            },
        ),
        migrations.RunPython(
            seed_existing_appointments,
            migrations.RunPython.noop,
        ),
    ]
