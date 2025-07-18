from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from workspaces.models import Workspace

from users.models import Invite, User


class UserSerializer(serializers.ModelSerializer):
    currency = serializers.CharField(source="currency_code")
    role = serializers.CharField()

    class Meta:
        model = User
        fields = (
            "uuid",
            "username",
            "email",
            "currency",
            "role",
            "first_name",
            "last_name",
            "is_staff",
            "is_active",
            "date_joined",
        )


class UserLoginSerializer(serializers.Serializer):
    email = serializers.CharField()
    password = serializers.CharField()


class ChangeDefaultCurrencySerializer(serializers.Serializer):
    currency = serializers.CharField()


class ChangeUserRoleSerializer(serializers.Serializer):
    role = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField()


class InviteRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invite
        fields = "__all__"


class InviteSeriazlier(serializers.ModelSerializer):
    class Meta:
        model = Invite
        fields = (
            "invite_reciever",
            "invite_owner",
            "workspace",
            "is_accepted",
        )


class RegisterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        required=True, validators=[UniqueValidator(queryset=User.objects.all())]
    )

    password = serializers.CharField(
        write_only=True, required=True, validators=[validate_password]
    )
    repeat_password = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = (
            "username",
            "password",
            "repeat_password",
            "email",
            "first_name",
            "last_name",
        )

    def validate(self, attrs):
        if attrs["password"] != attrs["repeat_password"]:
            raise serializers.ValidationError(
                {"password": "Password fields didn't match."}
            )

        return attrs

    def create(self, validated_data):
        user = User.objects.create(
            username=validated_data.get("username"),
            email=validated_data["email"],
            first_name=validated_data.get("first_name"),
            last_name=validated_data.get("last_name"),
        )

        user.set_password(validated_data["password"])
        user.save()

        workspace = Workspace.objects.create(
            name="default",
            owner=user,
        )

        user.active_workspace = workspace
        user.save()

        workspace.members.add(user)
        workspace.save()

        return user
