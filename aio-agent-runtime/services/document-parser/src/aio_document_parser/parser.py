"""Bounded text extraction with immutable source locations; no macros, external fetch, hooks or OCR fallback."""

import csv
import hashlib
import io
import json
from pathlib import PurePosixPath
import re
import stat
import zipfile

from defusedxml import ElementTree as XML

PARSER_VERSION = "document-parser-v1"
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_TEXT_BYTES = 1024 * 1024
MAX_CHUNKS = 512
MAX_CHUNK_BYTES = 4096
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
ALLOWED_FORMATS = {"txt", "md", "csv", "pdf", "docx", "xlsx"}


class ParseFailure(Exception):
    pass


class Output:
    def __init__(self):
        self.chunks, self.warnings = [], set()
        self.total = 0

    def add(self, text, location):
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n").strip()
        if not text:
            return
        if "\0" in text:
            raise ParseFailure("DOCUMENT_TEXT_INVALID")
        self.total += len(text.encode("utf-8"))
        if self.total > MAX_TEXT_BYTES:
            raise ParseFailure("DOCUMENT_TEXT_LIMIT")
        # Stable chunk boundaries within a page/paragraph/table row; do not invent cross-page coordinates.
        offset = 0
        while offset < len(text):
            end = min(len(text), offset + 1200)
            while len(text[offset:end].encode("utf-8")) > MAX_CHUNK_BYTES:
                end -= 64
            value = text[offset:end]
            if len(self.chunks) >= MAX_CHUNKS:
                raise ParseFailure("DOCUMENT_CHUNK_LIMIT")
            self.chunks.append(
                {
                    "ordinal": len(self.chunks),
                    "text": value,
                    "location": {**location, "text_start": offset, "text_end": end},
                    "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
                }
            )
            if end == len(text):
                break
            offset = max(offset + 1, end - 160)


class Archive:
    def __init__(self, raw):
        self.archive = zipfile.ZipFile(io.BytesIO(raw))
        entries = self.archive.infolist()
        if len(entries) > 2048:
            raise ParseFailure("DOCUMENT_ARCHIVE_LIMIT")
        names, total = set(), 0
        self.entries = {}
        for info in entries:
            # Some host platforms normalize separators while reading ZipInfo.filename.
            # Admission must inspect the original archive name, not a normalized alias.
            path = info.orig_filename
            normalized = path.rstrip("/")
            if (
                not normalized
                or len(path.encode("utf-8")) > 512
                or "\\" in path
                or ":" in path
                or any(ord(c) < 32 for c in path)
                or PurePosixPath(path).is_absolute()
                or any(part in {"", ".", ".."} for part in normalized.split("/"))
            ):
                raise ParseFailure("DOCUMENT_ARCHIVE_PATH")
            if normalized.casefold() in names:
                raise ParseFailure("DOCUMENT_ARCHIVE_DUPLICATE")
            names.add(normalized.casefold())
            kind = stat.S_IFMT(info.external_attr >> 16)
            if kind not in {0, stat.S_IFREG, stat.S_IFDIR} or (info.flag_bits & 1):
                raise ParseFailure("DOCUMENT_ARCHIVE_NODE")
            if "vbaproject" in normalized.lower() or "/embeddings/" in ("/" + normalized.lower()):
                raise ParseFailure("DOCUMENT_ACTIVE_CONTENT")
            total += info.file_size
            if (
                info.file_size > 16 * 1024 * 1024
                or total > MAX_ARCHIVE_BYTES
                or info.file_size > max(1024, info.compress_size * 150)
            ):
                raise ParseFailure("DOCUMENT_ARCHIVE_LIMIT")
            self.entries[path] = info
        self.read_bytes = 0

    def read(self, name):
        if name not in self.entries or self.entries[name].is_dir():
            raise ParseFailure("DOCUMENT_STRUCTURE_INVALID")
        with self.archive.open(self.entries[name]) as stream:
            value = stream.read(min(self.entries[name].file_size + 1, 16 * 1024 * 1024 + 1))
        self.read_bytes += len(value)
        if len(value) != self.entries[name].file_size or self.read_bytes > 64 * 1024 * 1024:
            raise ParseFailure("DOCUMENT_ARCHIVE_LIMIT")
        return value

    def xml(self, name):
        return XML.fromstring(self.read(name), forbid_dtd=True, forbid_entities=True, forbid_external=True)

    def close(self):
        self.archive.close()


def local(tag):
    return tag.rsplit("}", 1)[-1]


def xml_text(node):
    return "".join(child.text or "" for child in node.iter() if local(child.tag) == "t")


