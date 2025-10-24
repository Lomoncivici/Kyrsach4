from rest_framework.permissions import BasePermission, SAFE_METHODS

def _in_group(user, name: str) -> bool:
    return user.is_authenticated and user.groups.filter(name=name).exists()

class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_superuser or _in_group(request.user, "admin")

class IsSupport(BasePermission):
    def has_permission(self, request, view):
        return _in_group(request.user, "support") or IsAdmin().has_permission(request, view)

class IsFinance(BasePermission):
    def has_permission(self, request, view):
        return _in_group(request.user, "finance") or IsAdmin().has_permission(request, view)

class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS