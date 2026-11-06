"""Import and export the game library in portable file formats."""

import csv
import enum
import io
import json
import logging
import re
import sqlite3
from contextlib import closing
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from defusedxml import ElementTree as SafeET
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ValidationError
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend.database.database import get_connection
from backend.realtime.hub import hub
from routes.games.routes import game_from_row, insert_game
from routes.games.schemas import Game, GameCreate

router = APIRouter(tags=["admin"])
logger = logging.getLogger(__name__)

MAX_IMPORT_BYTES = 10 * 1024 * 1024
MAX_IMPORT_GAMES = 5000
NULL_CELL = r"\N"
ESCAPED_NULL_CELL = r"\\N"
GAME_FIELDS = tuple(Game.model_fields)
IMPORT_FIELDS = set(GameCreate.model_fields)
LIST_FIELDS = {"screenshots", "trailers"}
FORMULA_PREFIXES = "=+-@"


class GameDataFormat(str, enum.Enum):
    JSON = "json"
    XML = "xml"
    CSV = "csv"
    MARKDOWN = "markdown"
    PDF = "pdf"


def _game_records() -> list[dict]:
    with closing(get_connection()) as connection:
        rows = connection.execute("SELECT * FROM games ORDER BY id").fetchall()
    return [game_from_row(row).model_dump(mode="json") for row in rows]


