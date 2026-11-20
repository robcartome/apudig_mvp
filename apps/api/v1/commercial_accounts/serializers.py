from rest_framework import serializers
from apps.api.v1.websites.serializers import StrictSerializer


class CommercialTokenSerializer(serializers.Serializer):
    context = serializers.CharField(default="commercial", help_text="Always commercial; does not grant ERP access.")
    websiteId = serializers.UUIDField()
    access = serializers.CharField()
    access_token = serializers.CharField()
    refresh = serializers.CharField(required=False)
    refresh_token = serializers.CharField(required=False)


class CommercialUserSerializer(serializers.Serializer):
    name = serializers.CharField()
    email = serializers.EmailField()
    phone = serializers.CharField(required=False, allow_blank=True)


class CommercialProfileSerializer(serializers.Serializer):
    context = serializers.CharField(default="commercial")
    websiteId = serializers.UUIDField()
    accountId = serializers.UUIDField(help_text="Own account identifier for isolated cart storage; never an authorization input.")
    company = serializers.DictField(child=serializers.CharField())
    user = CommercialUserSerializer()
    contactVerified = serializers.BooleanField()
    verificationChannel = serializers.ChoiceField(choices=("email",))
    wholesaleApproved = serializers.BooleanField()
    capabilities = serializers.DictField(child=serializers.BooleanField())


class AdministrativeAccountSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    etag = serializers.CharField()
    user = CommercialUserSerializer()
    customer = serializers.DictField()
    contactVerified = serializers.BooleanField()
    wholesaleApproved = serializers.BooleanField()
    priceList = serializers.DictField(allow_null=True)


class AdministrativeAccountsPageSerializer(serializers.Serializer):
    websiteId = serializers.UUIDField()
    count = serializers.IntegerField()
    limit = serializers.IntegerField()
    offset = serializers.IntegerField()
    results = AdministrativeAccountSerializer(many=True)


class WholesaleApprovalSerializer(StrictSerializer):
    wholesaleApproved = serializers.BooleanField()

    def validate_wholesaleApproved(self, value):
        if type(self.initial_data.get("wholesaleApproved")) is not bool:
            raise serializers.ValidationError("Usa true o false.")
        return value
