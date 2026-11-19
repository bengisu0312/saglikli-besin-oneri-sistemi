import os
import warnings
import pandas as pd
import psycopg2
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

SAYISAL_SUTUNLAR = ["grams", "calories", "protein", "fat", "sat_fat", "fiber", "carbs"]
OZELLIKLER = ["calories", "protein", "fat", "carbs"]


def veritabani_baglantisi_al():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME", "SaglikliOneriDB"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "12345"),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
    )


def verileri_getir_ve_temizle():
    conn = veritabani_baglantisi_al()
    cur = conn.cursor()

    cur.execute("SELECT * FROM Besinler;")
    satirlar = cur.fetchall()
    sutun_isimleri = [desc[0] for desc in cur.description]

    cur.close()
    conn.close()

    df = pd.DataFrame(satirlar, columns=sutun_isimleri)

    for sutun in SAYISAL_SUTUNLAR:
        df[sutun] = df[sutun].replace("t", "0")
        df[sutun] = df[sutun].astype(str).str.replace(",", "", regex=False)
        df[sutun] = pd.to_numeric(df[sutun], errors="coerce")

    df.fillna(0, inplace=True)
    return df


def besinleri_listele(arama=None, limit=50):
    df = verileri_getir_ve_temizle()

    if arama:
        df = df[df["food"].astype(str).str.contains(arama.strip(), case=False, na=False)]

    sonuc_df = df[["food", "calories", "protein", "fat", "sat_fat", "carbs"]].head(limit)
    return sonuc_df.to_dict(orient="records")


def oneri_uret(besin_adi):
    df = verileri_getir_ve_temizle()

    eslesen = df[df["food"].astype(str).str.strip().str.lower() == besin_adi.strip().lower()]
    if eslesen.empty:
        raise LookupError(f"'{besin_adi}' veritabaninda bulunamadi.")

    hedef_satir = eslesen.iloc[0]
    secilen_besin_adi = str(hedef_satir["food"])
    hedef_kalori = float(hedef_satir["calories"])
    hedef_doymus_yag = float(hedef_satir["sat_fat"])

    saglikli_df = df[
        (df["calories"] < hedef_kalori) & (df["sat_fat"] <= hedef_doymus_yag)
    ].copy()
    saglikli_df.reset_index(drop=True, inplace=True)

    if saglikli_df.empty:
        raise ValueError(
            f"'{secilen_besin_adi}' icin daha dusuk kalori ve doymus yaga sahip alternatif bulunamadi."
        )

    komsu_sayisi = min(3, len(saglikli_df))

    scaler = StandardScaler()
    X_saglikli = scaler.fit_transform(saglikli_df[OZELLIKLER])

    knn_model = NearestNeighbors(n_neighbors=komsu_sayisi, metric="euclidean")
    knn_model.fit(X_saglikli)

    hedef_degerler = scaler.transform(eslesen.iloc[[0]][OZELLIKLER])
    mesafeler, komsu_indeksleri = knn_model.kneighbors(hedef_degerler)

    oneriler_detay = []
    oneriler_isimler = []

    for i in range(komsu_sayisi):
        komsu_idx = komsu_indeksleri[0][i]
        satir = saglikli_df.iloc[komsu_idx]
        oneri_adi = str(satir["food"])
        oneriler_isimler.append(oneri_adi)
        oneriler_detay.append(
            {
                "food": oneri_adi,
                "calories": float(satir["calories"]),
                "protein": float(satir["protein"]),
                "fat": float(satir["fat"]),
                "sat_fat": float(satir["sat_fat"]),
                "carbs": float(satir["carbs"]),
                "mesafe": round(float(mesafeler[0][i]), 4),
            }
        )

    kayit_isimleri = (oneriler_isimler + [None, None, None])[:3]

    conn_insert = veritabani_baglantisi_al()
    cur_insert = conn_insert.cursor()

    insert_sorgusu = """
        INSERT INTO Oneriler (secilen_besin, oneri_1, oneri_2, oneri_3)
        VALUES (%s, %s, %s, %s)
        RETURNING id, islem_tarihi;
    """
    cur_insert.execute(
        insert_sorgusu,
        (secilen_besin_adi, kayit_isimleri[0], kayit_isimleri[1], kayit_isimleri[2]),
    )
    kayit_id, islem_tarihi = cur_insert.fetchone()
    conn_insert.commit()

    cur_insert.close()
    conn_insert.close()

    return {
        "secilen_besin": {
            "food": secilen_besin_adi,
            "calories": hedef_kalori,
            "sat_fat": hedef_doymus_yag,
        },
        "oneriler": oneriler_detay,
        "veritabani_kayit_id": kayit_id,
        "islem_tarihi": islem_tarihi.isoformat() if islem_tarihi else None,
    }


def gecmis_onerileri_getir(limit=20):
    conn = veritabani_baglantisi_al()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, secilen_besin, oneri_1, oneri_2, oneri_3, islem_tarihi
        FROM Oneriler
        ORDER BY islem_tarihi DESC
        LIMIT %s;
        """,
        (limit,),
    )
    satirlar = cur.fetchall()

    cur.close()
    conn.close()

    return [
        {
            "id": s[0],
            "secilen_besin": s[1],
            "oneri_1": s[2],
            "oneri_2": s[3],
            "oneri_3": s[4],
            "islem_tarihi": s[5].isoformat() if s[5] else None,
        }
        for s in satirlar
    ]


if __name__ == "__main__":
    sonuc = oneri_uret("Fortified milk")
    secilen = sonuc["secilen_besin"]
    print(f"Secilen Sagliksiz Besin: {secilen['food']} (Kalori: {secilen['calories']}, Doymus Yag: {secilen['sat_fat']})")
    print("\n--- AKILLI ONERI SISTEMI CALISIYOR ---")
    for oneri in sonuc["oneriler"]:
        print(f"- {oneri['food']} (Kalori: {oneri['calories']})")
    print(f"\nBASARI: Sonuclar veritabanina kaydedildi! (Kayit ID: {sonuc['veritabani_kayit_id']})")