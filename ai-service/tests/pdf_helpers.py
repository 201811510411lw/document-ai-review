def write_minimal_pdf(path, text: str) -> None:
    text_stream = _pdf_text_stream(text)
    unicode_map = _pdf_unicode_map(text)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 8 0 R >>"
        ),
        (
            b"<< /Type /Font /Subtype /Type0 /BaseFont /Helvetica "
            b"/Encoding /Identity-H /DescendantFonts [5 0 R] /ToUnicode 6 0 R >>"
        ),
        (
            b"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /Helvetica "
            b"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) "
            b"/Supplement 0 >> /FontDescriptor 7 0 R >>"
        ),
        _pdf_stream_object(unicode_map),
        (
            b"<< /Type /FontDescriptor /FontName /Helvetica /Flags 4 "
            b"/FontBBox [0 -200 1000 900] /ItalicAngle 0 /Ascent 800 "
            b"/Descent -200 /CapHeight 700 /StemV 80 >>"
        ),
        _pdf_stream_object(text_stream),
    ]
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(content))
        content.extend(f"{index} 0 obj\n".encode("ascii"))
        content.extend(obj)
        content.extend(b"\nendobj\n")
    xref_offset = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    content.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    path.write_bytes(content)


def write_blank_pdf(path) -> None:
    write_blank_pdf_with_pages(path, 1)


def write_blank_pdf_with_pages(path, page_count: int) -> None:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        (
            b"<< /Type /Pages /Kids ["
            + b" ".join(f"{index} 0 R".encode("ascii") for index in range(3, 3 + page_count))
            + f" ] /Count {page_count} >>".encode("ascii")
        ),
    ]
    objects.extend(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>"
        for _ in range(page_count)
    )
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(content))
        content.extend(f"{index} 0 obj\n".encode("ascii"))
        content.extend(obj)
        content.extend(b"\nendobj\n")
    xref_offset = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    content.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    path.write_bytes(content)


def _pdf_stream_object(data: str) -> bytes:
    raw = data.encode("utf-8")
    return (
        b"<< /Length "
        + str(len(raw)).encode("ascii")
        + b" >>\nstream\n"
        + raw
        + b"\nendstream"
    )


def _pdf_text_stream(text: str) -> str:
    lines = ["BT /F1 12 Tf 72 720 Td 14 TL"]
    for index, line in enumerate(text.splitlines()):
        if index:
            lines.append("T*")
        lines.append(f"<{''.join(f'{ord(char):04X}' for char in line)}> Tj")
    lines.append("ET")
    return "\n".join(lines)


def _pdf_unicode_map(text: str) -> str:
    entries = [
        f"<{ord(char):04X}> <{ord(char):04X}>"
        for char in sorted(set(text) - {"\n"})
    ]
    return "\n".join(
        [
            "/CIDInit /ProcSet findresource begin",
            "12 dict begin",
            "begincmap",
            "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
            "/CMapName /Adobe-Identity-UCS def",
            "/CMapType 2 def",
            "1 begincodespacerange",
            "<0000> <FFFF>",
            "endcodespacerange",
            f"{len(entries)} beginbfchar",
            *entries,
            "endbfchar",
            "endcmap",
            "CMapName currentdict /CMap defineresource pop",
            "end",
            "end",
        ]
    )