def relationships(archive, name, output):
    if name not in archive.entries:
        return {}
    result = {}
    for entry in archive.xml(name):
        if entry.attrib.get("TargetMode") == "External":
            output.warnings.add("EXTERNAL_LINKS_NOT_FETCHED")
            if entry.attrib.get("Type", "").rsplit("/", 1)[-1] in {"attachedTemplate", "oleObject", "package"}:
                raise ParseFailure("DOCUMENT_ACTIVE_CONTENT")
            continue
        result[entry.attrib.get("Id")] = entry.attrib.get("Target", "")
    return result


def text_document(raw, output, kind):
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError:
        raise ParseFailure("DOCUMENT_ENCODING_UNSUPPORTED") from None
    if "\0" in text:
        raise ParseFailure("DOCUMENT_TEXT_INVALID")
    if kind == "csv":
        cells = 0
        for row_no, row in enumerate(csv.reader(io.StringIO(text)), 1):
            cells += len(row)
            if row_no > 5000 or len(row) > 128 or cells > 200000 or any(len(cell) > 4096 for cell in row):
                raise ParseFailure("DOCUMENT_TABLE_LIMIT")
            output.add(" | ".join(row), {"kind": "csv_row", "row": row_no})
        return
    lines, start, paragraph = text.splitlines(), 1, []
    if len(lines) > 50000:
        raise ParseFailure("DOCUMENT_TEXT_LIMIT")
    for number, line in enumerate(lines, 1):
        if not line.strip() and paragraph:
            output.add("\n".join(paragraph), {"kind": "lines", "line_start": start, "line_end": number - 1})
            paragraph = []
        elif line.strip():
            if not paragraph:
                start = number
            paragraph.append(line)
            if sum(len(value) for value in paragraph) >= 4000:
                output.add("\n".join(paragraph), {"kind": "lines", "line_start": start, "line_end": number})
                paragraph = []
    if paragraph:
        output.add("\n".join(paragraph), {"kind": "lines", "line_start": start, "line_end": len(lines)})


def word_document(raw, output):
    archive = Archive(raw)
    try:
        relationships(archive, "word/_rels/document.xml.rels", output)
        relationships(archive, "word/_rels/settings.xml.rels", output)
        root = archive.xml("word/document.xml")
        paragraphs = 0
        for element in root.iter():
            if local(element.tag) == "altChunk":
                raise ParseFailure("DOCUMENT_ACTIVE_CONTENT")
            if local(element.tag) != "p":
                continue
            paragraphs += 1
            if paragraphs > 10000:
                raise ParseFailure("DOCUMENT_TEXT_LIMIT")
            output.add(xml_text(element), {"kind": "paragraph", "paragraph": paragraphs})
    finally:
        archive.close()


def spreadsheet(raw, output):
    archive = Archive(raw)
    try:
        root = archive.xml("xl/workbook.xml")
        rels = relationships(archive, "xl/_rels/workbook.xml.rels", output)
        if any(name.startswith("xl/externalLinks/") for name in archive.entries):
            raise ParseFailure("DOCUMENT_ACTIVE_CONTENT")
        shared = []
        if "xl/sharedStrings.xml" in archive.entries:
            for item in archive.xml("xl/sharedStrings.xml"):
                value = xml_text(item)
                if len(shared) >= 100000 or len(value) > 16384:
                    raise ParseFailure("DOCUMENT_TABLE_LIMIT")
                shared.append(value)
        sheets = [e for e in root.iter() if local(e.tag) == "sheet"]
        if len(sheets) > 32:
            raise ParseFailure("DOCUMENT_TABLE_LIMIT")
        cells = 0
        for sheet in sheets:
            if sheet.attrib.get("state", "visible") != "visible":
                output.warnings.add("HIDDEN_SHEETS_NOT_INDEXED")
                continue
            name = sheet.attrib.get("name", "sheet")[:128]
            rel = next((value for key, value in sheet.attrib.items() if local(key) == "id"), None)
            target = rels.get(rel, "")
            if target.startswith("/xl/"):
                target = target[1:]
            elif not target.startswith("xl/"):
                target = "xl/" + target
            if ".." in target.split("/") or not target.startswith("xl/worksheets/"):
                raise ParseFailure("DOCUMENT_STRUCTURE_INVALID")
            rows = [node for node in archive.xml(target).iter() if local(node.tag) == "row"]
            if len(rows) > 5000:
                raise ParseFailure("DOCUMENT_TABLE_LIMIT")
            for row in rows:
                if row.attrib.get("hidden") == "1":
                    output.warnings.add("HIDDEN_ROWS_NOT_INDEXED")
                    continue
                row_no = row.attrib.get("r", "")
                if not row_no.isdecimal() or not 1 <= int(row_no) <= 1048576:
                    raise ParseFailure("DOCUMENT_STRUCTURE_INVALID")
                values = []
                for cell in row:
                    if local(cell.tag) != "c":
                        continue
                    cells += 1
                    ref = cell.attrib.get("r", "")
                    if cells > 200000 or len(values) >= 128 or not re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]{0,6}", ref):
                        raise ParseFailure("DOCUMENT_TABLE_LIMIT")
                    value = next((child.text or "" for child in cell if local(child.tag) == "v"), "")
                    if cell.attrib.get("t") == "s":
                        if not value.isdecimal() or int(value) >= len(shared):
                            raise ParseFailure("DOCUMENT_STRUCTURE_INVALID")
                        value = shared[int(value)]
                    elif cell.attrib.get("t") == "inlineStr":
                        value = xml_text(cell)
                    formula = next((child.text or "" for child in cell if local(child.tag) == "f"), None)
                    if formula is not None:
                        output.warnings.add("FORMULAS_NOT_EXECUTED")
                        value = "[公式未计算] " + formula + " [缓存值] " + value
                    if len(value) > 4096:
                        raise ParseFailure("DOCUMENT_TABLE_LIMIT")
                    values.append(ref + ": " + value)
                output.add(" | ".join(values), {"kind": "spreadsheet_row", "sheet": name, "row": int(row_no)})
    finally:
        archive.close()


