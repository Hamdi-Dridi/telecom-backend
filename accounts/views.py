from rest_framework import generics, serializers as drf_serializers, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Role, User
from .permissions import IsAdmin
from .serializers import (
    CreateUserDirectSerializer, LoginSerializer, RoleSerializer, SignupSerializer, UserSerializer,
)


class SignupView(generics.CreateAPIView):
    serializer_class = SignupSerializer
    permission_classes = [AllowAny]


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        password = serializer.validated_data['password']

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return Response({'detail': 'E-mail ou mot de passe incorrect.'}, status=status.HTTP_400_BAD_REQUEST)

        if not user.check_password(password):
            return Response({'detail': 'E-mail ou mot de passe incorrect.'}, status=status.HTTP_400_BAD_REQUEST)
        if user.status == User.Status.PENDING:
            return Response(
                {'detail': "Votre compte est en attente d'approbation par un administrateur.", 'reason': 'pending'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if user.status == User.Status.SUSPENDED:
            return Response(
                {'detail': 'Votre compte a été suspendu. Contactez un administrateur.', 'reason': 'suspended'},
                status=status.HTTP_403_FORBIDDEN,
            )

        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key, 'user': UserSerializer(user).data})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        password = request.data.get('password')
        if password:
            if len(password) < 6:
                raise drf_serializers.ValidationError({'password': 'Le mot de passe doit contenir au moins 6 caractères.'})
            request.user.set_password(password)
            request.user.save()
        return Response(UserSerializer(request.user).data)


class RoleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer


class UserViewSet(viewsets.ModelViewSet):
    """Admin-only CRUD, plus the approve/reject/toggle_suspend workflow
    actions that mirror the frontend's Utilisateurs page exactly."""
    queryset = User.objects.all().order_by('-created_at')
    serializer_class = UserSerializer
    permission_classes = [IsAdmin]

    def get_serializer_class(self):
        if self.action == 'create':
            return CreateUserDirectSerializer
        return UserSerializer

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        user = self.get_object()
        role_key = request.data.get('role', 'manager')
        try:
            role = Role.objects.get(key=role_key)
        except Role.DoesNotExist:
            return Response({'detail': 'Rôle inconnu.'}, status=400)
        user.status = User.Status.ACTIVE
        user.role = role
        user.save()
        return Response(UserSerializer(user).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        user = self.get_object()
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def toggle_suspend(self, request, pk=None):
        user = self.get_object()
        if user.role_key == 'admin':
            return Response({'detail': 'Les administrateurs ne peuvent pas être suspendus.'}, status=400)
        if user == request.user:
            return Response({'detail': 'Vous ne pouvez pas suspendre votre propre compte.'}, status=400)
        user.status = User.Status.SUSPENDED if user.status == User.Status.ACTIVE else User.Status.ACTIVE
        user.save()
        return Response(UserSerializer(user).data)

    def perform_update(self, serializer):
        instance = self.get_object()
        was_admin = instance.role_key == 'admin'
        user = serializer.save()
        if was_admin and user.role_key != 'admin':
            remaining_admins = User.objects.filter(role__key='admin', status='active').exclude(pk=user.pk).count()
            if remaining_admins == 0:
                admin_role = Role.objects.get(key='admin')
                user.role = admin_role
                user.save()
                raise drf_serializers.ValidationError("Impossible de retirer le rôle du dernier administrateur.")
        if user.role_key == 'admin' and user.status == User.Status.SUSPENDED:
            user.status = User.Status.ACTIVE
            user.save()

    def perform_destroy(self, instance):
        if instance == self.request.user:
            raise drf_serializers.ValidationError('Vous ne pouvez pas supprimer votre propre compte.')
        if instance.role_key == 'admin':
            active_admins = User.objects.filter(role__key='admin', status='active').count()
            if active_admins <= 1:
                raise drf_serializers.ValidationError("Impossible de supprimer le dernier administrateur actif.")
        instance.delete()
