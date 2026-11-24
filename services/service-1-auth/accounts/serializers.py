from rest_framework import serializers
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
import secrets
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from datetime import timedelta
from django.db.models import F
from rest_framework import serializers
from django.contrib.auth import authenticate



class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs["email"].lower()
        password = attrs["password"]

        User = get_user_model()

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError(
                "Invalid email or password."
            )

        now = timezone.now()

        # Check whether the account is temporarily locked
        if user.locked_until and user.locked_until > now:
            raise serializers.ValidationError(
                "Account temporarily locked. Try again later."
            )

        # Clear an expired lock
        if user.locked_until and user.locked_until <= now:
            user.locked_until = None
            user.failed_login_attempts = 0
            user.save(update_fields=[
                "locked_until",
                "failed_login_attempts"
            ])

        authenticated_user = authenticate(
            request=self.context.get("request"),
            email=email,
            password=password
        )

        if not authenticated_user:
            user.failed_login_attempts += 1

            if user.failed_login_attempts >= 5:
                user.locked_until = now + timedelta(minutes=15)

            user.save(update_fields=[
                "failed_login_attempts",
                "locked_until"
            ])

            if user.locked_until:
                raise serializers.ValidationError(
                    "Too many failed attempts. Account locked for 15 minutes."
                )

            raise serializers.ValidationError(
                "Invalid email or password."
            )

        if not authenticated_user.is_active:
            raise serializers.ValidationError(
                "This account is inactive."
            )

        # Reset failed attempts after successful authentication
        authenticated_user.failed_login_attempts = 0
        authenticated_user.locked_until = None
        authenticated_user.save(update_fields=[
            "failed_login_attempts",
            "locked_until"
        ])

        attrs["user"] = authenticated_user
        return attrs



class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def validate(self, attrs):
        try:
            token = RefreshToken(attrs["refresh"])

            # Ensure the token belongs to the logged-in user
            if str(token["user_id"]) != str(self.context["request"].user.id):
                raise serializers.ValidationError(
                    {"refresh": "This token does not belong to the logged-in user."}
                )

            self.token = token

        except TokenError:
            raise serializers.ValidationError(
                {"refresh": "Invalid or expired refresh token."}
            )

        return attrs

    def save(self, **kwargs):
        self.token.blacklist()



User = get_user_model()


class AdminCreateUserSerializer(serializers.ModelSerializer):

    role = serializers.ChoiceField(
        choices=[
            ("STUDENT", "Student"),
            ("TEACHER", "Teacher"),
        ]
    )

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "role",
        ]
        read_only_fields = ["id"]

    def create(self, validated_data):
        # Generate a temporary password
        temporary_password = secrets.token_urlsafe(10)

        user = User.objects.create_user(
            password=temporary_password,
            must_change_password=True,
            **validated_data
        )

        # Keep it temporarily so the view can return it to the admin
        self.temporary_password = temporary_password

        return user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(
        write_only=True,
        validators=[validate_password]
    )
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = self.context["request"].user

        if not user.check_password(attrs["old_password"]):
            raise serializers.ValidationError({
                "old_password": "Current password is incorrect."
            })

        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({
                "confirm_password": "Passwords do not match."
            })

        if attrs["old_password"] == attrs["new_password"]:
            raise serializers.ValidationError({
                "new_password": "New password must be different."
            })

        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password"])
        return user
