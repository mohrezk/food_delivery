from django.urls import path

from . import views

urlpatterns = [
    path(
        "conversations/",
        views.ConversationListView.as_view(),
        name="chat-conversations",
    ),
    path(
        "conversations/<int:pk>/",
        views.ConversationDetailView.as_view(),
        name="chat-conversation-detail",
    ),
    path(
        "conversations/<int:pk>/messages/",
        views.SendMessageView.as_view(),
        name="chat-send-message",
    ),
    path(
        "conversations/<int:pk>/read/",
        views.MarkConversationReadView.as_view(),
        name="chat-conversation-read",
    ),
    path(
        "unread-count/",
        views.UnreadCountView.as_view(),
        name="chat-unread-count",
    ),
]
