
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    CollectionAssignment, CollectionRequest, Complaint,
    Location, Payment, ServicePackage, User, WasteType,
)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('TakaSmart details', {'fields': ('role', 'phone_number')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('TakaSmart details', {'fields': ('role', 'phone_number')}),
    )
    list_display = ('username', 'email', 'role', 'phone_number', 'is_active')
    list_filter = ('role', 'is_active')


admin.site.register(WasteType)
admin.site.register(ServicePackage)
admin.site.register(Location)
admin.site.register(CollectionRequest)
admin.site.register(CollectionAssignment)
admin.site.register(Payment)
admin.site.register(Complaint)