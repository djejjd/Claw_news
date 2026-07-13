from app.delivery.state import ChannelResult, DeliveryState, make_delivery_id


def test_delivery_id_is_stable_for_the_same_digest_content():
    assert make_delivery_id("2026-07-13", "morning", "digest") == make_delivery_id(
        "2026-07-13", "morning", "digest"
    )


def test_delivery_id_changes_when_digest_content_changes():
    assert make_delivery_id("2026-07-13", "morning", "first") != make_delivery_id(
        "2026-07-13", "morning", "second"
    )


def test_succeeded_channel_is_not_attempted_but_failed_channel_is():
    state = DeliveryState(
        delivery_id="delivery-1",
        channels={
            "wecom": ChannelResult(enabled=True, status="succeeded"),
            "telegram": ChannelResult(enabled=True, status="failed", error="telegram_http: 500"),
        },
    )

    assert state.can_attempt("wecom") is False
    assert state.can_attempt("telegram") is True


def test_delivery_state_serialization_has_no_secret_fields():
    payload = DeliveryState(
        delivery_id="delivery-1",
        channels={"telegram": ChannelResult(enabled=True, status="pending")},
    ).to_dict()

    assert payload == {
        "delivery_id": "delivery-1",
        "channels": {
            "telegram": {
                "enabled": True,
                "status": "pending",
                "attempted_at": None,
                "error": None,
            }
        },
    }
    assert "token" not in str(payload).lower()
    assert "chat_id" not in str(payload).lower()
