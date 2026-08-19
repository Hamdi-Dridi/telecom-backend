from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAdmin(BasePermission):
    """Full CRUD reserved for administrators."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role_key == 'admin')


class IsAdminOrReadOnly(BasePermission):
    """Read access is public — these are non-sensitive reference/lookup
    tables (region names, period labels, domain/group names, thresholds)
    and the public signup form needs the region list before any login has
    happened. Only admins can write."""
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated and request.user.role_key == 'admin')


class IsManagerOrAdmin(BasePermission):
    """KPI Results: Regional Managers and Admins can write; Viewers read-only."""
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role_key in ('admin', 'manager')
