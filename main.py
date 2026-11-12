
import os
from pathlib import Path

import requests
import pandas as pd
import psycopg2
from dotenv import load_dotenv


# 1. CONFIGURATION


BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("API_KEY")
API_HOST = os.getenv("API_HOST")

LEAGUE_ID = 47

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST"),
    "port": os.getenv("POSTGRES_PORT"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "database": os.getenv("POSTGRES_DATABASE")
}

def validate_config():
    required = {
        "API_KEY": API_KEY,
        "API_HOST": API_HOST,
        **DB_CONFIG
    }

    missing = [key for key, value in required.items() if not value]

    if missing:
        raise ValueError(f"Missing environment variables: {missing}")



# 2. EXTRACT


def extract_standings():

    url = "https://free-api-live-football-data.p.rapidapi.com/football-get-standing-all"

    headers = {
        "x-rapidapi-key": API_KEY,
        "x-rapidapi-host": API_HOST
    }

    params = {
        "leagueid": LEAGUE_ID
    }

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    payload = response.json()

    standings = payload.get("response", {}).get("standing")

    if not isinstance(standings, list):
        raise ValueError("Invalid API response: standings list not found")

    if not standings:
        raise ValueError("API returned an empty standings list")

    print(f"Extracted {len(standings)} club records")

    return standings



# 3. TRANSFORM


def transform_standings(standings):

    columns = [
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
    ]

    rows = []

    for club in standings:

        record = (
            club["id"],
            club["idx"],
            club["name"],
            club["played"],
            club["wins"],
            club["draws"],
            club["losses"],
            club["scoresStr"],
            club["goalConDiff"],
            club["pts"]
        )

        rows.append(record)

    df = pd.DataFrame(rows, columns=columns)

    print(f"Transformation completed: {len(df)} rows, {len(df.columns)} columns")

    return df




# 4. LOAD

def load_standings(df):

    connector = psycopg2.connect(
        host=DB_CONFIG["host"],
        database=DB_CONFIG["database"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        port=int(DB_CONFIG["port"])
    )

    try:
        with connector:

            with connector.cursor() as cursor:

                # Check whether the target table exists

                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                        AND table_name = 'football_table'
                    );
                """)

                table_exists = cursor.fetchone()[0]

                if not table_exists:
                    raise ValueError("Target table does not exist")

                # Retrieve database columns

                cursor.execute("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                    AND table_name = 'football_table'
                    ORDER BY ordinal_position;
                """)

                table_columns = [row[0] for row in cursor.fetchall()]

                df_columns = list(df.columns)

                if df_columns != table_columns:
                    raise ValueError(
                        f"Column mismatch.\n"
                        f"DataFrame: {df_columns}\n"
                        f"Database: {table_columns}"
                    )

                # Prepare UPSERT query

                insert_query = """
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
                """

                records = list(
                    df.itertuples(index=False, name=None)
                )

                cursor.executemany(insert_query, records)

                print(f"Successfully processed {cursor.rowcount} records")

    finally:
        connector.close()



# 5. MAIN EXECUTION


def main():

    print("Starting Premier League ETL Pipeline...")

    validate_config()

    # Extract
    standings = extract_standings()

    # Transform
    df = transform_standings(standings)

    # Load
    load_standings(df)

    print("ETL Pipeline completed successfully!")


# 6. SCRIPT ENTRY POINT


if __name__ == "__main__":
    main()
