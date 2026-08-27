from datetime import UTC, datetime
from decimal import Decimal

from app.market_data.kraken import (
    _parse_ohlc_rest_result,
    _parse_rfc3339_seconds,
    parse_ohlc_message,
)


def _ws_candle(**overrides: object) -> dict[str, object]:
    candle: dict[str, object] = {
        "symbol": "BTC/USD",
        "open": 27400.1,
        "high": 27410.2,
        "low": 27395.0,
        "close": 27402.5,
        "trades": 12,
        "volume": 1.2345,
        "vwap": 27401.0,
        "interval_begin": "2023-10-06T17:35:00.000000000Z",
        "interval": 5,
        "timestamp": "2023-10-06T17:40:00.000000000Z",
    }
    candle.update(overrides)
    return candle


def test_parses_an_ohlc_update_message() -> None:
    payload = {"channel": "ohlc", "type": "update", "data": [_ws_candle()]}

    candles = parse_ohlc_message(payload)

    assert len(candles) == 1
    candle = candles[0]
    assert candle.pair == "BTC/USD"
    assert candle.interval == 5
    assert candle.open_time == datetime(2023, 10, 6, 17, 35, tzinfo=UTC)
    assert candle.open == Decimal("27400.1")
    assert candle.high == Decimal("27410.2")
    assert candle.low == Decimal("27395.0")
    assert candle.close == Decimal("27402.5")
    assert candle.volume == Decimal("1.2345")
    assert candle.vwap == Decimal("27401.0")
    assert candle.trades == 12


def test_parses_an_ohlc_snapshot_message() -> None:
    payload = {"channel": "ohlc", "type": "snapshot", "data": [_ws_candle()]}

    assert len(parse_ohlc_message(payload)) == 1


def test_parses_multiple_candles_in_one_message() -> None:
    payload = {
        "channel": "ohlc",
        "type": "update",
        "data": [
            _ws_candle(symbol="BTC/USD", interval=1),
            _ws_candle(symbol="ETH/USD", interval=1),
        ],
    }

    candles = parse_ohlc_message(payload)

    assert [(c.pair, c.interval) for c in candles] == [
        ("BTC/USD", 1),
        ("ETH/USD", 1),
    ]


def test_coerces_ws_numeric_prices_without_float_artifacts() -> None:
    # JSON numbers on the wire — must round-trip through str(), not float().
    payload = {
        "channel": "ohlc",
        "type": "update",
        "data": [_ws_candle(close=0.1, open=0.3)],
    }

    candle = parse_ohlc_message(payload)[0]

    assert candle.close == Decimal("0.1")
    assert candle.open == Decimal("0.3")


def test_missing_vwap_and_trades_become_none() -> None:
    item = _ws_candle()
    del item["vwap"]
    del item["trades"]
    payload = {"channel": "ohlc", "type": "update", "data": [item]}

    candle = parse_ohlc_message(payload)[0]

    assert candle.vwap is None
    assert candle.trades is None


def test_ignores_a_subscribe_acknowledgement() -> None:
    payload = {
        "method": "subscribe",
        "result": {"channel": "ohlc", "symbol": "BTC/USD", "interval": 5},
        "success": True,
    }

    assert parse_ohlc_message(payload) == []


def test_ignores_a_heartbeat() -> None:
    assert parse_ohlc_message({"channel": "heartbeat"}) == []


def test_ignores_a_non_ohlc_channel() -> None:
    payload = {"channel": "ticker", "type": "update", "data": [{"symbol": "BTC/USD"}]}
    assert parse_ohlc_message(payload) == []


def test_skips_a_malformed_entry_without_dropping_the_rest_of_the_batch() -> None:
    payload = {
        "channel": "ohlc",
        "type": "update",
        "data": [
            _ws_candle(symbol="BTC/USD", close="not-a-number"),
            _ws_candle(symbol="ETH/USD"),
        ],
    }

    candles = parse_ohlc_message(payload)

    assert [c.pair for c in candles] == ["ETH/USD"]


def test_parse_rfc3339_seconds_trims_nanoseconds() -> None:
    assert _parse_rfc3339_seconds("2023-10-04T15:25:00.000000000Z") == datetime(
        2023, 10, 4, 15, 25, tzinfo=UTC
    )


def test_parse_rfc3339_seconds_handles_a_plain_second_timestamp() -> None:
    assert _parse_rfc3339_seconds("2023-10-04T15:25:07Z") == datetime(
        2023, 10, 4, 15, 25, 7, tzinfo=UTC
    )


def test_parse_ohlc_rest_result_ignores_the_last_cursor_key() -> None:
    result = {
        "XXBTZUSD": [
            [1688671200, "30306.1", "30306.2", "30305.7", "30305.7", "30306.1", "3.3924", 23],
            [1688671260, "30304.5", "30304.5", "30300.0", "30300.0", "30300.0", "4.4299", 18],
        ],
        "last": 1688672160,
    }

    candles = _parse_ohlc_rest_result(result, pair="BTC/USD", interval=1)

    assert len(candles) == 2
    assert candles[0].pair == "BTC/USD"
    assert candles[0].interval == 1
    assert candles[0].open_time == datetime.fromtimestamp(1688671200, tz=UTC)
    assert candles[0].open == Decimal("30306.1")
    assert candles[0].close == Decimal("30305.7")
    assert candles[0].vwap == Decimal("30306.1")
    assert candles[0].volume == Decimal("3.3924")
    assert candles[0].trades == 23


def test_parse_ohlc_rest_result_survives_reversed_key_order() -> None:
    result = {
        "last": 1688672160,
        "XXBTZUSD": [
            [1688671200, "1", "2", "0.5", "1.5", "1.2", "10", 3],
        ],
    }

    candles = _parse_ohlc_rest_result(result, pair="BTC/USD", interval=15)

    assert len(candles) == 1
    assert candles[0].high == Decimal(2)
