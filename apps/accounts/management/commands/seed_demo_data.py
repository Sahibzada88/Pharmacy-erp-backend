"""
Seeds initial data so you can log in and test the API immediately after setup:
  - One branch (main pharmacy)
  - One OWNER user
  - One MANAGER, CASHIER, ACCOUNTANT, PHARMACIST user for that branch
  - A couple of expense categories

Usage:
    python manage.py seed_demo_data
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.branches.models import Branch
from apps.finance.models import ExpenseCategory

from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Seed the database with a demo branch, users for every role, and base lookup data."

    @transaction.atomic
    def handle(self, *args, **options):
        branch, created = Branch.objects.get_or_create(
            code='MAIN-01',
            defaults=dict(name='Main Pharmacy', city='Islamabad', address='Main Branch', is_active=True),
        )
        self.stdout.write(self.style.SUCCESS(f"Branch: {branch} ({'created' if created else 'exists'})"))

        demo_users = [
            dict(username='owner', role=User.Role.OWNER, branch=None,
                 first_name='Ali', last_name='Owner', password='Owner@12345'),
            dict(username='manager1', role=User.Role.MANAGER, branch=branch,
                 first_name='Sara', last_name='Manager', password='Manager@12345'),
            dict(username='cashier1', role=User.Role.CASHIER, branch=branch,
                 first_name='Bilal', last_name='Cashier', password='Cashier@12345'),
            dict(username='accountant1', role=User.Role.ACCOUNTANT, branch=branch,
                 first_name='Ayesha', last_name='Accountant', password='Accountant@12345'),
            dict(username='pharmacist1', role=User.Role.PHARMACIST, branch=branch,
                 first_name='Usman', last_name='Pharmacist', password='Pharmacist@12345'),
        ]

        for data in demo_users:
            password = data.pop('password')
            user, created = User.objects.get_or_create(
                username=data['username'],
                defaults={**data, 'is_staff': data['role'] == User.Role.OWNER},
            )
            if created:
                user.set_password(password)
                if data['role'] == User.Role.OWNER:
                    user.is_superuser = True
                    user.is_staff = True
                user.save()
                self.stdout.write(self.style.SUCCESS(f"User created: {user.username} / {password} (role={user.role})"))
            else:
                self.stdout.write(f"User exists: {user.username}")

        for cat_name in ['Rent', 'Utilities', 'Salaries', 'Transport', 'Misc']:
            ExpenseCategory.objects.get_or_create(name=cat_name)

        self.stdout.write(self.style.SUCCESS("\nDemo data seeded. Login credentials:"))
        self.stdout.write(self.style.WARNING(
            "\nowner / Owner@12345\nmanager1 / Manager@12345\ncashier1 / Cashier@12345\n"
            "accountant1 / Accountant@12345\npharmacist1 / Pharmacist@12345"
        ))
