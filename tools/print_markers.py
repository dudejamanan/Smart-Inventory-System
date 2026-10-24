import argparse
import io
import cv2
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from app.services.frames import marker


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--size-cm", type=float, default=5)
    p.add_argument("--output", default="markers.pdf")
    p.add_argument("--ids", default=",".join(map(str, range(30))))
    args = p.parse_args()
    if not 4 <= args.size_cm <= 12:
        raise ValueError("Use 4–12 cm for an A4 layout")
    ids = list(
        dict.fromkeys([int(x) for x in args.ids.split(",")] + list(range(40, 50)))
    )
    if any(i not in list(range(30)) + list(range(40, 50)) for i in ids):
        raise ValueError("Item IDs 0–29, anchors 40–49")
    from pathlib import Path

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(args.output, pagesize=A4)
    w, h = A4
    size = args.size_cm * cm
    cell = size + 2 * cm
    cols = max(1, int((w - 2 * cm) // cell))
    rows = max(1, int((h - 3 * cm) // cell))
    for n, ident in enumerate(ids):
        pos = n % (cols * rows)
        if n and not pos:
            pdf.showPage()
        if not pos:
            pdf.setFont("Helvetica", 10)
            pdf.drawString(
                cm,
                h - cm,
                "DICT_4X4_50 / Print at 100% actual size. Measure the black square.",
            )
        x = cm + (pos % cols) * cell + cm / 2
        y = h - 2 * cm - (pos // cols) * cell - size
        data = cv2.imencode(".png", marker(ident, 600))[1].tobytes()
        pdf.drawImage(ImageReader(io.BytesIO(data)), x, y, size, size)
        pdf.drawString(
            x,
            y - 0.55 * cm,
            f"{'Anchor' if ident >= 40 else 'Item'} #{ident} / {args.size_cm:g} cm",
        )
    pdf.save()
    print(f"Wrote {args.output}: {len(ids)} markers")


if __name__ == "__main__":
    main()
