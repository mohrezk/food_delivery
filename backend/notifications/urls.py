from django.urls import path

from . import views

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="notifications-list"),
    path(
        "unread-count/",
        views.NotificationUnreadCountView.as_view(),
        name="notifications-unread-count",
    ),
    path(
        "read-all/",
        views.NotificationReadAllView.as_view(),
        name="notifications-read-all",
    ),
    path(
        "<int:pk>/read/",
        views.NotificationReadView.as_view(),
        name="notification-read",
    ),
]
