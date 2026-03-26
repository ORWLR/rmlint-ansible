import pytest
from unittest.mock import MagicMock, patch
from db_utils import get_db_connection, setup_database, save_instruments
import psycopg2

def test_db_connection_params(monkeypatch):
    """Test that the DB connection uses environment variables correctly."""
    monkeypatch.setenv("DB_HOST", "testhost")
    monkeypatch.setenv("DB_PORT", "1234")
    monkeypatch.setenv("DB_NAME", "testdb")
    monkeypatch.setenv("DB_USER", "testuser")
    monkeypatch.setenv("DB_PASSWORD", "testpass")

    with patch("psycopg2.connect") as mock_connect:
        get_db_connection()
        mock_connect.assert_called_once_with(
            host="testhost",
            port="1234",
            dbname="testdb",
            user="testuser",
            password="testpass"
        )

def test_setup_database():
    """Test that the setup database function executes the CREATE TABLE query."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    # Setup the context manager for the cursor
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    setup_database(mock_conn)

    # Assert that execute was called
    mock_cursor.execute.assert_called_once()
    assert "CREATE TABLE IF NOT EXISTS instruments" in mock_cursor.execute.call_args[0][0]

    # Assert that commit was called
    mock_conn.commit.assert_called_once()

def test_save_instruments():
    """Test the save_instruments function with a list of dictionaries."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    # Setup context manager
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    test_instruments = [
        {
            'con_id': 12345,
            'symbol': 'EQNR',
            'sec_type': 'STK',
            'exchange': 'OSL',
            'currency': 'NOK',
            'local_symbol': 'EQNR',
            'trading_class': 'EQNR',
            'name': 'EQUINOR ASA',
            'industry': 'Energy',
            'category': 'Oil & Gas',
            'subcategory': 'Exploration & Production',
            'time_zone_id': 'Europe/Oslo'
        }
    ]

    with patch("db_utils.execute_values") as mock_execute_values:
        save_instruments(mock_conn, test_instruments)

        # Verify execute_values was called
        mock_execute_values.assert_called_once()

        # Check the query string
        query = mock_execute_values.call_args[0][1]
        assert "INSERT INTO instruments" in query
        assert "ON CONFLICT (con_id) DO UPDATE" in query

        # Check the values tuple that was passed
        values_passed = mock_execute_values.call_args[0][2]
        assert len(values_passed) == 1
        assert values_passed[0][0] == 12345  # con_id
        assert values_passed[0][1] == 'EQNR' # symbol
        # Ensure that the length of the tuple matches the number of columns inserted
        assert len(values_passed[0]) == 12 # con_id, symbol, sec_type, exchange, currency, local_symbol, trading_class, name, industry, category, subcategory, time_zone_id

        # Verify commit
        mock_conn.commit.assert_called_once()

def test_save_instruments_empty():
    """Test that save_instruments handles empty lists properly."""
    mock_conn = MagicMock()

    save_instruments(mock_conn, [])

    # Since list is empty, it should return early without executing queries
    mock_conn.cursor.assert_not_called()
    mock_conn.commit.assert_not_called()
