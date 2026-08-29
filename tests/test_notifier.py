"""Notifications are best-effort: they must never be able to stop trading."""

import logging

import pytest

from tradingbot.notifier import Notifier


def test_a_notifier_without_a_webhook_is_disabled(monkeypatch):
    monkeypatch.delenv("TRADINGBOT_WEBHOOK_URL", raising=False)
    assert not Notifier().enabled


def test_a_webhook_is_picked_up_from_the_environment(monkeypatch):
    monkeypatch.setenv("TRADINGBOT_WEBHOOK_URL", "https://example.test/hook")
    assert Notifier().enabled


def test_messages_are_logged_even_with_no_webhook(monkeypatch, caplog):
    monkeypatch.delenv("TRADINGBOT_WEBHOOK_URL", raising=False)
    with caplog.at_level(logging.INFO):
        Notifier().send("hello")
    assert "hello" in caplog.text


def test_a_webhook_receives_the_message(monkeypatch):
    sent = {}

    class FakeResponse:
        def close(self):
            pass

    def fake_urlopen(request, timeout=None):
        sent["url"] = request.full_url
        sent["body"] = request.data.decode()
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    Notifier("https://example.test/hook").send("trade opened")
    assert sent["url"] == "https://example.test/hook"
    assert "trade opened" in sent["body"]


def test_a_failing_webhook_does_not_raise(monkeypatch, caplog):
    import urllib.error

    def boom(request, timeout=None):
        raise urllib.error.URLError("network down")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    # A broken webhook must never propagate into the trading loop.
    with caplog.at_level(logging.WARNING):
        Notifier("https://example.test/hook").send("still trading")
    assert "notification failed" in caplog.text


def test_a_webhook_timeout_does_not_raise(monkeypatch):
    def boom(request, timeout=None):
        raise OSError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    Notifier("https://example.test/hook").send("still trading")  # must not raise


@pytest.mark.parametrize(
    "call,expected",
    [
        (lambda n: n.trade_opened("BTC/USDT", "buy", 1.5, 30_000.0, "cross"), "OPEN"),
        (lambda n: n.trade_closed("BTC/USDT", 120.0, 31_000.0, "target"), "CLOSE"),
        (lambda n: n.halted("drawdown"), "HALTED"),
        (lambda n: n.error("boom"), "ERROR"),
    ],
)
def test_each_event_type_is_logged(monkeypatch, caplog, call, expected):
    monkeypatch.delenv("TRADINGBOT_WEBHOOK_URL", raising=False)
    with caplog.at_level(logging.INFO):
        call(Notifier())
    assert expected in caplog.text


def test_a_profit_is_signed_in_the_message(monkeypatch, caplog):
    monkeypatch.delenv("TRADINGBOT_WEBHOOK_URL", raising=False)
    with caplog.at_level(logging.INFO):
        Notifier().trade_closed("BTC/USDT", 120.0, 31_000.0, "target")
    assert "+120.00" in caplog.text
