import sys
import os
import pandas as pd
from sqlalchemy import text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from connections.connect import make_engine

engine = make_engine()
with engine.connect() as conn:
    print("----- Agent Info Sample -----")
    res = conn.execute(text("SELECT superviseur, COUNT(user_name) as nb_agents, MIN(real_channel) as chnl FROM agent_info GROUP BY superviseur")).fetchall()
    for r in res:
        print(f"Sup: {r[0]}, Agents: {r[1]}, Type: {r[2]}")
    
    print("\n----- Tables & Views -----")
    tables = conn.execute(text("SHOW TABLES")).fetchall()
    for t in tables: print(t[0])
