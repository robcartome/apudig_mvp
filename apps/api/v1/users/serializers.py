from rest_framework import serializers


class AuthUserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    name = serializers.CharField()


class AuthCompanySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    store_id = serializers.UUIDField(allow_null=True)
    store_name = serializers.CharField(allow_null=True)
    roles = serializers.ListField(child=serializers.CharField(), required=False)
    permissions = serializers.ListField(child=serializers.CharField(), required=False)


class AuthCompanyListItemSerializer(serializers.Serializer):
    company_id = serializers.UUIDField()
    company_name = serializers.CharField()
    store_id = serializers.UUIDField(allow_null=True)
    store_name = serializers.CharField(allow_null=True)
    roles = serializers.ListField(child=serializers.CharField(), required=False)
    permissions = serializers.ListField(child=serializers.CharField(), required=False)


class TokenObtainRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)


class TokenObtainResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    access_token = serializers.CharField(required=False)
    refresh_token = serializers.CharField(required=False)
    user = AuthUserSerializer()
    company = AuthCompanySerializer(allow_null=True)
    companies = AuthCompanyListItemSerializer(many=True, required=False)


class TokenRefreshRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(required=False, allow_blank=True)
    refresh_token = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        refresh = attrs.get("refresh") or attrs.get("refresh_token")
        if not refresh:
            raise serializers.ValidationError({"detail": "refresh es requerido."})
        attrs["refresh"] = refresh
        return attrs


class TokenRefreshResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    access_token = serializers.CharField(required=False)


class SelectCompanyRequestSerializer(serializers.Serializer):
    company_id = serializers.UUIDField()


class SelectCompanyResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    access_token = serializers.CharField(required=False)


class MyCompaniesResponseSerializer(serializers.Serializer):
    companies = AuthCompanyListItemSerializer(many=True)


class LogoutRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(required=False, allow_blank=True)
    refresh_token = serializers.CharField(required=False, allow_blank=True)


class RegisterUserRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)
    name = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)


class CreateRoleRequestSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)


class CreatePermissionRequestSerializer(serializers.Serializer):
    code = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)


class AssignRoleRequestSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    role_id = serializers.UUIDField()
    company_id = serializers.UUIDField()
