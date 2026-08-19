from rest_framework import serializers

from kpi.models import Region
from .models import Role, User


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['id', 'key', 'name', 'description', 'permissions']


class UserSerializer(serializers.ModelSerializer):
    role = serializers.SlugRelatedField(slug_field='key', queryset=Role.objects.all())
    region = serializers.SlugRelatedField(
        slug_field='name', queryset=Region.objects.all(), allow_null=True, required=False
    )
    role_label = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email', 'role', 'role_label', 'region', 'status', 'created_at']
        read_only_fields = ['id', 'status', 'created_at']

    def get_role_label(self, obj):
        labels = {'admin': 'Administrateur', 'manager': 'Manager', 'viewer': 'Viewer'}
        return labels.get(obj.role_key, obj.role_key)


class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    region = serializers.SlugRelatedField(slug_field='name', queryset=Region.objects.all())

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'password', 'region']

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('Un compte existe déjà avec cet e-mail.')
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        manager_role, _ = Role.objects.get_or_create(key='manager', defaults={'name': 'Regional Manager'})
        user = User(status=User.Status.PENDING, role=manager_role, **validated_data)
        user.set_password(password)
        user.save()
        return user


class CreateUserDirectSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    role = serializers.SlugRelatedField(slug_field='key', queryset=Role.objects.all())
    region = serializers.SlugRelatedField(slug_field='name', queryset=Region.objects.all())

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'password', 'role', 'region']

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('Un compte existe déjà avec cet e-mail.')
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(status=User.Status.ACTIVE, **validated_data)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
