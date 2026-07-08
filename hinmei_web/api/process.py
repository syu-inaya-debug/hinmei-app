"""
送り状PDF 品名拡大 API
Vercel Serverless Function
"""
import base64
import io
import json
import os
import sys
import tempfile

from http.server import BaseHTTPRequestHandler


def process_pdf(pdf_bytes: bytes) -> bytes:
    """PDFの品名を大きく・太くして返す"""
    import pdfplumber
    import fitz  # PyMuPDF
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.pdfgen import canvas as rl_canvas
    from pypdf import PdfWriter, PdfReader

    DPI = 200
    SCALE = DPI / 72.0
    MAX_FONT_PT = 9.0
    MIN_FONT_PT = 6.0
    MAX_FONT_PX = int(MAX_FONT_PT * DPI / 72)
    MIN_FONT_PX = int(MIN_FONT_PT * DPI / 72)
    MAX_TEXT_WIDTH_PX = int(158.0 * SCALE)

    # Vercel環境のフォントパス（NotoSansCJK）
    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
    FONT_PATHS = [
        os.path.join(CURRENT_DIR, "NotoSansJP-Bold.ttf"),
    ]
    font_path = next((f for f in FONT_PATHS if os.path.exists(f)), None)

    def get_font_size(draw, text, fp, max_w, max_px, min_px):
        size = max_px
        while size >= min_px:
            try:
                fnt = ImageFont.truetype(fp, size)
            except Exception:
                fnt = ImageFont.load_default()
                return size, fnt
            bbox = draw.textbbox((0, 0), text, font=fnt)
            if bbox[2] - bbox[0] <= max_w:
                return size, fnt
