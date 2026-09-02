
"""
Reports app models.

This app generates reports from data stored in other apps' models.
Reports are dynamically generated using QuerySets and aggregations
rather than storing report data in separate models.

Report generation logic is handled in views and utility functions.
"""
from django.conf import settings
from django.db import models


class ScheduledReport(models.Model):
	"""A recurring emailed report definition."""
	class Frequency(models.TextChoices):
		DAILY = 'DAILY', 'Daily'
		WEEKLY = 'WEEKLY', 'Weekly'
		MONTHLY = 'MONTHLY', 'Monthly'

	name = models.CharField(max_length=150)
	frequency = models.CharField(max_length=10, choices=Frequency.choices, default=Frequency.MONTHLY)
	recipients = models.TextField(help_text='Comma-separated email addresses.')
	branch = models.ForeignKey('branches.Branch', on_delete=models.SET_NULL, null=True, blank=True)
	is_active = models.BooleanField(default=True)
	next_run_at = models.DateTimeField()
	last_run_at = models.DateTimeField(null=True, blank=True)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
	created_at = models.DateTimeField(auto_now_add=True)


class ScheduledReportDelivery(models.Model):
	"""Audit record for each scheduled report attempt."""
	report = models.ForeignKey(ScheduledReport, on_delete=models.CASCADE, related_name='deliveries')
	period_key = models.CharField(max_length=30)
	recipients = models.TextField()
	status = models.CharField(max_length=20, choices=[('SENT', 'Sent'), ('FAILED', 'Failed')])
	error_message = models.TextField(blank=True)
	sent_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		constraints = [models.UniqueConstraint(fields=['report', 'period_key'], name='unique_report_period_delivery')]
