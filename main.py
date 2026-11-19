from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from db_connect import (
    besinleri_listele,
    gecmis_onerileri_getir,
    oneri_uret,
    veritabani_baglantisi_al,
)

app = FastAPI(
    title="Saglikli Besin Oneri Sistemi API",
    description="PostgreSQL ve kNN tabanli saglikli besin alternatifi oneri servisi.",
)


class OneriIstegi(BaseModel):
    besin_adi: str = "Fortified milk"


@app.get("/")
def ana_sayfa():
    try:
        conn = veritabani_baglantisi_al()
        conn.close()
        return {
            "durum": "calisiyor",
            "veritabani": "bagli",
            "test_ekrani": "http://127.0.0.1:8000/docs",
        }
    except Exception as hata:
        raise HTTPException(status_code=500, detail=f"Veritabani baglanti hatasi: {hata}")


@app.get("/besinler")
def besin_listesi(
    arama: str | None = Query(default=None, description="Aramak istedigin besin adi (orn: milk)"),
    limit: int = Query(default=20, ge=1, le=500),
):
    try:
        return besinleri_listele(arama=arama, limit=limit)
    except Exception as hata:
        raise HTTPException(status_code=500, detail=str(hata))


@app.post("/oneri")
def saglikli_oneri_al(istek: OneriIstegi):
    try:
        return oneri_uret(istek.besin_adi)
    except LookupError as hata:
        raise HTTPException(status_code=404, detail=str(hata))
    except ValueError as hata:
        raise HTTPException(status_code=400, detail=str(hata))
    except Exception as hata:
        raise HTTPException(status_code=500, detail=str(hata))


@app.get("/gecmis")
def gecmis_oneriler(limit: int = Query(default=20, ge=1, le=200)):
    try:
        return gecmis_onerileri_getir(limit=limit)
    except Exception as hata:
        raise HTTPException(status_code=500, detail=str(hata))