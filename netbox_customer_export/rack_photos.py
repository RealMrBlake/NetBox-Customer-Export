"""Bildanhänge (extras.ImageAttachment) von Racks: Auswahl im Formular und Anhang am Dokumentende."""
from io import BytesIO

from dcim.models import Rack
from django.contrib.contenttypes.models import ContentType
from extras.models import ImageAttachment

MAX_EDGE = 1600  # px – Handyfotos verkleinern, damit PDF/Word handlich bleiben


def attachments(scope):
    """Bildanhänge aller Racks im Scope, die der Benutzer sehen darf – sortiert nach Rack."""
    racks = {r.pk: r for r in scope.racks().select_related("site", "location")}
    if not racks:
        return []
    qs = (
        ImageAttachment.objects.restrict(scope.user, "view")
        .filter(object_type=ContentType.objects.get_for_model(Rack), object_id__in=racks)
        .order_by("name", "pk")
    )
    items = [(racks[a.object_id], a) for a in qs]
    items.sort(key=lambda x: (str(x[0].site), str(x[0].location or ""), x[0].name))
    return items


def grouped(scope):
    """[(rack, [attachment, …]), …] für die Vorschau im Formular."""
    out = []
    for rack, att in attachments(scope):
        if out and out[-1][0] == rack:
            out[-1][1].append(att)
        else:
            out.append((rack, [att]))
    return out


def caption(att):
    name = att.name or att.image.name.rsplit("/", 1)[-1]
    desc = getattr(att, "description", "")
    return f"{name} – {desc}" if desc else name


def load_jpeg(att):
    """Bild drehen (EXIF), verkleinern und als JPEG zurückgeben. None, wenn nicht lesbar."""
    from PIL import Image, ImageOps

    try:
        with att.image.open("rb") as f:
            img = Image.open(BytesIO(f.read()))
            img = ImageOps.exif_transpose(img)
        img.thumbnail((MAX_EDGE, MAX_EDGE))
        if img.mode != "RGB":
            img = img.convert("RGB")
        out = BytesIO()
        img.save(out, "JPEG", quality=85)
        return out.getvalue()
    except Exception:  # noqa: BLE001 – fehlende/defekte Datei überspringen
        return None
