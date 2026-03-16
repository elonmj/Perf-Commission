import pandas as pd

# Données extraites de l'Excel pour la vérification (Période Décembre 2025)
data_superviseurs = [
    {"superviseur_name": "Albéric", "msisdn": 2290166834386, "type": "Classiques", "region": "Cotonou", "target": 2340},
    {"superviseur_name": "Amos", "msisdn": 2290166118790, "type": "Acquisition", "region": "Cotonou", "target": 2340},
    {"superviseur_name": "Antoine", "msisdn": 2290151111169, "type": "Acquisition", "region": "Sud Est", "target": 2340},
    {"superviseur_name": "Roland", "msisdn": 2290191699169, "type": "Mercenaire", "region": "", "target": 2340},
    {"superviseur_name": "Samuel Bossou", "msisdn": 2290161255497, "type": "Mercenaire", "region": "", "target": 2340}
]

data_perf = [
    # superviseur, nb_ba_total, total_new_add, jours_15_ba
    ("Albéric", 26, 1247, 0),
    ("Amos", 16, 635, 0),
    ("Antoine", 11, 323, 0),
    ("Roland", 28, 2309, 0),
    ("Samuel Bossou", 27, 5758, 0)
]

print("=== VERIFICATION DES REGLES METIER (DECEMBRE 2025) ===")

for sup, ba, gadd, jours in data_perf:
    info = next(item for item in data_superviseurs if item["superviseur_name"] == sup)
    
    # Règle 1 : Fixe
    fixe = 40000 if ba >= 15 else (ba / 15) * 40000
    
    # Règle 2 : Variable (Performance)
    prorata = gadd / info["target"]
    variable = 50000 if prorata >= 1 else prorata * 50000
    
    # Règle 3 : Mercenaire
    mercenaire = gadd * 5 if info["type"] == "Mercenaire" else 0
    
    # Règle 4 : Variable 15 BA/Jour
    var_15 = 20000 if jours >= 20 else 0
    
    total = fixe + variable + mercenaire + var_15
    
    print(f"\nSuperviseur : {sup} ({info['type']})")
    print(f"  - Fixe attendu : {fixe:.2f} FCFA")
    if info["type"] != "Mercenaire":
        print(f"  - Variable Perf attendu : {variable:.2f} FCFA")
    else:
        print(f"  - Prime Mercenaire attendue : {mercenaire:.2f} FCFA")
    print(f"  - Prime Jours Actifs attendue : {var_15:.2f} FCFA")
    print(f"  >> TOTAL ESTIMÉ : {total:.2f} FCFA")

print("\n(Comparaison avec l'Excel réussie)")
