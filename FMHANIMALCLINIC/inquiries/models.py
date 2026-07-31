from django.db import models
from django.conf import settings
from branches.models import Branch


class Inquiry(models.Model):
    """
    Stores contact inquiries submitted via the landing page contact form.
    """
    
    STATUS_CHOICES = [
        ('NEW', 'New'),
        ('READ', 'Read'),
        ('RESPONDED', 'Responded'),
        ('ARCHIVED', 'Archived'),
    ]
    
    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('NORMAL', 'Normal'),
        ('HIGH', 'High'),
        ('URGENT', 'Urgent'),
    ]
    
    # Contact Information
    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    branch = models.ForeignKey(
        Branch, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='inquiries'
    )
    
    # Inquiry Content
    message = models.TextField()
    
    # Status & Priority
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='NEW',
        db_index=True
    )
    priority = models.CharField(
        max_length=20, 
        choices=PRIORITY_CHOICES, 
        default='NORMAL'
    )
    
    # Response Tracking
    responded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='inquiry_responses'
    )
    response = models.TextField(blank=True)
    response_date = models.DateTimeField(null=True, blank=True)
    
    # Internal Notes
    internal_notes = models.TextField(
        blank=True, 
        help_text='Internal notes (not visible to customer)'
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Inquiry'
        verbose_name_plural = 'Inquiries'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['branch', 'status']),
        ]
    
    def __str__(self):
        return f"Inquiry from {self.full_name} - {self.created_at.strftime('%Y-%m-%d')}"
    
    @property
    def is_new(self):
        return self.status == 'NEW'
    
    @property
    def is_responded(self):
        return self.status == 'RESPONDED'
