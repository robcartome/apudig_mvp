from rest_framework import serializers


class WebsiteCapabilitiesSerializer(serializers.Serializer):
    view = serializers.BooleanField()
    edit = serializers.BooleanField()
    publish = serializers.BooleanField()
    mediaUpload = serializers.BooleanField()
    domains = serializers.BooleanField()
    realPublication = serializers.BooleanField()


class CurrentWebsiteSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    companyId = serializers.UUIDField(source="company_id")
    templateKey = serializers.CharField(source="template_key")
    documentSchemaVersion = serializers.IntegerField()
    revision = serializers.IntegerField(source="editorial_revision")
    capabilities = WebsiteCapabilitiesSerializer()


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError({key: "Campo no permitido." for key in set(data) - set(self.fields)})
        return super().to_internal_value(data)


class SaveDraftSerializer(StrictSerializer):
    document = serializers.JSONField()
    mediaReferences = serializers.DictField(child=serializers.UUIDField(), required=False)


class RestoreRevisionSerializer(StrictSerializer):
    revisionId = serializers.UUIDField()


class UploadMediaSerializer(StrictSerializer):
    file = serializers.FileField()
    kind = serializers.ChoiceField(choices=("IMAGE", "LOGO", "FAVICON", "BANNER", "PROMOTION", "SECTION"), default="IMAGE")
    altText = serializers.CharField(max_length=180, required=False, default="", allow_blank=True)


class WebsiteMediaSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    websiteId = serializers.UUIDField(source="website_id")
    url = serializers.CharField()
    thumbnailUrl = serializers.CharField(source="thumbnail_url")
    mimeType = serializers.CharField(source="mime_type")
    size = serializers.IntegerField()
    width = serializers.IntegerField()
    height = serializers.IntegerField()
    altText = serializers.CharField(source="alt_text")
    kind = serializers.CharField()


class EditorRecordSerializer(serializers.Serializer):
    schemaVersion = serializers.IntegerField()
    companyId = serializers.UUIDField()
    websiteId = serializers.UUIDField()
    revision = serializers.IntegerField()
    draft = serializers.JSONField()
    published = serializers.JSONField(allow_null=True)
    updatedAt = serializers.DateTimeField(allow_null=True)
    publishedAt = serializers.DateTimeField(allow_null=True)
    events = serializers.ListField(child=serializers.DictField())
    capabilities = WebsiteCapabilitiesSerializer()


class RevisionSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    version = serializers.IntegerField()
    editorialRevision = serializers.IntegerField(allow_null=True)
    operation = serializers.CharField()
    at = serializers.DateTimeField()
    actor = serializers.DictField(allow_null=True)
    sourceRevisionId = serializers.UUIDField(allow_null=True)


class RevisionsPageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    results = RevisionSummarySerializer(many=True)


class MediaPageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    results = WebsiteMediaSerializer(many=True)


class WebsitePreviewSerializer(serializers.Serializer):
    websiteId = serializers.UUIDField()
    revision = serializers.IntegerField()
    content = serializers.JSONField()


class PublicWebsiteContextSerializer(serializers.Serializer):
    websiteId = serializers.UUIDField()
    hostname = serializers.CharField()
    canonicalHostname = serializers.CharField()
    templateKey = serializers.CharField()
    locale = serializers.CharField()
    currency = serializers.CharField()
    revision = serializers.IntegerField()


class PublicWebsiteContentSerializer(PublicWebsiteContextSerializer):
    publishedAt = serializers.DateTimeField()
    commerceEnabled = serializers.BooleanField()
    content = serializers.JSONField()
