"""Create a readable PDF report containing the extracted product details."""

import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional
from urllib.parse import quote
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from config import DOWNLOAD_DIR
from models import Product


_FONT_NAME = "Helvetica"
_BOLD_FONT_NAME = "Helvetica-Bold"


def _register_unicode_font() -> None:
    """Register DejaVu Sans when available so symbols like the rupee sign render."""
    global _FONT_NAME, _BOLD_FONT_NAME

    # Common Linux, Windows, and macOS font locations; use the first pair found.
    font_pairs = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ]

    for regular_path, bold_path in font_pairs:
        if Path(regular_path).exists() and Path(bold_path).exists():
            try:
                pdfmetrics.registerFont(TTFont("StoreReportFont", regular_path))
                pdfmetrics.registerFont(TTFont("StoreReportFont-Bold", bold_path))
                _FONT_NAME = "StoreReportFont"
                _BOLD_FONT_NAME = "StoreReportFont-Bold"
                return
            except Exception:
                # Continue to another platform font if a font cannot be registered.
                continue


def _pdf_safe_text(value: Optional[str]) -> str:
    """Escape text for ReportLab Paragraph; degrade the rupee glyph if needed."""
    if value is None:
        return "Not listed"

    text = str(value)
    # Standard PDF base fonts may not contain the rupee glyph; provide a clear fallback.
    if _FONT_NAME == "Helvetica":
        text = text.replace("₹", "INR ")

    # Paragraph parses a small HTML-like markup language, so escape scraped site text.
    return escape(text).replace("\n", "<br/>")


def _styles():
    """Build consistent paragraph styles for headings, labels, and body text."""
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle", parent=base["Title"], fontName=_BOLD_FONT_NAME,
            fontSize=20, leading=25, alignment=TA_LEFT, spaceAfter=5 * mm,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle", parent=base["Normal"], fontName=_FONT_NAME,
            fontSize=9, leading=13, textColor=colors.HexColor("#555555"),
            spaceAfter=2 * mm,
        ),
        "product": ParagraphStyle(
            "ProductHeading", parent=base["Heading2"], fontName=_BOLD_FONT_NAME,
            fontSize=12, leading=16, spaceBefore=3 * mm, spaceAfter=2 * mm,
        ),
        "body": ParagraphStyle(
            "ProductBody", parent=base["BodyText"], fontName=_FONT_NAME,
            fontSize=8.5, leading=12, spaceAfter=1.2 * mm,
        ),
        "label": ParagraphStyle(
            "Label", parent=base["BodyText"], fontName=_BOLD_FONT_NAME,
            fontSize=8.5, leading=12,
        ),
        "small": ParagraphStyle(
            "SmallText", parent=base["BodyText"], fontName=_FONT_NAME,
            fontSize=7.5, leading=10, textColor=colors.HexColor("#555555"),
        ),
        "empty": ParagraphStyle(
            "EmptyMessage", parent=base["BodyText"], fontName=_FONT_NAME,
            fontSize=10, leading=15, spaceBefore=5 * mm,
        ),
    }