def pdf_document(raw, output):
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw), strict=True)
    if reader.is_encrypted:
        raise ParseFailure("DOCUMENT_ENCRYPTED")
    if len(reader.pages) > 100:
        raise ParseFailure("DOCUMENT_PAGE_LIMIT")
    root = reader.root_object
    names = root.get("/Names", {})
    if hasattr(names, "get_object"):
        names = names.get_object()
    form = root.get("/AcroForm", {})
    if hasattr(form, "get_object"):
        form = form.get_object()
    if "/JavaScript" in names or "/EmbeddedFiles" in names or (isinstance(form, dict) and "/XFA" in form):
        raise ParseFailure("DOCUMENT_ACTIVE_CONTENT")
    dangerous = {"/JavaScript", "/Launch", "/SubmitForm", "/ImportData", "/GoToR", "/Rendition"}

    def action(value):
        if hasattr(value, "get_object"):
            value = value.get_object()
        if isinstance(value, dict) and (value.get("/S") in dangerous or "/JS" in value):
            raise ParseFailure("DOCUMENT_ACTIVE_CONTENT")

    action(root.get("/OpenAction"))
    if root.get("/AA"):
        raise ParseFailure("DOCUMENT_ACTIVE_CONTENT")
    for number, page in enumerate(reader.pages, 1):
        if page.get("/AA"):
            raise ParseFailure("DOCUMENT_ACTIVE_CONTENT")
        annotations = page.get("/Annots", [])
        if len(annotations) > 1000:
            raise ParseFailure("DOCUMENT_STRUCTURE_LIMIT")
        for annotation in annotations:
            value = annotation.get_object()
            action(value.get("/A"))
            if value.get("/AA") or value.get("/Subtype") in {"/FileAttachment", "/RichMedia"}:
                raise ParseFailure("DOCUMENT_ACTIVE_CONTENT")
        output.add(page.extract_text() or "", {"kind": "page", "page": number})


def parse(raw: bytes, kind: str):
    if not isinstance(raw, bytes) or len(raw) > MAX_SOURCE_BYTES or not raw:
        raise ParseFailure("DOCUMENT_SOURCE_LIMIT")
    if kind not in ALLOWED_FORMATS:
        raise ParseFailure("DOCUMENT_FORMAT_UNSUPPORTED")
    output = Output()
    try:
        if kind in {"txt", "md", "csv"}:
            text_document(raw, output, kind)
        elif kind == "docx":
            word_document(raw, output)
        elif kind == "xlsx":
            spreadsheet(raw, output)
        else:
            pdf_document(raw, output)
    except ParseFailure:
        raise
    except Exception:
        # Never emit raw document content/tracebacks as a trusted parser report.
        raise ParseFailure("DOCUMENT_PARSE_FAILED") from None
    if not output.chunks:
        raise ParseFailure("DOCUMENT_NO_EXTRACTABLE_TEXT")
    result = {
        "schema_version": 1,
        "parser_version": PARSER_VERSION,
        "format": kind,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "text_bytes": output.total,
        "chunks": output.chunks,
        "warnings": sorted(output.warnings),
    }
    if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > 2 * 1024 * 1024:
        raise ParseFailure("DOCUMENT_OUTPUT_LIMIT")
    return result
