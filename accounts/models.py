from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class Role(models.Model):
    KEY_CHOICES = [
        ('admin', 'Administrateur'),
        ('manager', 'Regional Manager'),
        ('viewer', 'Viewer'),
    ]
    key = models.CharField(max_length=20, choices=KEY_CHOICES, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    permissions = models.JSONField(default=list, blank=True)

    def __str__(self):
        return self.name


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Un e-mail est requis.')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('status', User.Status.ACTIVE)
        extra_fields.setdefault('first_name', extra_fields.get('first_name', 'Admin'))
        extra_fields.setdefault('last_name', extra_fields.get('last_name', 'Système'))
        role, _ = Role.objects.get_or_create(key='admin', defaults={'name': 'Administrateur'})
        extra_fields.setdefault('role', role)
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    class Status(models.TextChoices):
        PENDING = 'pending', 'En attente'
        ACTIVE = 'active', 'Actif'
        SUSPENDED = 'suspended', 'Suspendu'

    username = None
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name='users', null=True)
    region = models.ForeignKey(
        'kpi.Region', on_delete=models.SET_NULL, null=True, blank=True, related_name='users'
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    objects = UserManager()

    def __str__(self):
        return f'{self.first_name} {self.last_name} <{self.email}>'

    @property
    def role_key(self):
        return self.role.key if self.role else None
