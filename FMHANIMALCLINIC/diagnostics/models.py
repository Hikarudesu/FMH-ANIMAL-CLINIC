from django.db import models
from patients.models import Pet
from employees.models import StaffMember


class AIDiagnosis(models.Model):
    """
    Stores AI-generated diagnostic suggestions for a pet.

    Vet-in-the-Loop Workflow:
      Phase A: Symptom intake + AI generation
      Phase B: Vet reviews results, selects condition/tests, enters Rx
      Phase C: Create RecordEntry with selected data, trigger signals
    """

    pet = models.ForeignKey(
        Pet,
        on_delete=models.CASCADE,
        related_name='ai_diagnoses'
    )
    requested_by = models.ForeignKey(
        StaffMember,
        on_delete=models.SET_NULL,
        null=True,
        related_name='requested_diagnoses'
    )

    # Input data snapshot
    input_symptoms = models.TextField(
        help_text="Current symptoms provided for analysis",
        blank=True
    )
    input_history = models.TextField(
        help_text="Medical history snapshot (last 10 entries)",
        blank=True
    )

    # AI Response - Primary Diagnosis
    primary_condition = models.CharField(max_length=200)
    primary_reasoning = models.TextField(blank=True)

    # AI Response - Selectable Lists (JSON)
    differential_diagnoses = models.JSONField(
        default=list,
        help_text="List of {condition, reasoning} for vet selection"
    )
    recommended_tests = models.JSONField(
        default=list,
        help_text="List of recommended tests for vet selection"
    )
    warning_signs = models.JSONField(default=list)
    summary = models.TextField(blank=True)

    # Raw response for debugging (optional)
    raw_response = models.JSONField(null=True, blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)

    # === Vet Review Fields ===
    is_reviewed = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        StaffMember,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_diagnoses'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    # Vet's selections during review
    selected_condition = models.CharField(
        max_length=200,
        blank=True,
        help_text="The condition selected by vet (primary or differential)"
    )
    selected_tests = models.JSONField(
        default=list,
        help_text="Tests selected by vet for the treatment plan"
    )
    vet_prescription = models.TextField(
        blank=True,
        help_text="Rx entered by vet during review"
    )
    diagnosis_notes = models.TextField(
        blank=True,
        help_text="Extra details about the selected diagnosis (vet notes)"
    )
    test_notes = models.TextField(
        blank=True,
        help_text="Extra details about the selected tests (vet notes)"
    )

    # Link to created medical record entry
    linked_record_entry = models.ForeignKey(
        'records.RecordEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ai_diagnoses',
        help_text="RecordEntry created from this diagnosis"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'AI Diagnosis'
        verbose_name_plural = 'AI Diagnoses'

    def __str__(self):
        return f"{self.pet.name} - {self.primary_condition} ({self.created_at.date()})"

    def get_all_conditions(self):
        """Return all selectable conditions (primary + differentials)."""
        conditions = [
            {'condition': self.primary_condition, 'reasoning': self.primary_reasoning, 'is_primary': True}
        ]
        for diff in self.differential_diagnoses:
            conditions.append({
                'condition': diff.get('condition', ''),
                'reasoning': diff.get('reasoning', ''),
                'is_primary': False
            })
        return conditions
