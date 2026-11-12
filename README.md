# PL Standings: Premier League ETL Pipeline

A small Python ETL pipeline that pulls the current Premier League table from a football data API, reshapes it into a clean tabular format, and loads it into a PostgreSQL table.

## What it does

| Stage | What happens |
| --- | --- |
| **Extract** | Calls the RapidAPI "Free API Live Football Data" standings endpoint for the Premier League (`leagueid=47`). |
| **Transform** | Picks the fields needed, renames them, and builds a pandas DataFrame (one row per club). |
| **Load** | Checks the DataFrame matches the target table, then upserts the rows into `public.football_table`. |

The load uses `INSERT ... ON CONFLICT ("ID") DO UPDATE`, so the pipeline is idempotent: running it again updates existing clubs instead of failing on duplicate keys.

## Project structure

```
PL-Standings/
├── main.py               # The full ETL pipeline
├── test.ipynb            # Step-by-step notebook version with inspection and debug cells
├── requirements.txt      # Python dependencies
├── TROUBLESHOOTING.md    # Errors hit during development and how they were fixed
├── .gitignore            # Excludes .env, virtual environments, caches
├── .env                  # Your credentials (not committed)
└── README.md
```

- **`main.py`** is the version to run. It validates config, enforces HTTP errors and timeouts, and upserts.
- **`test.ipynb`** walks through each stage interactively. It is useful for exploring the API response. It only inserts, so re-running its Load section fails on duplicate IDs if the table has a primary key (see [TROUBLESHOOTING.md](TROUBLESHOOTING.md)).

## Prerequisites

- Python 3.8+
- A running PostgreSQL database
- A RapidAPI key subscribed to the Free API Live Football Data API
- The target table `public.football_table` already created (see below)

## Setup

1. **Clone the repo**

   ```bash
   git clone <your-repo-url>
   cd PL-Standings
   ```

2. **Create a virtual environment and install dependencies**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

   Using a virtual environment avoids the `externally-managed-environment` (PEP 668) error on Ubuntu and WSL.

3. **Create a `.env` file** in the project root:

   ```env
   API_KEY=your_rapidapi_key
   API_HOST=free-api-live-football-data.p.rapidapi.com

   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432
   POSTGRES_USER=your_user
   POSTGRES_PASSWORD=your_password
   POSTGRES_DATABASE=your_database
   ```

   `.env` is listed in `.gitignore`, so your keys stay out of version control.

4. **Create the target table**

   Column names and order must match exactly, because the script compares them before loading. `"ID"` must be the primary key (or have a unique constraint) for the upsert to work.

   ```sql
   CREATE TABLE public.football_table (
       "ID"              INTEGER PRIMARY KEY,
       "Position"        INTEGER,
       "Team"            TEXT,
       "Matches Played"  INTEGER,
       "Matches Won"     INTEGER,
       "Matches Drawn"   INTEGER,
       "Matches Lost"    INTEGER,
       "GF-GA"           TEXT,
       "Goal Difference" INTEGER,
       "Points"          INTEGER
   );
   ```

## Running on WSL with PostgreSQL on Windows

If the script runs in WSL but PostgreSQL is installed on Windows, `localhost` will not reach the database. Three things need to line up:

1. **Host address.** Use the Windows host gateway as `POSTGRES_HOST`. Find it from WSL with:

   ```bash
   ip route show default
   ```

   Then set `POSTGRES_HOST` in `.env` to the address after `via`.

2. **Windows Firewall.** Allow inbound TCP on port 5432 from the WSL subnet (run PowerShell as Administrator, adjusting the subnet to yours):

   ```powershell
   New-NetFirewallRule -DisplayName "PostgreSQL from WSL" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5432 -RemoteAddress 192.168.144.0/20 -Profile Public
   ```

3. **PostgreSQL client authentication.** Add a rule to `pg_hba.conf` for the WSL subnet, then restart the PostgreSQL service:

   ```text
   host    your_database    your_user    192.168.144.0/20    scram-sha-256
   ```

   Also confirm `listen_addresses = '*'` in `postgresql.conf`.

The WSL gateway and subnet can change after a restart, so recheck them if the connection starts failing. Full diagnosis steps are in [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Usage

```bash
python main.py
```

Expected output:

```
Starting Premier League ETL Pipeline...
Extracted 20 club records
Transformation completed: 20 rows, 10 columns
Successfully processed 20 records
ETL Pipeline completed successfully!
```

Run it a second time to confirm it completes without duplicate key errors.

## Verifying the load

```sql
-- Should return 20
SELECT COUNT(*) FROM public.football_table;

-- Should return zero rows
SELECT "ID", COUNT(*)
FROM public.football_table
GROUP BY "ID"
HAVING COUNT(*) > 1;

-- Inspect the table
SELECT * FROM public.football_table ORDER BY "Position";
```

## Data mapping

| API field | Column | Meaning |
| --- | --- | --- |
| `id` | `ID` | Club ID |
| `idx` | `Position` | Table position |
| `name` | `Team` | Club name |
| `played` | `Matches Played` | Matches played |
| `wins` | `Matches Won` | Matches won |
| `draws` | `Matches Drawn` | Matches drawn |
| `losses` | `Matches Lost` | Matches lost |
| `scoresStr` | `GF-GA` | Goals for-against, e.g. `15-5` (kept as text) |
| `goalConDiff` | `Goal Difference` | Goal difference |
| `pts` | `Points` | League points |

## Error handling

`main.py` stops with a clear message when:

- Any required environment variable is missing
- The API returns a non-200 status or takes longer than 30 seconds
- The response has no standings list, or the list is empty
- The target table does not exist
- The DataFrame columns do not match the table columns

The database write runs inside a transaction, so a failure rolls the whole batch back and never leaves the table half-loaded.

## Troubleshooting

Common problems and fixes are documented in [TROUBLESHOOTING.md](TROUBLESHOOTING.md):

| Symptom | Likely cause |
| --- | --- |
| `externally-managed-environment` on `pip install` | Not using a virtual environment |
| `Connection refused` on port 5432 | WSL `localhost` is not the Windows host |
| `Connection timed out` | Windows Firewall blocking the WSL subnet |
| `no pg_hba.conf entry for host` | Missing client authentication rule |
| `duplicate key value violates unique constraint` | Using plain `INSERT` instead of the upsert (for example, the notebook) |

## Changing the league

Set `LEAGUE_ID` in `main.py` to the ID of another league supported by the API. The default, `47`, is the Premier League.

## Known limitations and ideas

- **No snapshot history.** Each run overwrites the current standings. Add a `fetched_at` column or a history table to track the table over time.
- **No retries.** A 429 or 5xx response fails the run. Consider adding retry logic.
- **Manual runs.** Schedule it with cron, Task Scheduler, or Airflow to keep the table fresh.
- **Notebook path.** `test.ipynb` has a hard-coded fallback `.env` path (`/home/user/PL-Standings/.env`). Change it to your own location before running that cell.

## Tech stack

Python, pandas, requests, psycopg2, python-dotenv, PostgreSQL, RapidAPI
