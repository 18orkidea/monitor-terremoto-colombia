"""Regresiones de la ingesta ciudadana que necesitan una corrida completa."""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "ingest"))
sys.path.insert(0, str(ROOT / "ingest" / "sources"))

import common
import chatmap


class _SinCerrar:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, nombre):
        return getattr(self._conn, nombre)

    def close(self):
        pass


class _Respuesta:
    status = 200
    headers = {}

    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class TestActualizacionDeCoordenadas(unittest.TestCase):
    def test_una_corrida_repara_el_redondeo_historico(self):
        """R5 también rige para filas existentes, no solo para altas nuevas."""
        lat, lon = 3.407633492061677, -76.55279292639023
        cuerpo = json.dumps({"features": [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"id": "reporte-existente",
                           "time": "2026-08-13T14:18:00", "file": ""},
        }]}).encode()

        conn = sqlite3.connect(":memory:")
        conn.executescript(common.SCHEMA)
        conn.execute(
            "INSERT INTO citizen_reports (origen, id_externo, ts, lat, lon,"
            " lat_pub, lon_pub, estado, snapshot_date)"
            " VALUES ('chatmap','reporte-existente','2026-08-13T14:18:00',"
            " ?,?,ROUND(?,3),ROUND(?,3),'recibido','2026-08-23')",
            (lat, lon, lat, lon))

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            media = tmp / "data" / "media"
            media.mkdir(parents=True)
            with mock.patch.object(chatmap, "db", lambda: _SinCerrar(conn)), \
                    mock.patch.object(chatmap, "MEDIA", media), \
                    mock.patch.object(common, "ROOT", tmp), \
                    mock.patch.object(common, "SNAPSHOTS",
                                      tmp / "data" / "snapshots"), \
                    mock.patch.object(common, "MANIFIESTO_R2",
                                      tmp / "data" / "r2_manifest.json"), \
                    mock.patch.object(common.urllib.request, "urlopen",
                                      return_value=_Respuesta(cuerpo)):
                chatmap.run(download_media=False)

        publicado = conn.execute(
            "SELECT lat, lon, lat_pub, lon_pub FROM citizen_reports"
            " WHERE id_externo='reporte-existente'").fetchone()
        self.assertEqual(publicado, (lat, lon, lat, lon))
        conn.close()


if __name__ == "__main__":
    unittest.main()
