"""DANE: proyecciones municipales de población por área.

Fuente oficial: serie municipal 2018-2042 por área geográfica, con base CNPV
2018. Se usa para enriquecer municipios en el área de influencia del sismo.
"""
from __future__ import annotations

import json
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict

from common import fetch, PUBLIC

URL = ("https://www.dane.gov.co/files/censo2018/proyecciones-de-poblacion/"
       "Municipal/PPED-AreaMun-2018-2042_VP.xlsx")
YEAR = 2026

NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "rel": "http://schemas.openxmlformats.org/package/2006/relationships"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


def _shared_strings(z: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    vals = []
    for si in root.findall("a:si", NS):
        vals.append("".join(t.text or "" for t in si.findall(".//a:t", NS)))
    return vals


def _sheet_path(z: zipfile.ZipFile, sheet_name: str) -> str:
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rid_to_target = {r.attrib["Id"]: r.attrib["Target"] for r in rels.findall("rel:Relationship", NS)}
    for s in wb.findall(".//a:sheet", NS):
        if s.attrib.get("name") == sheet_name:
            rid = s.attrib.get(f"{{{NS['r']}}}id")
            target = rid_to_target[rid]
            return "xl/" + target.lstrip("/")
    raise KeyError(sheet_name)


def _cell_value(c: ET.Element, shared: list[str]):
    t = c.attrib.get("t")
    v = c.find("a:v", NS)
    if v is None:
        inline = c.find("a:is", NS)
        if inline is not None:
            return "".join(x.text or "" for x in inline.findall(".//a:t", NS))
        return None
    raw = v.text or ""
    if t == "s":
        return shared[int(raw)]
    if t == "str":
        return raw
    try:
        n = float(raw)
        return int(n) if n.is_integer() else n
    except ValueError:
        return raw


def _rows_xlsx(body: bytes, sheet_name="PobMunicipalxÁrea"):
    with zipfile.ZipFile(__import__("io").BytesIO(body)) as z:
        shared = _shared_strings(z)
        sheet = ET.fromstring(z.read(_sheet_path(z, sheet_name)))
        for row in sheet.findall(".//a:row", NS):
            vals = {}
            for c in row.findall("a:c", NS):
                ref = c.attrib.get("r", "")
                m = re.match(r"([A-Z]+)", ref)
                if not m:
                    continue
                # A=0, B=1... suficiente para esta hoja
                col = 0
                for ch in m.group(1):
                    col = col * 26 + ord(ch) - ord("A") + 1
                vals[col - 1] = _cell_value(c, shared)
            if vals:
                yield [vals.get(i) for i in range(max(vals) + 1)]


def parse_population_2026(body: bytes) -> dict:
    header = None
    out = defaultdict(dict)
    for row in _rows_xlsx(body):
        if row[:7] == ["DP", "DPNOM", "MPIO", "DPMP", "AÑO", "ÁREA GEOGRÁFICA", "TOTAL"]:
            header = row
            continue
        if not header or len(row) < 7 or row[4] != YEAR:
            continue
        depto, divipola, municipio, area, total = row[1], str(row[2]), row[3], row[5], row[6]
        key = f"{_norm(municipio)}|{_norm(depto)}"
        rec = out[key]
        rec.update({"municipio": municipio, "departamento": depto, "divipola": divipola})
        if area == "Total":
            rec["poblacion_2026"] = int(total)
        elif area == "Cabecera Municipal":
            rec["cabecera_2026"] = int(total)
        elif area == "Centros Poblados y Rural Disperso":
            rec["rural_2026"] = int(total)
    return dict(out)


def run() -> dict:
    status, body = fetch(URL, note="dane poblacion municipal 2018-2042",
                         snapshot_name="dane_poblacion_municipal_2018_2042.xlsx",
                         binary=True, retries=1)
    if status != 200 or not body:
        return {"error": f"DANE HTTP {status}"}
    data = parse_population_2026(body)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (PUBLIC / "dane_population_2026.json").write_text(json.dumps({
        "fuente": URL,
        "anio": YEAR,
        "descripcion": "DANE PPED, serie municipal de población por área 2018-2042",
        "items": data,
    }, ensure_ascii=False))
    return {"municipios": len(data), "anio": YEAR}


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, ensure_ascii=False))
