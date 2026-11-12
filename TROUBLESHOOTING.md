
# PL-STANDINGS ETL PIPELINE
# TROUBLESHOOTING DOCUMENTATION

## Project Overview

This document records the errors encountered while developing and executing the PL-Standings ETL pipeline, the investigation carried out, the solutions implemented, and the technical lessons learned.

The pipeline extracts Premier League standings from an API, transforms the JSON response into a structured Pandas DataFrame, and loads the records into a PostgreSQL database.

Development environment:
- Operating System: Windows with WSL Ubuntu
- Programming Language: Python
- Data Processing: Pandas
- Database: PostgreSQL 18
- Database Connector: psycopg2
- API Client: Requests
- Configuration Management: python-dotenv

---

# 1. PYTHON PACKAGE INSTALLATION ERROR

### Error Encountered

When attempting to install Python dependencies using pip:

```bash
python3 -m pip install requests pandas psycopg2-binary python-dotenv
```

The installation failed with an externally-managed-environment error (PEP 668).

### Cause

Ubuntu manages its system Python installation and prevents pip from installing packages globally.

This restriction protects system-managed Python packages from being modified in ways that could affect the operating system.

### Investigation

The installation command was executed outside a virtual environment.

### Resolution

Created and activated a Python virtual environment.

```bash
python3 -m venv ~/.venv
source ~/.venv/bin/activate
```

Installed the required dependencies inside the virtual environment.

```bash
python3 -m pip install requests pandas psycopg2-binary python-dotenv
```

### Lesson Learned

Python virtual environments isolate project dependencies from the system Python installation.

They also make it easier to manage dependencies independently across different projects.

---

# 2. POSTGRESQL CONNECTION REFUSED ERROR

### Error Encountered

When executing `main.py`, the pipeline failed during the database loading stage.

```text
psycopg2.OperationalError:

connection to server at "localhost", port 5432 failed:
Connection refused
```

### Cause

The Python application was running inside WSL Ubuntu, while PostgreSQL was installed and running on Windows.

The application attempted to connect using `localhost`.

However, localhost inside WSL referred to the WSL environment rather than the Windows PostgreSQL server.

PostgreSQL was not installed or running inside WSL.

### Investigation

Checked the PostgreSQL service inside WSL.

```bash
sudo service postgresql status
```

Result:

```text
Unit postgresql.service could not be found.
```

Checked whether the PostgreSQL client was installed.

```bash
psql --version
```

Result:

```text
Command 'psql' not found.
```

Checked whether port 5432 was listening inside WSL.

```bash
sudo ss -ltnp | grep 5432
```

No output was returned.

Then investigated PostgreSQL on Windows.

Checked the PostgreSQL service:

```powershell
Get-Service *postgres*
```

Result:

```text
Running  postgresql-x64-18
```

Verified that PostgreSQL was listening on port 5432:

```powershell
Get-NetTCPConnection -LocalPort 5432 -State Listen
```

Checked the PostgreSQL server configuration:

```powershell
Get-Content "C:\Program Files\PostgreSQL\18\data\postgresql.conf" | Select-String "listen_addresses"
```

Result:

```text
listen_addresses = '*'
```

This confirmed that PostgreSQL was configured to listen on all network interfaces.

### Resolution

Identified the Windows host gateway address from WSL.

```bash
ip route show default
```

Result:

```text
default via 192.168.144.1 dev eth0
```

Updated the existing `.env` configuration:

```env
POSTGRES_HOST=192.168.144.1
POSTGRES_PORT=5432
```

The existing database name, username, and password were retained.

### Lesson Learned

When connecting applications running in WSL to services running on Windows, the appropriate Windows host network address must be used.

`localhost` does not always refer to the same environment when working across virtualised or isolated network environments.

---

# 3. WINDOWS FIREWALL BLOCKING THE CONNECTION

### Error Encountered

After updating the database host address, testing the connection from WSL returned:

