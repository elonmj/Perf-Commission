"""
scripts/convert_acquisition_to_json.py — Convertit le fichier Performance
Acquisition Json .xlsx en JSON.

Utilise Username comme clé unique (certains Id_unique sont dupliqués).

Usage :
  py -3 scripts/convert_acquisition_to_json.py
  py -3 scripts/convert_acquisition_to_json.py --input data/custom.xlsx
  py -3 scripts/convert_acquisition_to_json.py --output data/custom.json
"""

import sys
import json
import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
DEFAULT_INPUT = ROOT / "data" / "Performance Acquisition Json.xlsx"
DEFAULT_OUTPUT = ROOT / "data" / "pulse_acquisition.json"


def xlsx_to_json(input_path: Path, output_path: Path) -> dict:
    """
    Convertit le fichier xlsx en JSON indexé par Username.

    Chaque entrée contient : Type, Statu, Id_unique, et les colonnes
    de dates avec leurs valeurs.

    Parameters:
        input_path (Path): Chemin du fichier xlsx source.
        output_path (Path): Chemin du fichier JSON destination.

    Returns:
        dict: Le dictionnaire JSON produit.
    """
    print(f"  Lecture : {input_path.name}")
    df = pd.read_excel(input_path)

    # Nettoyage Username
    df["Username"] = df["Username"].astype(str).str.strip()
    df = df[df["Username"].notna() & (df["Username"] != "") & (df["Username"] != "nan")]

    # Dédupliquer sur Username (garder la dernière occurrence)
    n_before = len(df)
    df = df.drop_duplicates(subset=["Username"], keep="last")
    n_dupes = n_before - len(df)
    if n_dupes > 0:
        print(f"  {n_dupes} doublons Username supprimés")

    print(f"  {len(df)} agents uniques")

    # Construire le dictionnaire JSON indexé par Username
    result = {}
    for _, row in df.iterrows():
        username = row["Username"]
        entry = {}
        for col in df.columns:
            if col == "Username":
                continue
            val = row[col]
            # Convertir les NaN en None, les numpy int en int
            if pd.isna(val):
                entry[col] = None
            elif isinstance(val, (int, float)):
                entry[col] = int(val) if val == int(val) else float(val)
            else:
                entry[col] = str(val)
        result[username] = entry

    # Sauvegarder
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  JSON sauvegardé : {output_path.name}")
    print(f"  Taille : {output_path.stat().st_size / 1024:.1f} KB")

    return result


def main():
    """Point d'entrée principal du script de conversion."""
    parser = argparse.ArgumentParser(
        description="Convertir Performance Acquisition xlsx en JSON"
    )
    parser.add_argument(
        "--input", default=str(DEFAULT_INPUT),
        help="Fichier xlsx source",
    )
    parser.add_argument(
        "--output", default=str(DEFAULT_OUTPUT),
        help="Fichier JSON destination",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"ERREUR : fichier introuvable — {input_path}")
        sys.exit(1)

    print("=== Conversion xlsx → JSON ===\n")
    result = xlsx_to_json(input_path, output_path)
    print(f"\n  Total : {len(result)} entrées (clé = Username)")
    print("  Terminé.")


if __name__ == "__main__":
    main()
