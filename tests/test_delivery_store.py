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


@pytest.mark.parametrize(
    "field",
    [
        "api_key",
        "accessToken",
        "x-api-key",
        "privateKey",
        "bearerAuth",
        "auth",
        "app_secret",
        "webhook_url",
    ],
)
def test_pending_delivery_store_rejects_other_secret_field_names(tmp_path, field):
    store = PendingDeliveryStore(tmp_path)

    with pytest.raises(ValueError, match="secret field"):
        store.save("2026-07-13", "morning", {field: "secret"})


def test_pending_delivery_store_load_wraps_secret_field_as_corruption(tmp_path):
    store = PendingDeliveryStore(tmp_path)
    path = tmp_path / "pending_deliveries" / "2026-07-13-morning.json"
    path.parent.mkdir()
    path.write_text('{"apiKey":"secret"}', encoding="utf-8")

    with pytest.raises(PendingDeliveryCorruptError, match="secret field"):
        store.load("2026-07-13", "morning")


def test_pending_delivery_store_loads_clean_historical_file(tmp_path):
    store = PendingDeliveryStore(tmp_path)
    path = tmp_path / "pending_deliveries" / "2026-07-13-morning.json"
    path.parent.mkdir()
    payload = '{"delivery_id":"id-1","finalization":{"selection_evidence":[]}}'
    path.write_text(payload, encoding="utf-8")

    assert store.load("2026-07-13", "morning") == {
        "delivery_id": "id-1",
        "finalization": {"selection_evidence": []},
    }


def test_pending_delivery_store_allows_tokenizer_version_audit_field(tmp_path):
    store = PendingDeliveryStore(tmp_path)
    payload = {"selection_evidence": [{"tokenizer_version": "nfkc-casefold-v1"}]}

    store.save("2026-07-13", "morning", payload)

    assert store.load("2026-07-13", "morning") == payload


def test_pending_delivery_store_allows_author_metadata(tmp_path):
    store = PendingDeliveryStore(tmp_path)
    payload = {"author": "editor"}

    store.save("2026-07-13", "morning", payload)

    assert store.load("2026-07-13", "morning") == payload
