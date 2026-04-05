import time
from datetime import datetime
from typing import Iterator
import requests
from dagster import ConfigurableResource, get_dagster_logger

API_VERSION = "2026-03"
BASE_URL = "https://api.hubapi.com"

log = get_dagster_logger()


def _request_with_retry(method: str, url: str, max_retries: int = 5, **kwargs) -> requests.Response:
    """HTTP request with exponential backoff on 429 rate limits."""
    for attempt in range(max_retries):
        resp = requests.request(method, url, **kwargs)
        if resp.status_code == 429:
            wait = min(2 ** attempt * 2, 60)
            log.warning(f"Rate limited (429), retrying in {wait}s (attempt {attempt + 1}/{max_retries})")
            time.sleep(wait)
            continue
        return resp
    return resp  # return last response even if still 429


class HubSpotResource(ConfigurableResource):
    access_token: str

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

    def _get_all_properties(self, object_type: str) -> list[str]:
        """Fetch all property names for an object type."""
        url = f"{BASE_URL}/crm/objects/{API_VERSION}/{object_type}/properties"
        resp = _request_with_retry("GET", url, headers=self._headers())
        resp.raise_for_status()
        data = resp.json()
        # API 2026-03 returns a flat list of property name strings;
        # older versions returned {"results": [{"name": "..."}]}.
        if isinstance(data, list):
            return data
        return [p["name"] for p in data.get("results", [])]

    def fetch_crm_objects_batched(
        self,
        object_type: str,
        since: datetime | None = None,
        batch_size: int = 100,
    ) -> Iterator[list[dict]]:
        """Fetch CRM objects, choosing the right API automatically.

        - Full load (since=None): Uses the List API (no 10k limit).
        - Incremental (since set): Uses the Search API with lastmodifieddate filter.

        Yields lists (batches) of raw API response dicts.
        Sleeps 0.1s between pages to stay within the 150 req/10s rate limit.
        """
        properties = self._get_all_properties(object_type)
        if since:
            yield from self._fetch_crm_search(object_type, since, batch_size, properties)
        else:
            yield from self._fetch_crm_list(object_type, batch_size, properties)

    def _fetch_crm_list(
        self, object_type: str, batch_size: int = 100,
        properties: list[str] | None = None,
    ) -> Iterator[list[dict]]:
        """Full load via GET /crm/objects/{version}/{type} — no 10k limit."""
        url = f"{BASE_URL}/crm/objects/{API_VERSION}/{object_type}"
        params: dict = {"limit": batch_size}
        if properties:
            params["properties"] = ",".join(properties)

        while True:
            resp = _request_with_retry("GET", url, headers=self._headers(), params=params)
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            if results:
                yield results

            next_after = (
                (data.get("paging") or {}).get("next", {}).get("after")
            )
            if not next_after:
                break
            params["after"] = next_after
            time.sleep(0.1)

    def _fetch_crm_search(
        self, object_type: str, since: datetime, batch_size: int = 100,
        properties: list[str] | None = None,
    ) -> Iterator[list[dict]]:
        """Incremental load via Search API — 10k limit OK for hourly deltas."""
        url = f"{BASE_URL}/crm/objects/{API_VERSION}/{object_type}/search"
        filters = [{
            "propertyName": "lastmodifieddate",
            "operator": "GTE",
            "value": str(int(since.timestamp() * 1000)),
        }]

        after = None
        while True:
            body: dict = {
                "filterGroups": [{"filters": filters}],
                "limit": batch_size,
            }
            if properties:
                body["properties"] = properties
            if after:
                body["after"] = after

            resp = _request_with_retry("POST", url, headers=self._headers(), json=body)
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            if results:
                yield results

            next_after = (
                (data.get("paging") or {}).get("next", {}).get("after")
            )
            if not next_after:
                break
            after = next_after
            time.sleep(0.1)

    def fetch_associations_batched(
        self,
        from_type: str,
        to_type: str,
        object_ids: list[str],
        batch_size: int = 1000,
    ) -> Iterator[list[dict]]:
        """Batch-read associations between two object types.

        Yields lists of dicts: {from_id, to_id, association_type}.
        """
        url = (
            f"{BASE_URL}/crm/associations/{API_VERSION}"
            f"/{from_type}/{to_type}/batch/read"
        )

        for i in range(0, len(object_ids), batch_size):
            chunk = object_ids[i : i + batch_size]
            body = {"inputs": [{"id": oid} for oid in chunk]}

            resp = _request_with_retry("POST", url, headers=self._headers(), json=body)
            resp.raise_for_status()
            data = resp.json()

            rows = []
            for result in data.get("results", []):
                from_id = str(result.get("from", {}).get("id", ""))
                for assoc in result.get("to", []):
                    to_id = str(assoc.get("toObjectId") or assoc.get("id", ""))
                    assoc_types = assoc.get("associationTypes", [])
                    type_label = (
                        assoc_types[0].get("label") or ""
                        if assoc_types
                        else ""
                    )
                    rows.append({
                        "from_id": from_id,
                        "to_id": to_id,
                        "association_type": type_label,
                    })
            if rows:
                yield rows
            time.sleep(0.1)

    def fetch_owners(self, batch_size: int = 100) -> Iterator[list[dict]]:
        """Fetch all owners via GET /crm/v3/owners.

        Owners have a flat JSON structure (no properties map).
        Yields lists of owner dicts with id, email, firstName, lastName, etc.
        """
        url = f"{BASE_URL}/crm/v3/owners"
        params: dict = {"limit": batch_size}

        while True:
            resp = _request_with_retry("GET", url, headers=self._headers(), params=params)
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            if results:
                yield results

            next_after = (
                (data.get("paging") or {}).get("next", {}).get("after")
            )
            if not next_after:
                break
            params["after"] = next_after
            time.sleep(0.1)

    def fetch_all_object_ids(self, object_type: str) -> list[str]:
        """Fetch all record IDs for an object type (for association lookups)."""
        ids = []
        for batch in self._fetch_crm_list(object_type, batch_size=100):
            for r in batch:
                ids.append(str(r["id"]))
        return ids

    def fetch_properties(self, object_type: str) -> list[dict]:
        """Fetch full property metadata for an object type.

        GET /crm/v3/properties/{objectType}
        Returns list of dicts with: name, label, description, type, fieldType,
        groupName, options (for enumerations), etc.
        """
        url = f"{BASE_URL}/crm/v3/properties/{object_type}"
        resp = _request_with_retry("GET", url, headers=self._headers())
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", []) if isinstance(data, dict) else data

    def fetch_association_types(self, from_type: str, to_type: str) -> list[dict]:
        """Fetch association type metadata between two object types.

        GET /crm/v4/associations/{from}/{to}/labels
        Returns list of dicts with: typeId, label, category.
        """
        url = f"{BASE_URL}/crm/v4/associations/{from_type}/{to_type}/labels"
        resp = _request_with_retry("GET", url, headers=self._headers())
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])

    def fetch_marketing_list(
        self,
        path: str,
        results_key: str = "results",
        params: dict | None = None,
        since: datetime | None = None,
    ) -> Iterator[list[dict]]:
        """Paginate a marketing REST list endpoint.

        Yields lists of result dicts. Handles the standard HubSpot
        `paging.next.after` cursor pattern.
        """
        url = f"{BASE_URL}{path}"
        p = dict(params or {})
        if since:
            p["updatedAfter"] = since.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        while True:
            resp = _request_with_retry("GET", url, headers=self._headers(), params=p)
            resp.raise_for_status()
            data = resp.json()

            results = data.get(results_key, [])
            if results:
                yield results

            next_after = (
                (data.get("paging") or {}).get("next", {}).get("after")
            )
            if not next_after:
                break
            p["after"] = next_after
            time.sleep(0.1)
