from django.contrib import admin

from .models import Role, User


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ['key', 'name']


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ['email', 'first_name', 'last_name', 'role', 'status', 'region']
    list_filter = ['role', 'status', 'region']
    search_fields = ['email', 'first_name', 'last_name']
