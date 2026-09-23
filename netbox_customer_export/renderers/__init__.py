class MissingDependency(Exception):
    pass


def render(doc, fmt, request=None):
    """Gibt (bytes, content_type, dateiendung) zurück."""
    if fmt == "docx":
        from .docx import render_docx

        return render_docx(doc), "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"

    from .html import render_html

    html = render_html(doc)
    if fmt == "html":
        return html, "text/html; charset=utf-8", "html"

    try:
        from weasyprint import HTML
    except (ImportError, OSError) as e:
        raise MissingDependency(f"PDF-Export benötigt WeasyPrint (pip install weasyprint + Pango): {e}")
    base_url = request.build_absolute_uri("/") if request else None
    return HTML(string=html, base_url=base_url).write_pdf(), "application/pdf", "pdf"
