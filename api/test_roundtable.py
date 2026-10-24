from api.roundtable import parse_result


def test_parse_nested_task_and_id_alias():
    assert parse_result({"task": {"id": 22, "status": "available"}}) == {"id": 22, "status": "available", "task_id": 22}
    assert parse_result({"result": {"id": "abc"}}) == {"id": "abc", "task_id": "abc"}


def test_parse_stringified_result():
    assert parse_result({"result": '{"task":{"task_id":"t1"}}'}) == {"task_id": "t1"}
