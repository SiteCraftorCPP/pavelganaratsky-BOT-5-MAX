from typing import Any

_store: dict[int, dict[str, Any]] = {}


def clear(user_id: int) -> None:
    _store.pop(user_id, None)


def _ctx(user_id: int) -> dict[str, Any]:
    if user_id not in _store:
        _store[user_id] = {"state": None, "data": {}}
    return _store[user_id]


def get_state(user_id: int) -> str | None:
    return _ctx(user_id).get("state")


def set_state(user_id: int, state: str | None) -> None:
    _ctx(user_id)["state"] = state


def get_data(user_id: int) -> dict[str, Any]:
    return _ctx(user_id)["data"]


def update_data(user_id: int, **kwargs: Any) -> None:
    _ctx(user_id)["data"].update(kwargs)


def clear_data(user_id: int) -> None:
    _ctx(user_id)["data"] = {}