```text
nc: connect to 192.168.144.1 port 5432 failed: Connection timed out
```

### Cause

PostgreSQL was running and listening on port 5432, but Windows Firewall was blocking incoming connections from WSL.

The Windows Wi-Fi network profile was configured as Public.

### Investigation

Checked the WSL IP address:

```bash
ip -4 addr show eth0
```

Result:

```text
inet 192.168.150.188/20
```

Identified the WSL subnet:

```text
192.168.144.0/20
```

Checked the Windows network profile:

```powershell
Get-NetConnectionProfile
```

Result:

```text
NetworkCategory: Public
```

### Resolution

Created a Windows Firewall inbound rule using PowerShell as Administrator.

```powershell
New-NetFirewallRule -DisplayName "PostgreSQL 18 from WSL" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5432 -RemoteAddress 192.168.144.0/20 -Profile Public
```

The rule allowed incoming TCP connections on port 5432 specifically from the WSL subnet.

Retested the connection from WSL:

```bash
nc -vz 192.168.144.1 5432
```

Result:

```text
Connection to 192.168.144.1 5432 port [tcp/postgresql] succeeded!
```

### Lesson Learned

A database server can be running and listening on the correct port but remain inaccessible because of operating system firewall restrictions.

Network connectivity and database authentication are separate layers that must both be configured correctly.

---

# 4. POSTGRESQL CLIENT AUTHENTICATION ERROR

### Error Encountered

After resolving the network connection, running the Python pipeline returned:

```text
psycopg2.OperationalError:

FATAL: no pg_hba.conf entry for host
"192.168.150.188",
user "football_user",
database "football_data",
no encryption
```

### Cause

The connection successfully reached PostgreSQL, but the server did not have a client authentication rule permitting connections from the WSL IP address.

PostgreSQL uses `pg_hba.conf` to control which clients can connect, which databases they can access, and which authentication methods they must use.

### Resolution

Opened the PostgreSQL authentication configuration file on Windows.

```powershell
notepad "C:\Program Files\PostgreSQL\18\data\pg_hba.conf"
```

Added the following authentication rule:

```text
host    football_data    football_user    192.168.144.0/20    scram-sha-256
```

This rule specified:

- Connection type: Host/TCP connection
- Database: football_data
- Database user: football_user
- Allowed client subnet: 192.168.144.0/20
- Authentication method: SCRAM-SHA-256

Saved the configuration file.

Restarted the PostgreSQL service:

```powershell
Restart-Service postgresql-x64-18
```

Executed the pipeline again.

The authentication error was resolved.

### Lesson Learned

PostgreSQL has its own client authentication and access-control configuration.

Allowing a connection through the operating system firewall does not automatically authorise that client to access a PostgreSQL database.

The firewall controls network access, while `pg_hba.conf` controls PostgreSQL client authentication.

---

# 5. DUPLICATE PRIMARY KEY ERROR

### Error Encountered

After successfully connecting to PostgreSQL, the pipeline failed during the loading stage.

```text
psycopg2.errors.UniqueViolation:

duplicate key value violates unique constraint
"football_table_pkey"

DETAIL: Key ("ID")=(9825) already exists.
```

### Cause

The records had already been inserted into `public.football_table` during earlier testing.

The existing loading function used a standard SQL INSERT statement.

When the pipeline was executed again, it attempted to insert records with IDs that already existed in the database.

PostgreSQL rejected the operation because the ID column was configured as the table's primary key.

A primary key must contain unique values.

### Resolution

Replaced the standard INSERT statement with an UPSERT operation using PostgreSQL's:

```sql
ON CONFLICT ("ID")
DO UPDATE SET
```

The updated SQL statement:

