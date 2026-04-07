import time
from datetime import datetime
from typing import Iterator
import requests
from dagster import ConfigurableResource, get_dagster_logger

API_VERSION = "2026-03"
BASE_URL = "https://api.hubapi.com"

log = get_dagster_logger()


def _request_with_retry(method: str, url: str, max_retries: int = 5, **kwargs) -> requests.Response:
    """HTTP request with exponential backoff on 429/502/503 errors."""
    for attempt in range(max_retries):
        resp = requests.request(method, url, **kwargs)
        if resp.status_code in (429, 502, 503):
            wait = min(2 ** attempt * 2, 60)
            log.warning(f"HTTP {resp.status_code}, retrying in {wait}s (attempt {attempt + 1}/{max_retries})")
            time.sleep(wait)
            continue
        return resp
    return resp


class HubSpotResource(ConfigurableResource):
    access_token: str

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

    def _crm_url(self, *segments: str) -> str:
        """Build a CRM API URL: /crm/objects/{API_VERSION}/{segments...}"""
        return f"{BASE_URL}/crm/objects/{API_VERSION}/{'/'.join(segments)}"

    def _assoc_url(self, *segments: str) -> str:
        """Build an associations API URL: /crm/associations/{API_VERSION}/{segments...}"""
        return f"{BASE_URL}/crm/associations/{API_VERSION}/{'/'.join(segments)}"

    def _get_all_properties(self, object_type: str) -> list[str]:
        """Fetch all property names for an object type."""
        url = self._crm_url(object_type, "properties")
        resp = _request_with_retry("GET", url, headers=self._headers())
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        return [p["name"] for p in data.get("results", [])]

    # ------------------------------------------------------------------
    # CRM object listing (always full load — ReplacingMergeTree deduplicates)
    # ------------------------------------------------------------------

    def fetch_crm_objects_batched(
        self,
        object_type: str,
        batch_size: int = 100,
    ) -> Iterator[list[dict]]:
        """Full load via List API. No 10k limit, no Search API dependency.

        ReplacingMergeTree in ClickHouse handles deduplication by _record_id,
        so full loads are safe and idempotent on every run.
        """
        properties = self._get_all_properties(object_type)
        url = self._crm_url(object_type)
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

            next_after = (data.get("paging") or {}).get("next", {}).get("after")
            if not next_after:
                break
            params["after"] = next_after
            time.sleep(0.1)

    # ------------------------------------------------------------------
    # Associations
    # ------------------------------------------------------------------

    def fetch_all_object_ids(self, object_type: str) -> list[str]:
        """Fetch all record IDs for an object type (for association lookups)."""
        url = self._crm_url(object_type)
        params: dict = {"limit": 100}
        ids: list[str] = []

        while True:
            resp = _request_with_retry("GET", url, headers=self._headers(), params=params)
            resp.raise_for_status()
            data = resp.json()
            for r in data.get("results", []):
                ids.append(str(r["id"]))
            next_after = (data.get("paging") or {}).get("next", {}).get("after")
            if not next_after:
                break
            params["after"] = next_after
            time.sleep(0.1)
        return ids

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
        url = self._assoc_url(from_type, to_type, "batch/read")

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

    def fetch_association_types(self, from_type: str, to_type: str) -> list[dict]:
        """Fetch association type metadata between two object types."""
        url = self._assoc_url(from_type, to_type, "labels")
        resp = _request_with_retry("GET", url, headers=self._headers())
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])

    # ------------------------------------------------------------------
    # Owners (flat JSON, no properties map)
    # ------------------------------------------------------------------

    def fetch_owners(self, batch_size: int = 100) -> Iterator[list[dict]]:
        """Fetch all owners. Flat JSON structure (no properties map)."""
        url = f"{BASE_URL}/crm/v3/owners"
        params: dict = {"limit": batch_size}

        while True:
            resp = _request_with_retry("GET", url, headers=self._headers(), params=params)
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            if results:
                yield results

            next_after = (data.get("paging") or {}).get("next", {}).get("after")
            if not next_after:
                break
            params["after"] = next_after
            time.sleep(0.1)

    # ------------------------------------------------------------------
    # Form submissions (legacy v1 endpoint — no v3 equivalent exists)
    # ------------------------------------------------------------------

    def fetch_form_submissions(
        self,
        form_id: str,
        batch_size: int = 50,
    ) -> Iterator[list[dict]]:
        """Fetch all submissions for a single form.

        GET /form-integrations/v1/submissions/forms/{formId}
        Max 50 per page, cursor-based pagination.
        """
        url = f"{BASE_URL}/form-integrations/v1/submissions/forms/{form_id}"
        params: dict = {"limit": batch_size}

        while True:
            resp = _request_with_retry("GET", url, headers=self._headers(), params=params)
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            if results:
                yield results

            next_after = (data.get("paging") or {}).get("next", {}).get("after")
            if not next_after:
                break
            params["after"] = next_after
            time.sleep(0.1)

    def fetch_all_form_ids(self) -> list[dict]:
        """Fetch all form IDs and names. Returns [{id, name}, ...]."""
        forms = []
        for batch in self.fetch_marketing_list("/marketing/v3/forms"):
            for f in batch:
                forms.append({"id": str(f["id"]), "name": f.get("name", "")})
        return forms

    # ------------------------------------------------------------------
    # Property metadata (for semantic layer)
    # ------------------------------------------------------------------

    def fetch_properties(self, object_type: str) -> list[dict]:
        """Fetch full property metadata for an object type.

        Uses /crm/v3/properties/{objectType} (NOT the v4 objects endpoint).
        Returns list of dicts with: name, label, description, type, fieldType,
        groupName, options (for enumerations), etc.
        """
        url = f"{BASE_URL}/crm/v3/properties/{object_type}"
        resp = _request_with_retry("GET", url, headers=self._headers())
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else data.get("results", [])

    # ------------------------------------------------------------------
    # Marketing endpoints
    # ------------------------------------------------------------------

    def fetch_marketing_list(
        self,
        path: str,
        results_key: str = "results",
        params: dict | None = None,
        since: datetime | None = None,
    ) -> Iterator[list[dict]]:
        """Paginate a marketing REST list endpoint."""
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

            next_after = (data.get("paging") or {}).get("next", {}).get("after")
            if not next_after:
                break
            p["after"] = next_after
            time.sleep(0.1)
