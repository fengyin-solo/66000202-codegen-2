"""受控点位写入通道的验收测试。

可直接运行: python3 tests/test_write_channel.py
也可用 pytest 运行。
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from app.main import app
from app.services import write_service
from app.services.modbus_service import POINTS

client = TestClient(app)

_ORIG_VALUES = {k: v["value"] for k, v in POINTS.items()}


def reset_state():
    write_service._records.clear()
    write_service._locks.clear()
    write_service._seq = 0
    for k, v in _ORIG_VALUES.items():
        POINTS[k]["value"] = v


def login(username, password):
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- 既有接口口径不变 ----------

def test_existing_read_endpoints_unchanged():
    resp = client.get("/api/modbus/devices")
    assert resp.status_code == 200
    dev = resp.json()[0]
    assert {"id", "name", "ip", "port", "slave_id", "online"} <= set(dev)

    resp = client.get("/api/modbus/read/dev1/0/2")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"device_id", "address", "values"}
    assert body["device_id"] == "dev1" and body["address"] == 0
    assert len(body["values"]) == 2


# ---------- 身份与权限 ----------

def test_login_rejects_bad_credentials():
    resp = client.post("/api/auth/login", json={"username": "operator1", "password": "wrong"})
    assert resp.status_code == 401


def test_write_requires_login():
    reset_state()
    resp = client.post("/api/modbus/write", json={"device_id": "dev1", "address": 0, "value": 30})
    assert resp.status_code == 401
    assert POINTS[("dev1", 0)]["value"] == _ORIG_VALUES[("dev1", 0)]


def test_viewer_cannot_write_and_attempt_is_audited():
    reset_state()
    viewer = login("viewer1", "viewer123")
    before = POINTS[("dev1", 0)]["value"]
    resp = client.post("/api/modbus/write", json={"device_id": "dev1", "address": 0, "value": 30},
                       headers=auth(viewer))
    assert resp.status_code == 403
    record = resp.json()
    assert record["status"] == "forbidden"
    assert record["operator"] == "viewer1"
    assert POINTS[("dev1", 0)]["value"] == before  # 原值未改变

    # 只读查看者也不能查看下发记录
    resp = client.get("/api/modbus/write-records", headers=auth(viewer))
    assert resp.status_code == 403

    # 操作者能回看到这次被拒绝的提交
    op = login("operator1", "operator123")
    resp = client.get("/api/modbus/write-records?operator=viewer1", headers=auth(op))
    assert resp.status_code == 200
    assert any(r["status"] == "forbidden" for r in resp.json()["records"])


# ---------- 提交前校验 ----------

def test_write_to_unknown_point_rejected():
    reset_state()
    op = login("operator1", "operator123")
    resp = client.post("/api/modbus/write", json={"device_id": "dev1", "address": 99, "value": 10},
                       headers=auth(op))
    assert resp.status_code == 404
    record = resp.json()
    assert record["status"] == "failed" and "不存在" in record["reason"]

    resp = client.post("/api/modbus/write", json={"device_id": "devX", "address": 0, "value": 10},
                       headers=auth(op))
    assert resp.status_code == 404
    assert "不存在" in resp.json()["reason"]


def test_write_to_readonly_point_rejected():
    reset_state()
    op = login("operator1", "operator123")
    before = POINTS[("dev1", 2)]["value"]  # 露点：只读测量点
    resp = client.post("/api/modbus/write", json={"device_id": "dev1", "address": 2, "value": 20},
                       headers=auth(op))
    assert resp.status_code == 400
    assert "只读" in resp.json()["reason"]
    assert POINTS[("dev1", 2)]["value"] == before


def test_write_out_of_range_rejected_and_value_unchanged():
    reset_state()
    op = login("operator1", "operator123")
    before = POINTS[("dev1", 0)]["value"]  # 温度允许范围 [-10, 60]
    resp = client.post("/api/modbus/write", json={"device_id": "dev1", "address": 0, "value": 999},
                       headers=auth(op))
    assert resp.status_code == 400
    record = resp.json()
    assert record["status"] == "failed"
    assert "超出允许范围" in record["reason"] and "[-10.0, 60.0]" in record["reason"]

    # 刷新（重新拉取点位）后仍能看出这次下发没有生效
    resp = client.get("/api/modbus/points")
    point = next(p for p in resp.json()["points"] if p["device_id"] == "dev1" and p["address"] == 0)
    assert point["value"] == before

    # 审计记录里同样能看到这次失败的下发
    records = client.get("/api/modbus/write-records?operator=operator1", headers=auth(op)).json()["records"]
    failed = next(r for r in records if r["value"] == 999)
    assert failed["status"] == "failed" and failed["old_value"] is None


# ---------- 成功下发 ----------

def test_successful_write_takes_effect_and_is_audited():
    reset_state()
    op = login("operator1", "operator123")
    before = POINTS[("dev1", 0)]["value"]
    resp = client.post("/api/modbus/write", json={"device_id": "dev1", "address": 0, "value": 55},
                       headers=auth(op))
    assert resp.status_code == 200
    record = resp.json()
    assert record["status"] == "success"
    assert record["operator"] == "operator1" and record["operator_name"] == "张工"
    assert record["old_value"] == before and record["value"] == 55.0
    assert record["point_name"] == "温度" and record["timestamp"] > 0

    # 点位当前值已更新
    point = next(p for p in client.get("/api/modbus/points").json()["points"]
                 if p["device_id"] == "dev1" and p["address"] == 0)
    assert point["value"] == 55.0

    # 实时读数反映新值（±2% 噪声）
    value = client.get("/api/modbus/read/dev1/0/1").json()["values"][0]
    assert 53.0 < value < 57.0


# ---------- 并发：同一点位先到为准 ----------

def test_concurrent_write_same_point_first_wins_and_retry_works():
    reset_state()
    op1 = {"username": "operator1", "display_name": "张工", "role": "operator"}
    op2 = {"username": "operator2", "display_name": "李工", "role": "operator"}

    async def run():
        return await asyncio.gather(
            write_service.submit_write(op1, "dev1", 0, 30.0),
            write_service.submit_write(op2, "dev1", 0, 40.0),
        )

    (r1, s1), (r2, s2) = asyncio.run(run())
    assert sorted([s1, s2]) == [200, 409]  # 一次成功，一次冲突

    winner, loser = (r1, r2) if s1 == 200 else (r2, r1)
    assert POINTS[("dev1", 0)]["value"] == winner["value"]  # 以先到的一次为准
    assert loser["status"] == "conflict" and "先到" in loser["reason"]

    # 冲突的提交可以重试，第一次结束后重试成功
    record, status = asyncio.run(write_service.submit_write(op2, "dev1", 0, 40.0))
    assert status == 200 and record["status"] == "success"
    assert POINTS[("dev1", 0)]["value"] == 40.0


def test_concurrent_write_different_points_both_succeed():
    reset_state()
    op = {"username": "operator1", "display_name": "张工", "role": "operator"}

    async def run():
        return await asyncio.gather(
            write_service.submit_write(op, "dev1", 0, 30.0),
            write_service.submit_write(op, "dev2", 0, 5.0),
        )

    (_, s1), (_, s2) = asyncio.run(run())
    assert (s1, s2) == (200, 200)
    assert POINTS[("dev1", 0)]["value"] == 30.0
    assert POINTS[("dev2", 0)]["value"] == 5.0


# ---------- 按操作者回看 ----------

def test_records_queryable_by_operator():
    reset_state()
    op1 = login("operator1", "operator123")
    op2 = login("operator2", "operator123")
    client.post("/api/modbus/write", json={"device_id": "dev1", "address": 0, "value": 31}, headers=auth(op1))
    client.post("/api/modbus/write", json={"device_id": "dev1", "address": 1, "value": 50}, headers=auth(op2))
    client.post("/api/modbus/write", json={"device_id": "dev1", "address": 0, "value": 32}, headers=auth(op1))

    records = client.get("/api/modbus/write-records?operator=operator1", headers=auth(op1)).json()["records"]
    assert len(records) == 2
    assert all(r["operator"] == "operator1" for r in records)
    assert records[0]["timestamp"] >= records[1]["timestamp"]  # 最新在前

    records = client.get("/api/modbus/write-records?operator=operator2", headers=auth(op1)).json()["records"]
    assert len(records) == 1 and records[0]["operator"] == "operator2"

    # 不带过滤条件返回全部；未登录不可查
    assert len(client.get("/api/modbus/write-records", headers=auth(op1)).json()["records"]) == 3
    assert client.get("/api/modbus/write-records").status_code == 401


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {name}: {exc!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