def _product_field_table(product: Product, styles) -> Table:
    """Create a compact two-column table of the main product attributes."""
    rows = []

    # Keep common comparison fields in a consistent order across different stores.
    fields = [
        ("Price", product.price),
        ("Original price", product.original_price),
        ("Discount", product.discount),
        ("Rating", product.rating),
        ("Ratings count", product.ratings_count),
        ("Reviews count", product.reviews_count),
        ("Availability", product.availability),
        ("Brand", product.brand),
        ("Currency", product.currency),
    ]

    for label, value in fields:
        if value:
            rows.append([
                Paragraph(_pdf_safe_text(label), styles["label"]),
                Paragraph(_pdf_safe_text(value), styles["body"]),
            ])

    if not rows:
        rows.append([
            Paragraph("Product details", styles["label"]),
            Paragraph("No price or rating fields were found on this page.", styles["body"]),
        ])

    # Give labels enough room while allowing long values to wrap.
    table = Table(rows, colWidths=[36 * mm, 140 * mm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F4F7")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D5D9DE")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _product_block(product: Product, index: int, styles) -> List[object]:
    """Build the PDF flowables for one product, including details and links."""
    block: List[object] = []

    # Add a numbered product heading; escape untrusted scraped text before formatting.
    block.append(Paragraph(f"{index}. {_pdf_safe_text(product.name)}", styles["product"]))
    block.append(_product_field_table(product, styles))
    block.append(Spacer(1, 2 * mm))

    # Add a clickable product URL. Escape the visible text and URL attribute separately.
    if product.product_url:
        safe_url = escape(product.product_url, {"\"": "&quot;", "'": "&#x27;"})
        url_text = escape(product.product_url)
        block.append(Paragraph(
            f"<b>Product URL:</b> <link href=\"{safe_url}\" color=\"#1459B8\">{url_text}</link>",
            styles["small"],
        ))

    # Description and specifications can be missing on search-result cards.
    if product.description:
        block.append(Spacer(1, 1 * mm))
        block.append(Paragraph(
            f"<b>Description:</b> {_pdf_safe_text(product.description)}",
            styles["body"],
        ))

    if product.specifications:
        block.append(Spacer(1, 1 * mm))
        block.append(Paragraph("<b>Specifications:</b>", styles["body"]))
        for specification in product.specifications:
            block.append(Paragraph(f"&#8226; {_pdf_safe_text(specification)}", styles["body"]))

    if product.image_url:
        block.append(Paragraph(
            f"<b>Image URL:</b> {_pdf_safe_text(product.image_url)}",
            styles["small"],
        ))

    block.append(Spacer(1, 3 * mm))
    block.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#D5D9DE")))
    block.append(Spacer(1, 2 * mm))
    return block


def _draw_page_footer(canvas, document) -> None:
    """Draw a simple page number and report label on each PDF page."""
    canvas.saveState()
    page_width, _ = A4
    canvas.setFont(_FONT_NAME, 8)
    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.drawString(18 * mm, 10 * mm, "E-commerce product search report")
    canvas.drawRightString(page_width - 18 * mm, 10 * mm, f"Page {document.page}")
    canvas.restoreState()


def generate_pdf_report(
    products: Iterable[Product],
    query: str,
    website: str,
    output_dir: Optional[Path] = None,
) -> Path:
    """Write extracted products to a timestamped PDF and return its path.

    A PDF is created even if extraction returned no products, so the user always
    receives a report explaining what was searched and what needs attention.
    """
    _register_unicode_font()
    selected_dir = Path(output_dir or DOWNLOAD_DIR)
    selected_dir.mkdir(parents=True, exist_ok=True)

    # Use a filesystem-safe query fragment and timestamp to avoid overwriting reports.
    safe_query = re.sub(r"[^A-Za-z0-9_-]+", "_", query).strip("_")[:45] or "search"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = selected_dir / f"product_report_{safe_query}_{timestamp}.pdf"

    product_list = list(products)
    styles = _styles()

    # Set a print-friendly A4 layout with consistent margins and a repeatable footer.
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=17 * mm,
        title=f"Product search report: {query}",
        author="E-commerce Product Scraper",
    )

    story: List[object] = []
    story.append(Paragraph("E-commerce Product Search Report", styles["title"]))
    story.append(Paragraph(f"<b>Search query:</b> {_pdf_safe_text(query)}", styles["subtitle"]))
    story.append(Paragraph(f"<b>Website:</b> {_pdf_safe_text(website)}", styles["subtitle"]))
    story.append(Paragraph(
        f"<b>Generated:</b> {_pdf_safe_text(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}",
        styles["subtitle"],
    ))
    story.append(Paragraph(f"<b>Products extracted:</b> {len(product_list)}", styles["subtitle"]))
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#9AA4B2")))
    story.append(Spacer(1, 3 * mm))

    if not product_list:
        # Be explicit rather than producing an empty/ambiguous PDF.
        story.append(Paragraph(
            "No product cards could be extracted from the loaded page. "
            "The store may require a manual cookie/login step, may have shown a "
            "verification page, or may use custom HTML selectors. Review the browser "
            "page and add/update a site adapter if needed.",
            styles["empty"],
        ))
    else:
        for index, product in enumerate(product_list, start=1):
            story.extend(_product_block(product, index, styles))

    # Build the file and add the same footer to every page.
    document.build(story, onFirstPage=_draw_page_footer, onLaterPages=_draw_page_footer)
    return output_path
