import json

import rbc_server
import train_evc


def test_sign_and_verify_roundtrip():
    key = b"test-key-123"
    payload = {"type": "MA", "id": 42, "speed_kmh": 120, "distance_m": 2000}

    sig = rbc_server.sign_message(key, payload)
    assert isinstance(sig, str)

    assert train_evc.verify_signature(key, payload, sig) is True


def test_verify_rejects_tampered_payload():
    key = b"test-key-123"
    payload = {"type": "MA", "id": 1, "speed_kmh": 80, "distance_m": 1000}

    sig = rbc_server.sign_message(key, payload)

    # Tamper with the payload after signing
    tampered = dict(payload)
    tampered["speed_kmh"] = 200

    assert train_evc.verify_signature(key, tampered, sig) is False


def test_dmi_publisher_update_ma_changes_targets():
    pub = train_evc.DmiPublisher()

    # Initial values should be zero
    assert pub.target_speed == 0.0
    assert pub.distance_to_go == 0.0

    pub.update_ma(100.0, 1500.0)

    assert pub.target_speed == 100.0
    assert pub.distance_to_go == 1500.0