def _json_bytes(records: list[dict]) -> bytes:
    return json.dumps(
        {"format": "lcpgamecol.games", "version": 1, "games": records},
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")


def _xml_bytes(records: list[dict]) -> bytes:
    root = ET.Element("games", {"format": "lcpgamecol.games", "version": "1"})
    for record in records:
        game_element = ET.SubElement(root, "game")
        for field, value in record.items():
            element = ET.SubElement(game_element, field)
            if value is None:
                element.set("null", "true")
            elif isinstance(value, (list, dict)):
                element.set("encoding", "json")
                element.text = json.dumps(value, ensure_ascii=False)
            elif isinstance(value, bool):
                element.set("type", "boolean")
                element.text = "true" if value else "false"
            else:
                element.text = str(value)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _csv_cell(value):
    if value is None:
        return NULL_CELL
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    if not isinstance(value, str):
        return value
    if value == NULL_CELL:
        return ESCAPED_NULL_CELL
    if value.startswith("'") and _is_formula_cell(value[1:]):
        return "'" + value
    if _is_formula_cell(value):
        return "'" + value
    return value


def _is_formula_cell(value: str) -> bool:
    return value.lstrip(" \t\r\n").startswith(tuple(FORMULA_PREFIXES))


def _csv_bytes(records: list[dict]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=GAME_FIELDS, lineterminator="\r\n")
    writer.writeheader()
    for record in records:
        writer.writerow({field: _csv_cell(record.get(field)) for field in GAME_FIELDS})
    return output.getvalue().encode("utf-8-sig")


def _markdown_bytes(records: list[dict]) -> bytes:
    lines = ["# LCPGameCol game export", "", f"Games: {len(records)}", ""]
    for record in records:
        title = str(record.get("title") or "Untitled game").replace("\r", " ").replace("\n", " ")
        lines.extend(
            [
                f"## {title}",
                "",
                "```json",
                json.dumps(record, ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )
    return "\n".join(lines).encode("utf-8")


def _pdf_text(value) -> str:
    text = str(value if value is not None else "")
    return text.encode("cp1252", "backslashreplace").decode("cp1252")


def _pdf_bytes(records: list[dict]) -> bytes:
    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    cell_style = ParagraphStyle(
        "GameCell",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7,
        leading=9,
    )

    def paragraph(value, style=cell_style):
        return Paragraph(escape(_pdf_text(value)).replace("\n", "<br/>"), style)

    headings = ["Title", "Year", "Genre", "Platforms", "Rating", "Category"]
    table_data = [[paragraph(value, styles["Heading4"]) for value in headings]]
    for record in records:
        table_data.append(
            [
                paragraph(record.get("title")),
                paragraph(record.get("release_year")),
                paragraph(record.get("genre")),
                paragraph(record.get("platforms")),
                paragraph(record.get("esrb")),
                paragraph(record.get("category")),
            ]
        )

    pdf_buffer = io.BytesIO()
    document = SimpleDocTemplate(
        pdf_buffer,
        pagesize=landscape(A4),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title="LCPGameCol game library",
    )
    table = Table(
        table_data,
        colWidths=[72 * mm, 17 * mm, 42 * mm, 54 * mm, 24 * mm, 42 * mm],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#263c37")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#ccd4cf")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f4f1")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    document.build(
        [
            Paragraph("Game library", title_style),
            Paragraph(f"{len(records)} games · Importable JSON data is attached.", styles["BodyText"]),
            Spacer(1, 8),
            table,
        ]
    )

    rendered = PdfReader(io.BytesIO(pdf_buffer.getvalue()))
    writer = PdfWriter()
    writer.clone_document_from_reader(rendered)
    writer.add_attachment("games.json", _json_bytes(records))
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


EXPORTERS = {
    GameDataFormat.JSON: (_json_bytes, "application/json", "json"),
    GameDataFormat.XML: (_xml_bytes, "application/xml", "xml"),
    GameDataFormat.CSV: (_csv_bytes, "text/csv; charset=utf-8", "csv"),
    GameDataFormat.MARKDOWN: (_markdown_bytes, "text/markdown; charset=utf-8", "md"),
    GameDataFormat.PDF: (_pdf_bytes, "application/pdf", "pdf"),
}


def _records_from_value(value) -> list[dict]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        games = value.get("games")
        if isinstance(games, list):
            return games
        if "title" in value:
            return [value]
    raise ValueError("The file must contain a list of game records.")


def _parse_xml(data: bytes) -> list[dict]:
    if re.search(rb"<!DOCTYPE|<!ENTITY", data, re.IGNORECASE):
        raise ValueError("Document type and entity declarations are not allowed.")
    root = SafeET.fromstring(data)
    if root.tag != "games":
        raise ValueError("The XML root element must be <games>.")
    records = []
    for game_element in root.findall("game"):
        record = {}
        for element in game_element:
            if element.get("null") == "true":
                record[element.tag] = None
            elif element.get("encoding") == "json":
                record[element.tag] = json.loads(element.text or "null")
            elif element.get("type") == "boolean":
                record[element.tag] = (element.text or "").lower() == "true"
            else:
                record[element.tag] = element.text or ""
        records.append(record)
    return records


def _parse_csv(data: bytes) -> list[dict]:
    text = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    if not reader.fieldnames or not {"title", "genre", "release_year"}.issubset(reader.fieldnames):
        raise ValueError("CSV needs title, genre, and release_year columns.")
    records = []
    for row in reader:
        record = {}
        for field, value in row.items():
            if field not in IMPORT_FIELDS or value is None:
                continue
            if value == NULL_CELL:
                record[field] = None
                continue
            if value == ESCAPED_NULL_CELL:
                record[field] = NULL_CELL
                continue
            if value.startswith("''") and _is_formula_cell(value[2:]):
                value = value[1:]
            elif value.startswith("'") and _is_formula_cell(value[1:]):
                value = value[1:]
            if value.startswith("["):
                value = json.loads(value)
            elif field in LIST_FIELDS and not value:
                value = []
            record[field] = value
        records.append(record)
    return records


def _parse_markdown(data: bytes) -> list[dict]:
    text = data.decode("utf-8-sig")
    blocks = re.findall(
        r"(?im)^```json[ \t]*\r?\n(.*?)\r?\n```[ \t]*$",
        text,
        flags=re.DOTALL,
    )
    if not blocks:
        raise ValueError("Markdown must contain JSON game blocks exported by this app.")
    records = []
    for block in blocks:
        records.extend(_records_from_value(json.loads(block)))
    return records


def _parse_pdf(data: bytes) -> list[dict]:
    reader = PdfReader(io.BytesIO(data), strict=False)
    if reader.is_encrypted:
        raise ValueError("Encrypted PDFs are not supported.")
    attachments = reader.attachments
    attached_files = attachments.get("games.json")
    if not attached_files:
        raise ValueError("PDF import requires a PDF exported by this app.")
    attached_data = attached_files[0] if isinstance(attached_files, list) else attached_files
    return _records_from_value(json.loads(attached_data))


def _parse_records(data: bytes, file_format: GameDataFormat) -> list[dict]:
    if file_format is GameDataFormat.JSON:
        return _records_from_value(json.loads(data.decode("utf-8-sig")))
    if file_format is GameDataFormat.XML:
        return _parse_xml(data)
    if file_format is GameDataFormat.CSV:
        return _parse_csv(data)
    if file_format is GameDataFormat.MARKDOWN:
        return _parse_markdown(data)
    return _parse_pdf(data)


def _validate_records(records: list[dict]) -> list[GameCreate]:
    if not records:
        raise HTTPException(status_code=422, detail="The file contains no games.")
    if len(records) > MAX_IMPORT_GAMES:
        raise HTTPException(
            status_code=413,
            detail=f"Import at most {MAX_IMPORT_GAMES} games at a time.",
        )

    games = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise HTTPException(status_code=422, detail=f"Game {index} must be an object.")
        try:
            game = GameCreate.model_validate(record)
        except ValidationError as error:
            first_error = error.errors(include_url=False)[0]
            field = ".".join(str(part) for part in first_error["loc"])
            raise HTTPException(
                status_code=422,
                detail=f"Game {index}, {field}: {first_error['msg']}",
            ) from error
        values = game.model_dump()
        for field in ("platforms", "gamemodes", "editions"):
            items = values[field]
            if isinstance(items, list):
                values[field] = ", ".join(_database_label(item) for item in items)
        games.append(GameCreate.model_validate(values))
    return games


def _database_label(value) -> str:
    if isinstance(value, enum.Enum):
        return str(value.value)
    if isinstance(value, BaseModel):
        value = value.model_dump()
    if isinstance(value, dict):
        value = value.get("name") or value.get("value") or ""
    return str(value)


@router.get("/admin/games/export")
def export_games(file_format: GameDataFormat = Query(..., alias="format")) -> Response:
    records = _game_records()
    exporter, media_type, extension = EXPORTERS[file_format]
    content = exporter(records)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="games.{extension}"'},
    )


@router.post("/admin/games/import")
async def import_games(
    file: UploadFile = File(...),
    file_format: GameDataFormat = Query(..., alias="format"),
) -> dict[str, int | list[int]]:
    data = await file.read(MAX_IMPORT_BYTES + 1)
    await file.close()
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="Import files may not exceed 10 MiB.")
    if not data:
        raise HTTPException(status_code=422, detail="Choose a non-empty import file.")

    try:
        records = _parse_records(data, file_format)
    except (ValueError, TypeError, csv.Error, PdfReadError) as error:
        logger.info("Rejected %s game import (%s)", file_format.value, type(error).__name__)
        raise HTTPException(
            status_code=422,
            detail=f"Could not read a valid {file_format.value.upper()} game export.",
        ) from error
    except Exception as error:
        logger.info("Rejected %s game import (%s)", file_format.value, type(error).__name__)
        raise HTTPException(
            status_code=422,
            detail=f"Could not read a valid {file_format.value.upper()} game export.",
        ) from error

    games = _validate_records(records)
    try:
        with closing(get_connection()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            game_ids = [insert_game(connection, game) for game in games]
            connection.commit()
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=422, detail="The imported games violate a library constraint.") from error

    hub.publish("gameChanged", {"action": "imported", "game_id": None, "title": None})
    return {"imported": len(game_ids), "game_ids": game_ids}