"""Verwaltung der Branding-Profile in der NetBox-Oberfläche."""
from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from .blocks import KV, P, T, Document, H
from .branding import _normalize
from .forms import BrandingProfileForm
from .models import BrandingProfile
from .renderers.html import render_html

APP = "netbox_customer_export"


class BrandingListView(PermissionRequiredMixin, View):
    permission_required = f"{APP}.view_brandingprofile"

    def get(self, request):
        return render(request, f"{APP}/branding_list.html", {"profiles": BrandingProfile.objects.all()})


class BrandingEditView(PermissionRequiredMixin, View):
    template_name = f"{APP}/branding_edit.html"

    def get_permission_required(self):
        return [f"{APP}.{'change' if self.kwargs.get('pk') else 'add'}_brandingprofile"]

    def _obj(self, pk):
        return get_object_or_404(BrandingProfile, pk=pk) if pk else BrandingProfile()

    def get(self, request, pk=None):
        obj = self._obj(pk)
        return render(request, self.template_name, {"object": obj, "form": BrandingProfileForm(instance=obj)})

    def post(self, request, pk=None):
        obj = self._obj(pk)
        form = BrandingProfileForm(request.POST, request.FILES, instance=obj)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f"Branding-Profil „{obj}“ gespeichert.")
            return redirect(f"plugins:{APP}:branding_list")
        return render(request, self.template_name, {"object": obj, "form": form})


class BrandingDeleteView(PermissionRequiredMixin, View):
    permission_required = f"{APP}.delete_brandingprofile"

    def get(self, request, pk):
        return render(request, f"{APP}/branding_delete.html", {"object": get_object_or_404(BrandingProfile, pk=pk)})

    def post(self, request, pk):
        obj = get_object_or_404(BrandingProfile, pk=pk)
        name = str(obj)
        for f in (obj.logo, obj.docx_template):
            if f:
                f.delete(save=False)
        obj.delete()
        messages.success(request, f"Branding-Profil „{name}“ gelöscht.")
        return redirect(f"plugins:{APP}:branding_list")


class BrandingPreviewView(PermissionRequiredMixin, View):
    """Beispieldokument (HTML) mit dem Profil – zum Prüfen von Farben und Logo."""

    permission_required = f"{APP}.view_brandingprofile"

    def get(self, request, pk):
        obj = get_object_or_404(BrandingProfile, pk=pk)
        blocks = [
            H(1, "Übersicht"),
            KV([("Standort", "Musterstandort"), ("Status", "Aktiv"), ("Anschrift", "Musterstraße 1\n12345 Musterstadt")]),
            H(2, "Geräte"),
            T(
                ["Name", "Hersteller / Modell", "Rack / HE", "Management-IP"],
                [
                    ["SW-CORE-01", "HPE Aruba 6100", "Rack A / HE 20", "10.0.0.2/24"],
                    ["SW-ACC-01", "HPE Aruba 6000", "Rack A / HE 18", "10.0.0.3/24"],
                    ["FW-01", "Sophos XGS 2100", "Rack A / HE 16", "10.0.0.1/24"],
                ],
            ),
            P("So sehen Überschriften, Tabellen und Fließtext mit diesem Profil aus."),
        ]
        doc = Document(
            title="Netzwerkdokumentation Vorschau",
            subtitle="Beispielkunde",
            blocks=blocks,
            meta={"author": request.user.username, "date": timezone.localtime().strftime("%d.%m.%Y")},
            branding=_normalize(obj.as_branding()),
        )
        return HttpResponse(render_html(doc), content_type="text/html; charset=utf-8")
