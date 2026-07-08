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
    FONT_PATHS = [
        "/var/task/fonts/NotoSansCJKjp-Bold.otf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
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
            size -= 1
        try:
            fnt = ImageFont.truetype(fp, min_px)
        except Exception:
            fnt = ImageFont.load_default()
        return min_px, fnt

    def img_to_pdf_page(img, pw, ph):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
            img.save(tmp_path, format="JPEG", quality=95)
        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=(pw, ph))
        c.drawImage(tmp_path, 0, 0, width=pw, height=ph)
        c.save()
        os.unlink(tmp_path)
        buf.seek(0)
        return PdfReader(buf).pages[0]

    def render_page_to_image(fitz_doc, page_index, dpi):
        page = fitz_doc[page_index]
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        return img

    writer = PdfWriter()

    fitz_doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as plumber_pdf:
        total = len(plumber_pdf.pages)

        for i in range(total):
            pl_page = plumber_pdf.pages[i]
            img = render_page_to_image(fitz_doc, i, DPI)

words = pl_page.extract_words()

            # ▼▼▼ デバッグ用（原因特定できたら削除） ▼▼▼
            if i == 0:
                raise Exception("DEBUG WORDS: " + json.dumps([w["text"] for w in words], ensure_ascii=False))
            # ▲▲▲ デバッグ用 ▲▲▲

            items = [
                (w["text"], w["x0"], w["x1"], w["top"], w["bottom"])
                for w in words
                if "\u3010" in w["text"]
            ]
            if items:
                draw = ImageDraw.Draw(img)
                for text, x0, x1, top, bottom in items:
                    px0 = int(x0 * SCALE)
                    py0 = int(top * SCALE)
                    erase_x1 = px0 + MAX_TEXT_WIDTH_PX + 5
                    py1 = py0 + MAX_FONT_PX + 4

                    if font_path:
                        font_size_px, font = get_font_size(
                            draw, text, font_path,
                            MAX_TEXT_WIDTH_PX, MAX_FONT_PX, MIN_FONT_PX
                        )
                    else:
                        font = ImageFont.load_default()
                        font_size_px = MAX_FONT_PX

                    draw.rectangle([px0 - 3, py0 - 3, erase_x1, py1 + 3], fill="white")
                    draw.text((px0, py0), text, font=font, fill="black")

            writer.add_page(img_to_pdf_page(img, pl_page.width, pl_page.height))

    fitz_doc.close()

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors()
        self.end_headers()

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)

            pdf_b64 = data.get("pdf")
            if not pdf_b64:
                self._error(400, "pdf field is required")
                return

            pdf_bytes = base64.b64decode(pdf_b64)
            result_bytes = process_pdf(pdf_bytes)
            result_b64 = base64.b64encode(result_bytes).decode()

            self.send_response(200)
            self._set_cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"pdf": result_b64}).encode())

        except Exception as e:
            self._error(500, str(e))

    def _set_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _error(self, code, msg):
        self.send_response(code)
        self._set_cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": msg}).encode())

    def log_message(self, format, *args):
        pass
