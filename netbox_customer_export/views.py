from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views import View

from .blocks import Document
from .branding import get_branding
from .forms import ExportForm, ScopeSelectForm
from .renderers import MissingDependency, render as render_document
from .scope import SCOPE_MODELS, Scope
from .sections import SECTIONS


class ScopeSelectView(LoginRequiredMixin, View):
    template_name = "netbox_customer_export/select.html"

    def get(self, request):
        return render(request, self.template_name, {"form": ScopeSelectForm()})

    def post(self, request):
        form = ScopeSelectForm(request.POST)
        if form.is_valid():
            return redirect("plugins:netbox_customer_export:export", kind=form.cleaned_data["kind"], pk=form.cleaned_data["obj"].pk)
        return render(request, self.template_name, {"form": form})


class ExportView(LoginRequiredMixin, View):
    def _drawio(self, request, scope, form, opts):
        """Nur die Topologie – als editierbare draw.io-Datei (eine Seite je Standort)."""
        from .topology import build_graphs, render_drawio

        graphs = build_graphs(scope, opts)
        if not graphs:
            messages.warning(request, "Keine verkabelten Geräte gefunden – es gibt keine Topologie zu exportieren.")
            return self._render_form(request, scope, form)
        content = render_drawio(graphs, show_ports="ports" in (opts.get("topo_details") or []))
        response = HttpResponse(content, content_type="application/xml")
        filename = f"topologie_{slugify(str(scope.obj)) or 'export'}_{timezone.localdate():%Y%m%d}.drawio"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    template_name = "netbox_customer_export/export.html"

    def _scope(self, request, kind, pk):
        model = SCOPE_MODELS.get(kind)
        if model is None:
            raise Http404
        obj = get_object_or_404(model.objects.restrict(request.user, "view"), pk=pk)
        return Scope(kind, obj, request.user)

    def _render_form(self, request, scope, form):
        grouped = {}
        for s in SECTIONS.values():
            grouped.setdefault(s.group, []).append(s)
        return render(request, self.template_name, {"object": scope.obj, "scope": scope, "form": form, "section_groups": grouped})

    def get(self, request, kind, pk):
        scope = self._scope(request, kind, pk)
        return self._render_form(request, scope, ExportForm(scope=scope))

    def post(self, request, kind, pk):
        scope = self._scope(request, kind, pk)
        form = ExportForm(request.POST, scope=scope)
        if not form.is_valid():
            return self._render_form(request, scope, form)

        opts = form.cleaned_data
        if opts["format"] == "drawio":
            return self._drawio(request, scope, form, opts)
        blocks = []
        for key in opts["sections"]:
            blocks += SECTIONS[key].func(scope, opts)

        doc = Document(
            title=opts["title"],
            subtitle=opts.get("subtitle", ""),
            blocks=blocks,
            meta={
                "author": opts.get("author") or request.user.get_full_name() or request.user.username,
                "date": timezone.localtime().strftime("%d.%m.%Y"),
            },
            branding=get_branding(opts["branding"]),
        )
        try:
            content, content_type, ext = render_document(doc, opts["format"], request)
        except MissingDependency as e:
            messages.error(request, str(e))
            return self._render_form(request, scope, form)

        response = HttpResponse(content, content_type=content_type)
        if ext != "html":
            filename = f"{slugify(opts['title']) or 'dokumentation'}_{timezone.localdate():%Y%m%d}.{ext}"
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
