import time
from typing import Any
from urllib.parse import quote

import requests

from ..models import AlertError, Post

API = "https://api.apify.com/v2"


def _field(item: dict[str, Any], path: str, index: int) -> str:
    value: Any = item
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise AlertError(f"Apify item {index}: missing mapped field '{path}'; update apify.fields")
        value = value[part]
    if value is None:
        return ""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise AlertError(f"Apify item {index}: field '{path}' must be scalar; use a dotted field path")
    return str(value)


def map_item(item: dict[str, Any], fields: dict[str, str], index: int = 0) -> Post:
    values = {key: _field(item, path, index) for key, path in fields.items()}
    if not values["url_field"]:
        raise AlertError(f"Apify item {index}: URL field is empty")
    return Post(url=values["url_field"], author=values["author_field"], text=values["text_field"],
                published=values["date_field"], source="apify")


def fetch_task(token: str, task_id: str, fields: dict[str, str], timeout: int,
               poll: int, session: requests.Session) -> list[Post]:
    if not token or not task_id:
        raise AlertError("Apify requires APIFY_TOKEN and APIFY_TASK_ID")
    deadline = time.monotonic() + timeout

    def request(method: str, path: str, **kwargs: Any) -> Any:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AlertError("Apify timed out waiting for run/dataset; check the run in Apify Console")
        try:
            response = session.request(method, API + path, headers={"Authorization": f"Bearer {token}"},
                                       timeout=min(30, remaining), **kwargs)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            raise AlertError("Apify HTTP/JSON request failed; check credentials, task, and connectivity") from None

    try:
        # Do not retry POST: an ambiguous timeout could otherwise create a second paid run.
        run = request("POST", f"/actor-tasks/{quote(task_id, safe='')}/runs", params={"timeout": timeout})["data"]
        run_id = quote(run["id"], safe="")
        while run["status"] in {"READY", "RUNNING", "TIMING-OUT", "ABORTING"}:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AlertError("Apify run timed out; inspect Apify Console (server timeout is also configured)")
            time.sleep(min(poll, remaining))
            run = request("GET", f"/actor-runs/{run_id}")["data"]
        if run["status"] != "SUCCEEDED":
            raise AlertError("Apify run did not succeed; inspect run status/logs in Apify Console")
        dataset = quote(run["defaultDatasetId"], safe="")
        posts: list[Post] = []
        offset, limit = 0, 1000
        while True:
            items = request("GET", f"/datasets/{dataset}/items",
                            params={"format": "json", "offset": offset, "limit": limit})
            if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                raise AlertError("Apify dataset must contain JSON objects")
            posts.extend(map_item(item, fields, offset + i) for i, item in enumerate(items))
            if len(items) < limit:
                return posts
            offset += len(items)
    except (KeyError, TypeError):
        raise AlertError("Apify response missing required run/dataset metadata") from None
