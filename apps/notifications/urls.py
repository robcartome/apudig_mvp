from django.urls import path

from . import views


app_name = "notifications"

urlpatterns = [
    path("", views.notification_list, name="list"),
    path("dropdown/", views.notification_dropdown, name="dropdown"),
    path("unread-count/", views.notification_unread_count, name="unread_count"),
    path("<uuid:pk>/read/", views.notification_mark_read, name="mark_read"),
    path("read-all/", views.notification_mark_all_read, name="mark_all_read"),
]

