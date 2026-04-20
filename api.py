from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from datetime import date
import os
import sys

from sqlalchemy import text
from dotenv import load_dotenv

# Charger les variables d'environnement globales
ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(ROOT, ".env"))

sys.path.insert(0, ROOT)
from connections.connect import make_engine

app = FastAPI(title="API Performances LKA", description="API connectée à MySQL pour récupérer les performances avec l'ID Pulse")

cors_origins = [
    origin.strip()
    for origin in os.environ.get("PERF_API_CORS_ORIGINS", "*").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    engine = make_engine()
except Exception as e:
    engine = None
    print(f"Attention, connexion BD échouée à l'initialisation: {e}")

@app.get("/api/performances/{id_pulse}")
def get_performance(
    id_pulse: str, 
    start_date: Optional[date] = Query(None, description="Date de début (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Date de fin (YYYY-MM-DD)"),
    include_details: bool = Query(False, description="Inclure le détail journalier")
):
    if engine is None:
        raise HTTPException(status_code=500, detail="Erreur de connexion à la base de données")
        
    with engine.connect() as conn:
        # 1. Rechercher l'utilisateur avec l'ID Pulse
        res_user = conn.execute(text(
            "SELECT user_name, agent_name FROM lka_client_mtn.lka_usernames WHERE id_pulse = :id_pulse LIMIT 1"
        ), {"id_pulse": id_pulse}).fetchone()

        if not res_user:
            raise HTTPException(status_code=404, detail=f"Aucun utilisateur trouvé pour l'ID Pulse {id_pulse}")
        
        user_name, agent_name = res_user

        # 2. Construire les requêtes de base
        query_gadd = "SELECT perf_date, gadd FROM daily_gadd WHERE user_name = :un"
        query_ads = "SELECT perf_date, ads FROM daily_ads WHERE user_name = :un"
        params = {"un": user_name}

        # 3. Ajouter les filtres de dates si fournis
        if start_date:
            query_gadd += " AND perf_date >= :start_date"
            query_ads += " AND perf_date >= :start_date"
            params["start_date"] = start_date
        
        if end_date:
            query_gadd += " AND perf_date <= :end_date"
            query_ads += " AND perf_date <= :end_date"
            params["end_date"] = end_date

        # Trier par date
        query_gadd += " ORDER BY perf_date ASC"
        query_ads += " ORDER BY perf_date ASC"

        # 4. Exécuter
        records_gadd = conn.execute(text(query_gadd), params).fetchall()
        records_ads = conn.execute(text(query_ads), params).fetchall()

    total_gadd = sum((row[1] or 0) for row in records_gadd)
    total_ads = sum((row[1] or 0) for row in records_ads)

    response = {
        "success": True,
        "id_pulse": id_pulse,
        "user_name": user_name,
        "agent_name": agent_name,
        "filtres_appliques": {
            "start_date": start_date,
            "end_date": end_date
        },
        "total": {
            "gadd": total_gadd,
            "ads": total_ads,
        },
    }

    if include_details:
        performances = {}

        for row in records_gadd:
            d = row[0].isoformat()
            if d not in performances:
                performances[d] = {"gadd": 0, "ads": 0}
            performances[d]["gadd"] = row[1]

        for row in records_ads:
            d = row[0].isoformat()
            if d not in performances:
                performances[d] = {"gadd": 0, "ads": 0}
            performances[d]["ads"] = row[1]

        response["performances"] = performances

    return response

@app.get("/")
def read_root():
    return {"message": "API Performances LKA est en ligne (Connectée à MySQL).", "docs": "/docs"}
