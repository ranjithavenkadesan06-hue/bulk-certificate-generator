"""
Certificate generation: the single predefined template, drawn with ReportLab.

The template is just the code in generate_certificate_pdf(): the layout is
fixed and only the recipient name, course name and date change.
"""
import re
from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


def fit_text(text, font, start_size, max_width):
    """Shrink the font size until the text fits inside max_width (so long names don't overflow)."""
    size = start_size
    while stringWidth(text, font, size) > max_width and size > 10:
        size -= 1
    return size


def generate_certificate_pdf(file_path: Path, recipient_name: str, course_name: str, issue_date: date):
    """Create one PDF certificate and save it at file_path. Raises an error if it cannot."""
    # The built-in Helvetica font only supports Latin characters. If we tried to
    # draw anything else it would print garbage, so we fail clearly instead.
    for text in (recipient_name, course_name):
        try:
            text.encode("latin-1")
        except UnicodeEncodeError:
            raise ValueError("Name contains characters not supported by the certificate font")

    page_width, page_height = landscape(A4)
    center = page_width / 2
    max_text_width = page_width - 160

    # pageCompression=0 keeps the text readable inside the PDF file (handy for tests)
    pdf = canvas.Canvas(str(file_path), pagesize=landscape(A4), pageCompression=0)

    # Double border
    pdf.setLineWidth(4)
    pdf.rect(30, 30, page_width - 60, page_height - 60)
    pdf.setLineWidth(1)
    pdf.rect(40, 40, page_width - 80, page_height - 80)

    # Title
    pdf.setFont("Helvetica-Bold", 38)
    pdf.drawCentredString(center, page_height - 130, "CERTIFICATE OF COMPLETION")

    # "This is to certify that"
    pdf.setFont("Helvetica", 16)
    pdf.drawCentredString(center, page_height - 190, "This is to certify that")

    # Recipient name (recipient-specific)
    name_size = fit_text(recipient_name, "Helvetica-Bold", 34, max_text_width)
    pdf.setFont("Helvetica-Bold", name_size)
    pdf.drawCentredString(center, page_height - 250, recipient_name)

    # "has successfully completed"
    pdf.setFont("Helvetica", 16)
    pdf.drawCentredString(center, page_height - 300, "has successfully completed")

    # Course / event name (same for the whole job)
    course_size = fit_text(course_name, "Helvetica-Bold", 24, max_text_width)
    pdf.setFont("Helvetica-Bold", course_size)
    pdf.drawCentredString(center, page_height - 345, course_name)

    # Date
    pdf.setFont("Helvetica", 14)
    pdf.drawCentredString(center, 90, f"Date: {issue_date.isoformat()}")

    pdf.save()


def safe_filename(text):
    """Turn a name into something safe to use as a file name, e.g. 'A/B C' -> 'A_B_C'."""
    cleaned = re.sub(r"[^A-Za-z0-9 _-]", "_", text).strip().replace(" ", "_")
    return cleaned or "certificate"
