from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user with a role. Each non-owner user is tied to one branch.
    Owner can see/manage all branches (chain-wide).
    """

    class Role(models.TextChoices):
        OWNER = 'OWNER', 'Owner'
        MANAGER = 'MANAGER', 'Branch Manager'
        CASHIER = 'CASHIER', 'Cashier'
        ACCOUNTANT = 'ACCOUNTANT', 'Accountant'
        PHARMACIST = 'PHARMACIST', 'Pharmacist'

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CASHIER)
    branch = models.ForeignKey(
        'branches.Branch', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='staff',
        help_text="Home branch for this staff member. Not required for OWNER."
    )
    phone = models.CharField(max_length=20, blank=True)
    cnic = models.CharField(max_length=20, blank=True, help_text="National ID, for HR/audit purposes")
    is_active_staff = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'accounts_user'
        indexes = [
            models.Index(fields=['role']),
            models.Index(fields=['branch']),
        ]

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.role})"

    @property
    def is_owner(self):
        return self.role == self.Role.OWNER

    @property
    def is_manager(self):
        return self.role == self.Role.MANAGER

    @property
    def is_cashier(self):
        return self.role == self.Role.CASHIER

    @property
    def is_accountant(self):
        return self.role == self.Role.ACCOUNTANT

    @property
    def is_pharmacist(self):
        return self.role == self.Role.PHARMACIST
