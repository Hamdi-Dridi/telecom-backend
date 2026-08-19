from rest_framework.routers import DefaultRouter

from django.urls import path

from .views import LoginView, LogoutView, MeView, RoleViewSet, SignupView, UserViewSet

router = DefaultRouter()
router.register('users', UserViewSet, basename='user')
router.register('roles', RoleViewSet, basename='role')

urlpatterns = [
    path('auth/signup/', SignupView.as_view()),
    path('auth/login/', LoginView.as_view()),
    path('auth/logout/', LogoutView.as_view()),
    path('auth/me/', MeView.as_view()),
] + router.urls
