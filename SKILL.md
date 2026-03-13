# SKILL — Perf_commissions Pipeline

## Identity
- **Name**: Perf_commissions Daily Pipeline
- **Purpose**: Automated daily performance tracking (GADD/ADS) and commission calculation for LKA agents
- **Stack**: Python 3 · pandas · openpyxl · SQLAlchemy · PyMySQL · Gmail IMAP/SMTP

## Key Files

| File | Role |
|------|------|
| `connections/config.py` | All credentials, table names, Excel structure constants |
| `connections/connect.py` | SQLAlchemy engine factory |
| `mysql/setup_db.py` | Database DDL (3 tables) |
| `scripts/00_fetch_mail.py` | IMAP download from Gmail |
| `scripts/01_process.py` | Parse GLOBALE PERFORMANCE (openpyxl multi-row headers) |
| `scripts/02_compile.py` | Merge into cumulative wide-format Excel |
| `scripts/03_upload.py` | Initial full load to MySQL |
| `scripts/04_sync.py` | Daily UPSERT to MySQL |
| `scripts/05_commission.py` | Generate commission Excel with visible formulas |
| `scripts/06_send_report.py` | Email commission via Gmail SMTP SSL |
| `run_daily.py` | Orchestrator (all steps + flag file) |
| `run_pipeline.bat` | Windows Task Scheduler launcher |

## Critical Patterns

### GLOBALE PERFORMANCE Excel Structure
- Sheet: `WEEKLYGLOBAL`
- Row 4: merged date cells (pairs of columns per date)
- Row 5: column headers (cols 5-15 = agent info, cols 16+ = alternating GADD/ADS)
- Row 6+: data rows
- Must use openpyxl (not pandas) to read multi-row merged headers

### Cumulative Files (Wide Format)
- Header: `Username`, then date strings `DD/MM/YYYY`
- Values: integers (0 or count)
- Keyed by Username (user_name in agent info)

### MySQL UPSERT Pattern
```sql
INSERT INTO table (msisdn_momo, perf_date, metric)
VALUES (?, ?, ?)
ON DUPLICATE KEY UPDATE metric = VALUES(metric)
```

### Commission Excel Formulas
- GADD sheet: `=I{row}*Resume!$B$2` (references GADD rate in Resume sheet)
- ADS sheet: `=I{row}*Resume!$B$3` (references ADS rate in Resume sheet)
- Resume sheet: cross-sheet SUM formulas for totals

## Infrastructure
- MySQL 8.0 on Docker at `75.119.154.255:3306`
- Database: `lka_perf_commissions`
- Gmail: IMAP (993) + SMTP (465) with App Password auth
- Windows Task Scheduler: 3 triggers at 08:00, 12:00, 18:00
