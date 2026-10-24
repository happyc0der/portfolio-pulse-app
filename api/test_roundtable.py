from api.main import extract_version
from api.roundtable import parse_result


def test_parse_nested_task_and_id_alias():
    assert parse_result({"task": {"id": 22, "status": "available"}}) == {"id": 22, "status": "available", "task_id": 22}
    assert parse_result({"result": {"id": "abc"}}) == {"id": "abc", "task_id": "abc"}


def test_parse_stringified_result():
    assert parse_result({"result": '{"task":{"task_id":"t1"}}'}) == {"task_id": "t1"}


def test_task_with_its_own_result_field_is_not_unwrapped():
    task = {"id": "t1", "status": "done", "version": 3, "result": {"summary": "Cited draft prepared"}}
    assert parse_result(task)["status"] == "done"
    assert parse_result(task)["task_id"] == "t1"


def test_envelope_is_unwrapped():
    assert parse_result({"result": '{"id": "t2", "status": "active"}'})["status"] == "active"


def test_file_version_object_gives_its_id():
    assert extract_version({"version": {"id": "7820d3b3e3b3", "number": 9}}) == "7820d3b3e3b3"
    assert extract_version({"version_id": "abc"}) == "abc"
    assert extract_version({"ok": True}) is None
