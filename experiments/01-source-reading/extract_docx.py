"""Extract Word body paragraphs with locators; this is not an OCR/AI reader."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
NS = {"w": WORD_NS, "m": MATH_NS}


def extract(source: Path) -> dict:
    source_bytes = source.read_bytes()
    checksum = hashlib.sha256(source_bytes).hexdigest()
    with ZipFile(source) as package:
        body = ET.fromstring(package.read("word/document.xml"))
        media = [name for name in package.namelist() if name.startswith("word/media/")]
    parents = {child: parent for parent in body.iter() for child in parent}
    paragraphs = body.findall(".//w:p", NS)
    tables = body.findall(".//w:tbl", NS)
    table_indices = {table: index for index, table in enumerate(tables, 1)}
    styles = Counter()
    fragments = []
    heading = None

    for paragraph_index, paragraph in enumerate(paragraphs, 1):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", NS))
        style_node = paragraph.find("./w:pPr/w:pStyle", NS)
        style = style_node.get(f"{{{WORD_NS}}}val") if style_node is not None else None
        styles[style or "(none)"] += 1
        if not text.strip():
            continue
        if style == "Title" or (style and style.startswith("Heading")):
            heading = text

        locator = {"part": "word/document.xml", "paragraph_index": paragraph_index}
        ancestor = parents.get(paragraph)
        cell = row = table = None
        while ancestor is not None:
            if ancestor.tag == f"{{{WORD_NS}}}tc" and cell is None:
                cell = ancestor
            if ancestor.tag == f"{{{WORD_NS}}}tr" and row is None:
                row = ancestor
            if ancestor.tag == f"{{{WORD_NS}}}tbl":
                table = ancestor
                break
            ancestor = parents.get(ancestor)
        if table is not None:
            locator["table_index"] = table_indices[table]
            if row is not None:
                locator["row_index"] = table.findall("./w:tr", NS).index(row) + 1
            if row is not None and cell is not None:
                locator["cell_index"] = row.findall("./w:tc", NS).index(cell) + 1

        fragments.append({
            "id": f"assignment-p{paragraph_index:04d}",
            "locator": locator,
            "style": style,
            "heading_context": heading,
            "text": text,
        })

    return {
        "extraction_version": "docx-body-xml-v1",
        "source_name": source.name,
        "source_sha256": checksum,
        "source_bytes": len(source_bytes),
        "locator_note": "All indices are 1-based and valid only for this source checksum; no page numbers are inferred.",
        "limitations": [
            "Only word/document.xml text nodes are extracted; headers, footers, image pixels, and page layout are not read.",
            "Text run order is preserved without correction; semantic accuracy and reading order require comparison with the rendered source.",
            "The assignment brief is not a study-material or OCR benchmark.",
        ],
        "structure": {
            "paragraphs": len(paragraphs),
            "nonempty_paragraphs": len(fragments),
            "tables": len(tables),
            "embedded_media": len(media),
            "body_drawings": len(body.findall(".//w:drawing", NS)),
            "body_math_nodes": len(body.findall(".//m:oMath", NS)),
            "text_characters": sum(len(fragment["text"]) for fragment in fragments),
            "paragraph_styles": dict(styles),
        },
        "fragments": fragments,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = extract(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "sha256": result["source_sha256"], "structure": result["structure"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
