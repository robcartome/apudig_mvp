from django.urls import path

from .views import (
    CurrentWebsiteAPIView, WebsiteDraftAPIView, WebsiteEditorAPIView,
    WebsiteMediaAPIView, WebsiteMediaDetailAPIView, WebsitePreviewAPIView,
    WebsitePublishAPIView, WebsiteRestoreAPIView, WebsiteRevisionsAPIView,
)


urlpatterns = [
    path("websites/current/", CurrentWebsiteAPIView.as_view(), name="api_v1_current_website"),
    path("websites/<uuid:website_id>/editor/", WebsiteEditorAPIView.as_view(), name="api_v1_website_editor"),
    path("websites/<uuid:website_id>/draft/", WebsiteDraftAPIView.as_view(), name="api_v1_website_draft"),
    path("websites/<uuid:website_id>/publish/", WebsitePublishAPIView.as_view(), name="api_v1_website_publish"),
    path("websites/<uuid:website_id>/revisions/", WebsiteRevisionsAPIView.as_view(), name="api_v1_website_revisions"),
    path("websites/<uuid:website_id>/restore/", WebsiteRestoreAPIView.as_view(), name="api_v1_website_restore"),
    path("websites/<uuid:website_id>/preview/", WebsitePreviewAPIView.as_view(), name="api_v1_website_preview"),
    path("websites/<uuid:website_id>/media/", WebsiteMediaAPIView.as_view(), name="api_v1_website_media"),
    path("websites/<uuid:website_id>/media/<uuid:media_id>/", WebsiteMediaDetailAPIView.as_view(), name="api_v1_website_media_detail"),
]
