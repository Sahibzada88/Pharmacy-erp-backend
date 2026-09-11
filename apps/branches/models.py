from django.db import models


class Branch(models.Model):
    """A single pharmacy location within the chain."""
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=20, unique=True, help_text="Short branch code, e.g. LHR-01")
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    license_number = models.CharField(max_length=100, blank=True, help_text="Drug license / registration no.")
    is_active = models.BooleanField(default=True)
    opened_on = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'branches_branch'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"
