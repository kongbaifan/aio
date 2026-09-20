"""Only synthetic fixtures are parsed by host unit tests; product documents run in isolated cells."""

import io
import zipfile

import pytest

from aio_document_parser.parser import ParseFailure, parse


def archive(files, compression=zipfile.ZIP_DEFLATED):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=compression) as z:
        for name, value in files.items():
            z.writestr(name, value)
    return output.getvalue()


def docx(text="公司报销规范：发票在月底前提交。"):
    return archive(
        {
            "word/document.xml": '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'
            + text
            + "</w:t></w:r></w:p></w:body></w:document>"
        }
    )


def xlsx():
    return archive(
        {
            "xl/workbook.xml": '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="费用" sheetId="1" r:id="rId1"/></sheets></workbook>',
            "xl/_rels/workbook.xml.rels": '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
            "xl/worksheets/sheet1.xml": '<worksheet><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>报销标准</t></is></c><c r="B1"><v>200</v></c><c r="C1"><f>SUM(B1:B2)</f><v>300</v></c></row></sheetData></worksheet>',
        }
    )


def pdf():
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 10 250 Td (Approved travel allowance is 200.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.mark.parametrize(
    "kind,data,expected,location",
    [
        ("txt", "报销流程\n月底提交发票。".encode(), "月底提交", "lines"),
        ("md", "# 报销说明\n\n先取得审批。".encode(), "取得审批", "lines"),
        ("csv", "项目,标准\n餐费,200\n".encode(), "餐费", "csv_row"),
        ("docx", docx(), "报销规范", "paragraph"),
        ("xlsx", xlsx(), "报销标准", "spreadsheet_row"),
    ],
)
def test_supported_formats_preserve_text_and_source_locations(kind, data, expected, location):
    result = parse(data, kind)
    assert expected in str(result["chunks"])
    assert result["chunks"][0]["location"]["kind"] == location
    assert all(len(c["text"].encode()) <= 4096 for c in result["chunks"])


def test_pdf_extracts_page_without_rendering_or_executing_content():
    result = parse(pdf(), "pdf")
    assert "allowance is 200" in result["chunks"][0]["text"]
    assert result["chunks"][0]["location"]["page"] == 1


def test_indirect_xfa_form_is_rejected_before_indexing():
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, TextStringObject

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf())))
    form = DictionaryObject({NameObject("/XFA"): TextStringObject("synthetic untrusted XFA")})
    writer.root_object[NameObject("/AcroForm")] = writer._add_object(form)
    out = io.BytesIO()
    writer.write(out)
    with pytest.raises(ParseFailure) as rejected:
        parse(out.getvalue(), "pdf")
    assert str(rejected.value) == "DOCUMENT_ACTIVE_CONTENT"


def test_spreadsheet_formulas_are_not_executed_or_presented_as_fresh_calculation():
    result = parse(xlsx(), "xlsx")
    assert result["warnings"] == ["FORMULAS_NOT_EXECUTED"]
    assert "公式未计算" in result["chunks"][0]["text"]


@pytest.mark.parametrize("name", ["../escape.txt", "/absolute.txt", "C:/secret.txt", "nested\\bad.txt"])
def test_archive_paths_are_rejected_before_decoding(name):
    raw = archive({"word/document.xml": "<document/>", name: "inert"})
    if "\\" in name:
        raw = raw.replace(name.replace("\\", "/").encode(), name.encode())
    with pytest.raises(ParseFailure) as rejected:
        parse(raw, "docx")
    assert str(rejected.value) == "DOCUMENT_ARCHIVE_PATH"


def test_xml_entities_macros_and_compression_bombs_are_rejected():
    cases = [
        archive({"word/document.xml": '<!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><r>&x;</r>'}),
        archive({"word/document.xml": "<r/>", "word/vbaProject.bin": "inert"}),
        archive({"word/document.xml": "x" * 2_000_000}),
    ]
    for raw in cases:
        with pytest.raises(ParseFailure):
            parse(raw, "docx")


def test_symlink_and_case_collisions_are_not_accepted_as_office_files():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        info = zipfile.ZipInfo("word/document.xml")
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        z.writestr(info, "../../secret")
    with pytest.raises(ParseFailure):
        parse(out.getvalue(), "docx")
    with pytest.raises(ParseFailure):
        parse(archive({"word/document.xml": "<r/>", "word/DOCUMENT.xml": "<r/>"}), "docx")


def test_external_hyperlinks_are_not_fetched():
    raw = archive(
        {
            "word/document.xml": '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>Text only</w:t></w:r></w:p></w:document>',
            "word/_rels/document.xml.rels": '<Relationships><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" TargetMode="External" Target="http://169.254.169.254/latest/meta-data/"/></Relationships>',
        }
    )
    result = parse(raw, "docx")
    assert result["warnings"] == ["EXTERNAL_LINKS_NOT_FETCHED"]
    assert result["chunks"][0]["text"] == "Text only"


def test_limits_and_unsupported_encoding_fail_closed():
    for raw, kind in [
        (b"bad\x00text", "txt"),
        (b"\xff\xfeabc", "txt"),
        (b"\n", "txt"),
        (b"plain", "exe"),
        (b"x" * (8 * 1024 * 1024 + 1), "txt"),
    ]:
        with pytest.raises(ParseFailure):
            parse(raw, kind)
