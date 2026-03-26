import os
import psycopg2
from psycopg2.extras import execute_values
import logging

logger = logging.getLogger(__name__)

def get_db_connection():
    """
    Connect to the TimescaleDB database.
    Configuration is read from environment variables, with defaults.
    """
    try:
        conn = psycopg2.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=os.environ.get("DB_PORT", "5432"),
            dbname=os.environ.get("DB_NAME", "trading"),
            user=os.environ.get("DB_USER", "postgres"),
            password=os.environ.get("DB_PASSWORD", "postgres")
        )
        return conn
    except Exception as e:
        logger.error(f"Error connecting to database: {e}")
        raise

def setup_database(conn):
    """
    Creates the necessary tables if they do not exist.
    """
    with conn.cursor() as cur:
        # Create table for instruments
        cur.execute("""
            CREATE TABLE IF NOT EXISTS instruments (
                con_id BIGINT PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                sec_type VARCHAR(10),
                exchange VARCHAR(20),
                currency VARCHAR(10),
                local_symbol VARCHAR(50),
                trading_class VARCHAR(50),
                name VARCHAR(255),
                industry VARCHAR(100),
                category VARCHAR(100),
                subcategory VARCHAR(100),
                time_zone_id VARCHAR(50),
                last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

def save_instruments(conn, instruments):
    """
    Upserts a list of instrument dictionaries into the database.

    Args:
        conn: psycopg2 connection object
        instruments: List of dictionaries containing instrument details
    """
    if not instruments:
        return

    query = """
        INSERT INTO instruments (
            con_id, symbol, sec_type, exchange, currency,
            local_symbol, trading_class, name, industry,
            category, subcategory, time_zone_id
        ) VALUES %s
        ON CONFLICT (con_id) DO UPDATE SET
            symbol = EXCLUDED.symbol,
            sec_type = EXCLUDED.sec_type,
            exchange = EXCLUDED.exchange,
            currency = EXCLUDED.currency,
            local_symbol = EXCLUDED.local_symbol,
            trading_class = EXCLUDED.trading_class,
            name = EXCLUDED.name,
            industry = EXCLUDED.industry,
            category = EXCLUDED.category,
            subcategory = EXCLUDED.subcategory,
            time_zone_id = EXCLUDED.time_zone_id,
            last_updated = CURRENT_TIMESTAMP;
    """

    # Extract values from dictionaries in the correct order
    values = [
        (
            inst.get('con_id'),
            inst.get('symbol'),
            inst.get('sec_type'),
            inst.get('exchange'),
            inst.get('currency'),
            inst.get('local_symbol'),
            inst.get('trading_class'),
            inst.get('name'),
            inst.get('industry'),
            inst.get('category'),
            inst.get('subcategory'),
            inst.get('time_zone_id')
        ) for inst in instruments
    ]

    try:
        with conn.cursor() as cur:
            execute_values(cur, query, values)
        conn.commit()
        logger.info(f"Successfully saved {len(instruments)} instruments to database.")
    except Exception as e:
        logger.error(f"Error saving instruments to database: {e}")
        conn.rollback()
        raise

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        conn = get_db_connection()
        setup_database(conn)
        logger.info("Database setup complete.")
        conn.close()
    except Exception as e:
        logger.error(f"Failed to setup database: {e}")