```sql
INSERT INTO public.football_table (
    "ID",
    "Position",
    "Team",
    "Matches Played",
    "Matches Won",
    "Matches Drawn",
    "Matches Lost",
    "GF-GA",
    "Goal Difference",
    "Points"
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)

ON CONFLICT ("ID")
DO UPDATE SET
    "Position" = EXCLUDED."Position",
    "Team" = EXCLUDED."Team",
    "Matches Played" = EXCLUDED."Matches Played",
    "Matches Won" = EXCLUDED."Matches Won",
    "Matches Drawn" = EXCLUDED."Matches Drawn",
    "Matches Lost" = EXCLUDED."Matches Lost",
    "GF-GA" = EXCLUDED."GF-GA",
    "Goal Difference" = EXCLUDED."Goal Difference",
    "Points" = EXCLUDED."Points";
```

The Python execution logic remained:

```python
cursor.executemany(insert_query, records)
```

### How UPSERT Works

1. If the incoming team ID does not exist, PostgreSQL inserts a new record.
2. If the incoming team ID already exists, PostgreSQL updates the existing record with the incoming values.
3. The operation prevents duplicate primary-key violations when the pipeline is executed repeatedly.

### Lesson Learned

Data pipelines should account for repeated executions.

UPSERT allows a pipeline to insert new records and update existing records without violating primary key constraints.

This supports idempotent loading behaviour.

---

# 6. FINAL PIPELINE EXECUTION

After resolving the errors and implementing UPSERT, the pipeline executed successfully.

The following stages were completed:

### Extraction

- Connected to the external football standings API.
- Sent the required API request.
- Retrieved the Premier League standings JSON response.

### Transformation

- Extracted the standings records from the API response.
- Selected the required fields.
- Renamed the fields into meaningful column names.
- Converted the records into a Pandas DataFrame.

### Loading

- Established a connection to PostgreSQL.
- Checked whether the target table existed.
- Retrieved the database column names.
- Validated the DataFrame columns against the database table columns.
- Prepared the records for insertion.
- Executed the UPSERT statement.
- Loaded the records into `public.football_table`.

### Final Outcome

The PL-Standings ETL pipeline successfully executed after the network, authentication, and duplicate-record issues were resolved.

The loading process now supports:

- Inserting new records.
- Updating existing records.
- Repeated pipeline execution without duplicate primary key errors.

---

# 7. POST-IMPLEMENTATION TESTING CHECKLIST

The following tests should be completed to validate the pipeline.

### Pipeline Execution

- [ ] Execute `main.py` successfully.
- [ ] Execute `main.py` a second time.
- [ ] Confirm that repeated executions do not produce duplicate primary key errors.

### Database Validation

Check the total number of records:

```sql
SELECT COUNT(*)
FROM public.football_table;
```

Check for duplicate IDs:

```sql
SELECT "ID", COUNT(*)
FROM public.football_table
GROUP BY "ID"
HAVING COUNT(*) > 1;
```

Expected result: Zero rows.

Inspect the loaded standings:

```sql
SELECT *
FROM public.football_table
ORDER BY "Position";
```

### UPSERT Validation

- [ ] Confirm that existing IDs do not create duplicate records.
- [ ] Verify that existing records are updated when incoming values change.
- [ ] Confirm that new IDs are inserted successfully.

---

# 8. TECHNICAL CONCEPTS LEARNED

The troubleshooting process involved the following concepts:

### Python and Environment Management
- Python virtual environments
- PEP 668
- Dependency management
- requirements.txt

### Networking and Connectivity
- WSL networking
- Windows host and guest connectivity
- IP addresses and subnets
- TCP ports
- Windows Firewall
- Network troubleshooting

### PostgreSQL Administration
- PostgreSQL services
- `listen_addresses`
- `pg_hba.conf`
- SCRAM-SHA-256 authentication
- Database connectivity
- Primary key constraints

### SQL and Data Loading
- INSERT statements
- UPSERT
- ON CONFLICT
- EXCLUDED
- Database transactions
- Idempotency
- Duplicate record handling

### Python Database Integration
- psycopg2
- Database connections
- Cursors
- executemany()
- Exception handling
- Connection management

---


