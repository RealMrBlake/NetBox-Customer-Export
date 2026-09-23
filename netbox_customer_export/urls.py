from django.urls import path

from . import views

urlpatterns = [
    path("", views.ScopeSelectView.as_view(), name="select"),
    path("export/<str:kind>/<int:pk>/", views.ExportView.as_view(), name="export"),
]
