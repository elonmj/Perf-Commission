@echo off
REM ============================================================================
REM run_pipeline.bat — Lanceur pour Windows Task Scheduler
REM
REM Cree 3 declencheurs (Triggers) dans le Planificateur de taches :
REM   - 08:00, 12:00, 18:00 chaque jour
REM
REM Le script verifie last_success.txt avant de relancer.
REM
REM Installation :
REM   1. Ouvrir le Planificateur de taches Windows (taskschd.msc)
REM   2. Creer une tache "LKA_Perf_Commissions"
REM   3. Declencheur : Quotidien, repeter a 08:00, 12:00, 18:00
REM   4. Action : Demarrer un programme
REM      Programme : D:\LKA\Perf_commissions\run_pipeline.bat
REM      Demarrer dans : D:\LKA\Perf_commissions
REM
REM Ou via PowerShell (en admin) :
REM   schtasks /Create /SC DAILY /TN "LKA_Perf_Commissions_08h" /TR "D:\LKA\Perf_commissions\run_pipeline.bat" /ST 08:00 /F
REM   schtasks /Create /SC DAILY /TN "LKA_Perf_Commissions_12h" /TR "D:\LKA\Perf_commissions\run_pipeline.bat" /ST 12:00 /F
REM   schtasks /Create /SC DAILY /TN "LKA_Perf_Commissions_18h" /TR "D:\LKA\Perf_commissions\run_pipeline.bat" /ST 18:00 /F
REM ============================================================================

cd /d D:\LKA\Perf_commissions

REM Activer l'environnement Python si necessaire (decommenter si venv)
REM call venv\Scripts\activate.bat

echo [%date% %time%] Lancement pipeline Perf_commissions >> logs\pipeline.log 2>&1

REM Creer le dossier logs si absent
if not exist logs mkdir logs

py -3 run_daily.py >> logs\pipeline.log 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo [%date% %time%] ECHEC pipeline >> logs\pipeline.log
) else (
    echo [%date% %time%] SUCCES pipeline >> logs\pipeline.log
)
