from django.db import models

from branches.models import Branch
from patients.models import Pet


class DiseaseGeoMappingInsight(models.Model):
    """Stores AI-assisted geo-disease trend insights derived from branch data."""

    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='disease_geo_insights')
    pet = models.ForeignKey(Pet, on_delete=models.SET_NULL, null=True, blank=True, related_name='disease_geo_insights')
    disease = models.CharField(max_length=120)
    location = models.CharField(max_length=120)
    case_count = models.PositiveIntegerField(default=1)
    trend_score = models.FloatField(default=0.0)
    seasonality = models.CharField(max_length=80, blank=True)
    summary = models.TextField(blank=True)
    confidence = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Disease Geo Mapping Insight'
        verbose_name_plural = 'Disease Geo Mapping Insights'

    def __str__(self):
        return f'{self.disease} @ {self.branch.name}'
