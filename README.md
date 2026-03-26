# IBKR Data Extractor for OSL Tickers

This is a learning project intended to connect to Interactive Brokers (IB Gateway/TWS), extract ticker and instrument information for prominent stocks on Oslo Børs (OSL), and store them in a local TimescaleDB instance.

It provides two scripts for comparison:
1. `fetch_ibapi.py`: Uses the official low-level Interactive Brokers Python API (`ibapi`), requiring you to build wrappers to handle event callbacks.
2. `fetch_ib_insync.py`: Uses the popular third-party `ib_insync` library, offering an asynchronous, "pythonic" interface that allows directly requesting details without manually managing threads or wrappers.

## Prerequisites

1.  **IB Gateway / TWS**: Ensure it is installed and running locally.
2.  **TimescaleDB**: A PostgreSQL instance with the TimescaleDB extension running locally. You can customize the connection strings using environment variables.

## Project Setup

Install the required dependencies using pip:

```bash
pip install ibapi ib_insync psycopg2-binary
```

### Setting up IB Gateway for Paper Trading

By default, these scripts target **Paper Trading** on port **4002** to avoid accidentally sending live orders during algorithmic experiments.

To configure IB Gateway to accept API requests:

1.  Open IB Gateway and log in to your **Paper Trading** account.
2.  Go to `Configure` -> `Settings` -> `API` -> `Settings`.
3.  Ensure **Enable ActiveX and Socket Clients** is **checked**.
4.  Ensure **Socket port** is set to `4002`. (For live accounts, it's typically `4001`).
5.  If you intend to run the Python scripts from the same machine as the gateway, `127.0.0.1` is usually already in the Trusted IPs.

### Environment Variables for Database

The `db_utils.py` module uses `psycopg2` to connect to your TimescaleDB instance.
By default, it will look for a database named `trading` running locally on port `5432` with user/pass `postgres`/`postgres`.

You can modify these locally using environment variables:
```bash
export DB_HOST="localhost"
export DB_PORT="5432"
export DB_NAME="trading"
export DB_USER="postgres"
export DB_PASSWORD="mysecretpassword"
```

## Running the Extraction

To test the official Interactive Brokers API approach:
```bash
python fetch_ibapi.py
```

To test the `ib_insync` asynchronous approach:
```bash
python fetch_ib_insync.py
```

Both scripts request the same batch of sample OSL tickers, and rely on `db_utils.py` to create the table (if it doesn't exist) and perform an "upsert" (Insert or Update on Conflict based on the `con_id`) ensuring you don't generate duplicate entries!