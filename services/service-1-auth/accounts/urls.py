from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import LoginView, MeView
from .views import LoginView, MeView, LogoutView
from .views import (
    LoginView,
    MeView,
    LogoutView,
    AdminCreateUserView,
)
from .views import (
    LoginView,
    MeView,
    LogoutView,
    AdminCreateUserView,
    ChangePasswordView,
)




urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('me/', MeView.as_view(), name='me'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('users/create/', AdminCreateUserView.as_view(), name='admin_create_user'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
]