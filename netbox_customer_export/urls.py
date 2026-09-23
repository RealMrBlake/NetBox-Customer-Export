from django.urls import path

from . import branding_views, views

urlpatterns = [
    path("", views.ScopeSelectView.as_view(), name="select"),
    path("export/<str:kind>/<int:pk>/", views.ExportView.as_view(), name="export"),
    path("branding/", branding_views.BrandingListView.as_view(), name="branding_list"),
    path("branding/add/", branding_views.BrandingEditView.as_view(), name="branding_add"),
    path("branding/<int:pk>/", branding_views.BrandingEditView.as_view(), name="branding_edit"),
    path("branding/<int:pk>/delete/", branding_views.BrandingDeleteView.as_view(), name="branding_delete"),
    path("branding/<int:pk>/preview/", branding_views.BrandingPreviewView.as_view(), name="branding_preview"),
]
