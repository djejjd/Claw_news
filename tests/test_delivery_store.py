import pytest

from app.delivery.store import PendingDeliveryCorruptError, PendingDeliveryStore


def test_pending_delivery_store_round_trips_and_deletes(tmp_path):
    store = PendingDeliveryStore(tmp_path)
    payload = {"delivery_id": "id-1", "wecom_markdown": "digest", "telegram_messages": ["digest"]}

    store.save("2026-07-13", "morning", payload)

    assert store.load("2026-07-13", "morning") == payload
    store.delete("2026-07-13", "morning")
    assert store.load("2026-07-13", "morning") is None


def test_pending_delivery_store_preserves_corrupt_file_for_investigation(tmp_path):
    store = PendingDeliveryStore(tmp_path)
    path = tmp_path / "pending_deliveries" / "2026-07-13-morning.json"
    path.parent.mkdir()
    path.write_text("not-json", encoding="utf-8")

    with pytest.raises(PendingDeliveryCorruptError):
        store.load("2026-07-13", "morning")

    assert path.read_text(encoding="utf-8") == "not-json"


def test_pending_delivery_store_payload_cannot_contain_secrets(tmp_path):
    store = PendingDeliveryStore(tmp_path)

    with pytest.raises(ValueError, match="secret field"):
        store.save("2026-07-13", "morning", {"telegram_bot_token": "secret"})

    assert not (tmp_path / "pending_deliveries").exists()
