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


class DiseaseDetailedPrediction(models.Model):
    """Stores comprehensive AI-generated disease predictions with specific animal-focused details."""

    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='disease_predictions')
    disease_name = models.CharField(max_length=150)
    confidence = models.FloatField(default=0.0)
    case_count = models.PositiveIntegerField(default=1)
    
    # Disease Breakdown - Specific Examples
    disease_breakdown = models.TextField(blank=True, help_text="Main disease description for animals")
    specific_examples = models.TextField(blank=True, help_text="JSON list of 5 specific disease examples")
    
    # Prevention & Guidance
    prevention_guidance = models.TextField(blank=True, help_text="Animal-specific prevention and care guidance")
    
    # Recommended Actions
    recommended_actions = models.TextField(blank=True, help_text="Clinical and operational actions for clinic staff")
    
    # Clinical Summary
    clinical_summary = models.TextField(blank=True, help_text="Specific clinical presentation in animals")
    suggested_investigations = models.TextField(blank=True, help_text="Diagnostic tests and investigations")
    
    # Location & Timeframe
    location_branch = models.CharField(max_length=120, blank=True)
    time_period_start = models.DateField(null=True, blank=True)
    time_period_end = models.DateField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Disease Detailed Prediction'
        verbose_name_plural = 'Disease Detailed Predictions'

    def __str__(self):
        return f'{self.disease_name} @ {self.location_branch}'
