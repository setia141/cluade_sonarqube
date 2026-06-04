from unittest.mock import patch, MagicMock
from app.payment_service import get_balance


def test_get_balance_returns_float():
    mock_response = MagicMock()
    mock_response.json.return_value = {"balance": 99.50}

    with patch("app.payment_service.requests.get", return_value=mock_response):
        result = get_balance("cust-1")

    assert result == 99.50

# NOTE: charge() and find_transactions() are NOT tested.
# The agent will detect uncovered lines and create tests for them.
