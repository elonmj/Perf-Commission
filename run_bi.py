"""
run_bi.py -- Point d'entree BI local (Zero-Touch).

Lance la generation des commissions en se connectant directement
a la base MySQL distante. Aucun fichier Excel source necessaire.

Configuration dans connections/config.py :
  AUTO_MODE = True   -> 3 derniers jours disponibles en base
  AUTO_MODE = False  -> plage manuelle (MANUAL_END_DATE / MANUAL_RANGE_DAYS)

Usage :
  Double-clic sur run_bi.py  (ou)  py -3 run_bi.py
"""

import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent


def main():
    print("=" * 60)
    print("  PERF COMMISSIONS -- Mode BI Local")
    print("=" * 60)

    sys.path.insert(0, str(ROOT))
    from connections.config import AUTO_MODE, AUTO_DAYS_RANGE, MANUAL_END_DATE, MANUAL_RANGE_DAYS

    if AUTO_MODE:
        print(f"  Mode : AUTO ({AUTO_DAYS_RANGE} derniers jours en base)")
    else:
        print(f"  Mode : MANUEL (fin={MANUAL_END_DATE}, range={MANUAL_RANGE_DAYS}j)")

    print(f"  Connexion a la base distante...")
    print()

    cmd = [sys.executable, str(ROOT / "scripts" / "05_commission.py")]
    result = subprocess.run(cmd, cwd=str(ROOT))

    if result.returncode != 0:
        print(f"\n  ERREUR : generation echouee (exit code {result.returncode})")
        sys.exit(1)

    print()
    print("=" * 60)
    print(f"  Fichiers generes dans : {ROOT / 'outputs'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
