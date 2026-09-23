import base64
import mimetypes

from django.template.loader import render_to_string


def _logo_data_uri(path):
    if not path:
        return None
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as f:
        return f"data:{mime};base64,{base64.b64encode(f.read()).decode('ascii')}"


def render_html(doc):
    return render_to_string(
        "netbox_customer_export/document.html",
        {"doc": doc, "b": doc.branding, "logo": _logo_data_uri(doc.branding.get("logo_path"))},
    )
