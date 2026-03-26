import logging
from ib_insync import IB, Stock
from db_utils import get_db_connection, setup_database, save_instruments

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')
logger = logging.getLogger(__name__)

def extract_ib_insync_osl():
    """
    Connects to IB Gateway using the ib_insync async library, requests
    Oslo Børs stocks, and saves the extracted details to the database.
    """
    ib = IB()

    try:
        # Connect to IB Gateway.
        # Ensure your gateway is running locally on port 4002 (default for paper trading)
        # and has "Enable ActiveX and Socket Clients" checked.
        logger.info("Connecting to IB Gateway...")
        ib.connect('127.0.0.1', 4002, clientId=124)
        logger.info("Connected.")

        # Like the official API, fetching "everything" at once without symbols
        # isn't generally supported, so we provide an initial set of prominent
        # tickers to demonstrate the extraction process.
        symbols_to_fetch = ["EQNR", "DNB", "TEL", "NHY", "MOWI"]

        instruments_data = []

        for symbol in symbols_to_fetch:
            logger.info(f"Requesting contract details for {symbol} on OSL...")

            # Create a simple Stock contract definition
            contract = Stock(symbol, 'OSL', 'NOK')

            # Fetch details
            details_list = ib.reqContractDetails(contract)

            if not details_list:
                logger.warning(f"No details found for {symbol}.")
                continue

            for details in details_list:
                inst = {
                    'con_id': details.contract.conId,
                    'symbol': details.contract.symbol,
                    'sec_type': details.contract.secType,
                    'exchange': details.contract.primaryExchange or details.contract.exchange,
                    'currency': details.contract.currency,
                    'local_symbol': details.contract.localSymbol,
                    'trading_class': details.contract.tradingClass,
                    'name': details.longName,
                    'industry': details.industry,
                    'category': details.category,
                    'subcategory': details.subcategory,
                    'time_zone_id': details.timeZoneId
                }
                instruments_data.append(inst)
                logger.info(f"Retrieved: {inst['symbol']} ({inst['name']})")

        # Save to Database
        if instruments_data:
            logger.info("Connecting to DB to save instruments...")
            conn = get_db_connection()
            setup_database(conn)
            save_instruments(conn, instruments_data)
            conn.close()
            logger.info("Database save complete.")
        else:
            logger.info("No instruments extracted to save.")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        # Ensure we disconnect cleanly
        if ib.isConnected():
            ib.disconnect()
            logger.info("Disconnected from IB Gateway.")

if __name__ == '__main__':
    extract_ib_insync_osl()
