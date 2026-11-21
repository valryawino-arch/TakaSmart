from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
# Create your models here.

class User(AbstractUser):
    """
    Custom user for TakaSmart Kenya.
    Inherits username, password, email, first_name, last_name, etc.
    from Django's AbstractUser and adds a role and a phone number.
    """

    class Role(models.TextChoices):
        RESIDENT = 'resident', 'Resident'
        COLLECTOR = 'collector', 'Waste Collector'
        OFFICER = 'officer', 'Waste Management Officer'
        ADMIN = 'admin', 'Administrator'

    # Accepts 07XXXXXXXX, 01XXXXXXXX, 2547XXXXXXXX, +2547XXXXXXXX (and 2541...)
    phone_validator = RegexValidator(
        regex=r'^(?:\+?254|0)[17]\d{8}$',
        message='Enter a valid Kenyan phone number, e.g. 0712345678.',
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.RESIDENT,
    )
    phone_number = models.CharField(
        max_length=15,
        validators=[phone_validator],
        blank=True,
    )

    def save(self, *args, **kwargs):
        # Superusers created with "createsuperuser" should be administrators
        if self.is_superuser:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)

    # Convenience checks used later in views and templates
    @property
    def is_resident(self):
        return self.role == self.Role.RESIDENT

    @property
    def is_collector(self):
        return self.role == self.Role.COLLECTOR

    @property
    def is_officer(self):
        return self.role == self.Role.OFFICER

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN

    def __str__(self):
        return f'{self.get_full_name() or self.username} ({self.get_role_display()})'

    

class WasteType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class ServicePackage(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('1.00'))],
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.name} (KES {self.price})'


class Location(models.Model):
    resident = models.ForeignKey(User, on_delete=models.CASCADE, related_name='locations')
    label = models.CharField(max_length=60)          # e.g. Home
    estate = models.CharField(max_length=120)
    street_address = models.CharField(max_length=200)
    landmark = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f'{self.label}: {self.estate}'


class CollectionRequest(models.Model):

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending review'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        ASSIGNED = 'assigned', 'Collector assigned'
        IN_PROGRESS = 'in_progress', 'In progress'
        COLLECTED = 'collected', 'Collected'

    resident = models.ForeignKey(User, on_delete=models.CASCADE, related_name='collection_requests')
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    package = models.ForeignKey(ServicePackage, on_delete=models.PROTECT)
    waste_type = models.ForeignKey(WasteType, on_delete=models.PROTECT)
    preferred_date = models.DateField()
    notes = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        # Copy the package price when the request is first created
        if not self.pk and self.amount == Decimal('0.00'):
            self.amount = self.package.price
        super().save(*args, **kwargs)

    @property
    def is_paid(self):
        return self.payments.filter(status='success').exists()

    def __str__(self):
        return f'Request #{self.pk} by {self.resident.username}'


class CollectionAssignment(models.Model):
    request = models.OneToOneField(CollectionRequest, on_delete=models.CASCADE, related_name='assignment')
    collector = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='assignments',
        limit_choices_to={'role': 'collector'},
    )
    scheduled_date = models.DateField()
    instructions = models.TextField(blank=True)
    assigned_at = models.DateTimeField(auto_now_add=True)

    # Filled in by the collector when the job is done
    completed_at = models.DateTimeField(null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    completion_notes = models.TextField(blank=True)

    def __str__(self):
        return f'Request #{self.request_id} -> {self.collector.username}'


class Payment(models.Model):

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SUCCESS = 'success', 'Successful'
        FAILED = 'failed', 'Failed'

    request = models.ForeignKey(CollectionRequest, on_delete=models.PROTECT, related_name='payments')
    resident = models.ForeignKey(User, on_delete=models.PROTECT, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    phone_number = models.CharField(max_length=12)    # format 2547XXXXXXXX
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    # Filled in by M-Pesa (Step 10)
    checkout_request_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    mpesa_receipt_number = models.CharField(max_length=30, unique=True, null=True, blank=True)
    result_description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Payment #{self.pk}: KES {self.amount} ({self.status})'


class Complaint(models.Model):

    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        RESOLVED = 'resolved', 'Resolved'

    resident = models.ForeignKey(User, on_delete=models.CASCADE, related_name='complaints')
    request = models.ForeignKey(CollectionRequest, on_delete=models.SET_NULL, null=True, blank=True)
    subject = models.CharField(max_length=150)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    response = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.subject