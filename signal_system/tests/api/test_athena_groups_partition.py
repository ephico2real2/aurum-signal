"""Partition logic: ATHENA open_groups vs MT5 magics (no false-positive tiles)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "python"))

from athena_api import partition_open_groups_for_athena  # noqa: E402


def test_partition_confirms_only_matching_magic():
    mt5 = {
        "open_positions": [{"magic": 202405, "ticket": 1}],
        "pending_orders": [],
    }
    groups = [
        {"id": 4, "direction": "SELL", "status": "OPEN"},
        {"id": 7, "direction": "BUY", "status": "OPEN"},
    ]
    conf, que = partition_open_groups_for_athena(groups, mt5, 202401)
    assert [g["id"] for g in conf] == [4]
    assert [g["id"] for g in que] == [7]


def test_partition_pending_order_magic_counts():
    mt5 = {
        "open_positions": [],
        "pending_orders": [{"magic": 202408, "ticket": 2}],
    }
    groups = [{"id": 7, "status": "OPEN"}]
    conf, que = partition_open_groups_for_athena(groups, mt5, 202401)
    assert conf == groups
    assert que == []


def test_partition_empty_mt5_queues_everything():
    conf, que = partition_open_groups_for_athena(
        [{"id": 1, "status": "OPEN"}], {}, 202401
    )
    assert conf == []
    assert len(que) == 1


def test_api_live_exposes_partition_fields():
    import athena_api  # noqa: WPS433

    client = athena_api.app.test_client()
    r = client.get("/api/live")
    assert r.status_code == 200
    d = r.get_json()
    assert "open_groups" in d and isinstance(d["open_groups"], list)
    assert "open_groups_queued" in d and isinstance(d["open_groups_queued"], list)
    assert "open_groups_policy" in d and len(d["open_groups_policy"]) > 20

