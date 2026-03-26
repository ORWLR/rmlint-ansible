import threading
import time
import logging
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from db_utils import get_db_connection, setup_database, save_instruments

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')
logger = logging.getLogger(__name__)

class IBapi(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.instruments = []
        self.req_complete = False

    def contractDetails(self, reqId, contractDetails):
        """
        Callback when contract details are received from TWS/Gateway.
        """
        inst = {
            'con_id': contractDetails.contract.conId,
            'symbol': contractDetails.contract.symbol,
            'sec_type': contractDetails.contract.secType,
            'exchange': contractDetails.contract.primaryExchange or contractDetails.contract.exchange,
            'currency': contractDetails.contract.currency,
            'local_symbol': contractDetails.contract.localSymbol,
            'trading_class': contractDetails.contract.tradingClass,
            'name': contractDetails.longName,
            'industry': contractDetails.industry,
            'category': contractDetails.category,
            'subcategory': contractDetails.subcategory,
            'time_zone_id': contractDetails.timeZoneId
        }
        self.instruments.append(inst)
        logger.info(f"Received details for: {inst['symbol']} ({inst['name']})")

    def contractDetailsEnd(self, reqId):
        """
        Callback when all contract details for a request have been received.
        """
        logger.info("Finished receiving contract details.")
        self.req_complete = True

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        """
        Callback for IB error messages. Many "errors" are just informational (like connection established).
        """
        if errorCode not in [2104, 2106, 2158]: # ignore common informational messages
            logger.error(f"Error. Id: {reqId} Code: {errorCode} Msg: {errorString}")
            # If there's a real error finding the contract, end the request early
            # 200 is 'No security definition has been found for the request'
            if errorCode == 200:
                self.req_complete = True

def run_loop(app):
    app.run()

def extract_ibapi_osl():
    """
    Connects to IB Gateway using the official API, requests Oslo Børs stocks,
    and saves the extracted details to the database.
    """
    # Initialize the app
    app = IBapi()

    # Connect to IB Gateway. By default paper trading uses port 4002.
    # Change port to 4001 for live trading if needed.
    app.connect('127.0.0.1', 4002, 123)

    # Start the socket in a thread
    api_thread = threading.Thread(target=run_loop, args=(app,), daemon=True)
    api_thread.start()

    # Wait for connection
    time.sleep(1)

    # Define a generic contract for OSL (Oslo Børs).
    # By omitting the specific symbol, we request multiple contracts matching the parameters.
    # Note: Interactive Brokers generally limits 'wildcard' or empty symbol searches,
    # so we often have to specify a symbol. For demonstration, we'll request a few major ones.
    symbols_to_fetch = ["EQNR", "DNB", "TEL", "NHY", "MOWI"]

    req_id = 1
    for symbol in symbols_to_fetch:
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = "OSL"
        contract.currency = "NOK"

        logger.info(f"Requesting details for {symbol} on OSL...")
        app.req_complete = False
        app.reqContractDetails(req_id, contract)
        req_id += 1

        # Wait until the request completes (or timeout after 10 seconds)
        timeout = 10
        start_time = time.time()
        while not app.req_complete and (time.time() - start_time) < timeout:
            time.sleep(0.1)

        if not app.req_complete:
             logger.warning(f"Timeout waiting for {symbol} details.")

    # Disconnect from IB
    app.disconnect()

    # Save to Database
    if app.instruments:
        try:
            logger.info("Connecting to DB to save instruments...")
            conn = get_db_connection()
            setup_database(conn)
            save_instruments(conn, app.instruments)
            conn.close()
            logger.info("Database save complete.")
        except Exception as e:
            logger.error(f"Failed to save to database: {e}")
    else:
        logger.info("No instruments extracted to save.")

if __name__ == "__main__":
    extract_ibapi_osl()
