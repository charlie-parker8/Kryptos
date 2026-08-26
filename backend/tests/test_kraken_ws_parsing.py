from decimal import Decimal

from app.market_data.kraken import parse_ticker_message


def test_parses_a_ticker_snapshot_message() -> None:
    payload = {
        "channel": "ticker",
        "type": "snapshot",
        "data": [
            {
                "symbol": "BTC/USD",
                "bid": 49995.0,
                "ask": 50005.0,
                "last": 50000.0,
                "volume": 123.4,
            }
        ],
    }

    tickers = parse_ticker_message(payload)

    assert len(tickers) == 1
    ticker = tickers[0]
    assert ticker.pair == "BTC/USD"
    assert ticker.bid == Decimal("49995.0")
    assert ticker.ask == Decimal("50005.0")
    assert ticker.last == Decimal("50000.0")


def test_parses_a_ticker_update_message() -> None:
    payload = {
        "channel": "ticker",
        "type": "update",
        "data": [{"symbol": "ETH/USD", "bid": 3000, "ask": 3001, "last": 3000.5}],
    }

    tickers = parse_ticker_message(payload)

    assert len(tickers) == 1
    assert tickers[0].pair == "ETH/USD"


def test_parses_multiple_tickers_in_one_message() -> None:
    payload = {
        "channel": "ticker",
        "type": "snapshot",
        "data": [
            {"symbol": "BTC/USD", "bid": 1, "ask": 2, "last": 1.5},
            {"symbol": "ETH/USD", "bid": 3, "ask": 4, "last": 3.5},
        ],
    }

    tickers = parse_ticker_message(payload)

    assert [t.pair for t in tickers] == ["BTC/USD", "ETH/USD"]


def test_ignores_a_subscribe_acknowledgement() -> None:
    payload = {
        "method": "subscribe",
        "result": {"channel": "ticker", "symbol": "BTC/USD"},
        "success": True,
    }

    assert parse_ticker_message(payload) == []


def test_ignores_a_heartbeat() -> None:
    assert parse_ticker_message({"channel": "heartbeat"}) == []


def test_ignores_a_non_ticker_channel() -> None:
    payload = {"channel": "book", "type": "snapshot", "data": [{"symbol": "BTC/USD"}]}
    assert parse_ticker_message(payload) == []


def test_skips_a_malformed_entry_without_dropping_the_rest_of_the_batch() -> None:
    payload = {
        "channel": "ticker",
        "type": "update",
        "data": [
            {"symbol": "BTC/USD", "bid": "not-a-number", "ask": 2, "last": 1.5},
            {"symbol": "ETH/USD", "bid": 3, "ask": 4, "last": 3.5},
        ],
    }

    tickers = parse_ticker_message(payload)

    assert [t.pair for t in tickers] == ["ETH/USD"]
