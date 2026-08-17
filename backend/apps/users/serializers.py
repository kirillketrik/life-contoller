from rest_framework import serializers

from apps.core.permissions import PermissionService

from .models import User


class UserSerializer(serializers.ModelSerializer):
    is_admin = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "is_admin"]

    def get_is_admin(self, obj) -> bool:
        return PermissionService.is_admin(obj)
