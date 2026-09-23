"""Verwaltung der Topologie-Symbole je Gerätetyp / Geräterolle."""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from .forms import TopologySymbolForm
from .models import TopologySymbol
from .symbols import HIDDEN, KINDS, builtin_icon

APP = "netbox_customer_export"


def _builtin_kinds():
    return [(k, label, reverse(f"plugins:{APP}:symbol_builtin", kwargs={"kind": k})) for k, (label, _) in KINDS.items()]


class BuiltinIconView(LoginRequiredMixin, View):
    """PNG eines eingebauten Symbols (für Galerie und Vorschau)."""

    def get(self, request, kind):
        if kind not in KINDS:
            raise Http404
        response = HttpResponse(builtin_icon(kind), content_type="image/png")
        response["Cache-Control"] = "max-age=86400"
        return response


class SymbolListView(PermissionRequiredMixin, View):
    permission_required = f"{APP}.view_topologysymbol"

    def get(self, request):
        symbols = TopologySymbol.objects.select_related("device_type__manufacturer", "role")
        builtin = {k: url for k, _, url in _builtin_kinds()}
        rows = []
        for s in symbols:
            if s.icon:
                preview = s.icon.url
            elif s.kind and s.kind != HIDDEN:
                preview = builtin[s.kind]
            else:
                preview = None
            rows.append((s, preview))
        return render(
            request,
            f"{APP}/symbol_list.html",
            {"rows": rows, "builtin": _builtin_kinds(), "types": [r for r in rows if r[0].device_type_id], "roles": [r for r in rows if r[0].role_id]},
        )


class SymbolEditView(PermissionRequiredMixin, View):
    template_name = f"{APP}/symbol_edit.html"

    def get_permission_required(self):
        return [f"{APP}.{'change' if self.kwargs.get('pk') else 'add'}_topologysymbol"]

    def _obj(self, pk):
        return get_object_or_404(TopologySymbol, pk=pk) if pk else TopologySymbol()

    def _render(self, request, obj, form):
        return render(request, self.template_name, {"object": obj, "form": form, "builtin": _builtin_kinds()})

    def get(self, request, pk=None):
        obj = self._obj(pk)
        initial = {}
        for key in ("device_type", "role"):  # Vorbelegung z.B. aus dem Link auf der Gerätetyp-Seite
            if request.GET.get(key):
                initial[key] = request.GET[key]
        return self._render(request, obj, TopologySymbolForm(instance=obj, initial=initial))

    def post(self, request, pk=None):
        obj = self._obj(pk)
        form = TopologySymbolForm(request.POST, request.FILES, instance=obj)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f"Topologie-Symbol für „{obj}“ gespeichert.")
            return redirect(f"plugins:{APP}:symbol_list")
        return self._render(request, obj, form)


class SymbolDeleteView(PermissionRequiredMixin, View):
    permission_required = f"{APP}.delete_topologysymbol"

    def get(self, request, pk):
        return render(request, f"{APP}/symbol_delete.html", {"object": get_object_or_404(TopologySymbol, pk=pk)})

    def post(self, request, pk):
        obj = get_object_or_404(TopologySymbol, pk=pk)
        name = str(obj)
        if obj.icon:
            obj.icon.delete(save=False)
        obj.delete()
        messages.success(request, f"Topologie-Symbol für „{name}“ gelöscht – es gilt wieder die automatische Erkennung.")
        return redirect(f"plugins:{APP}:symbol_list")
