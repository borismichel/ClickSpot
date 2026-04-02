import time
from datetime import datetime
from typing import Iterator
import hubspot
import requests
from dagster import ConfigurableResource


class HubSpotResource(ConfigurableResource):
    access_token: str

    def _client(self):
        return hubspot.Client.create(access_token=self.access_token)

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
        if since:
            yield from self._fetch_crm_search(object_type, since, batch_size)
        else:
            yield from self._fetch_crm_list(object_type, batch_size)

    def _fetch_crm_list(
        self, object_type: str, batch_size: int = 100,
    ) -> Iterator[list[dict]]:
        """Full load via GET /crm/v3/objects/{type} — no 10k limit."""
        url = f"https://api.hubapi.com/crm/v3/objects/{object_type}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        params: dict = {"limit": batch_size}

        while True:
            resp = requests.get(url, headers=headers, params=params)
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
    ) -> Iterator[list[dict]]:
        """Incremental load via Search API — 10k limit OK for hourly deltas."""
        client = self._client()
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
            if after:
                body["after"] = after

            resp = client.crm.objects.search_api.do_search(
                object_type=object_type,
                public_object_search_request=body,
            )

            if resp.results:
                yield [r.to_dict() for r in resp.results]

            if resp.paging and resp.paging.next:
                after = resp.paging.next.after
                time.sleep(0.1)
            else:
                break

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
        url = f"https://api.hubapi.com{path}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        p = dict(params or {})
        if since:
            p["updatedAfter"] = since.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        while True:
            resp = requests.get(url, headers=headers, params=p)
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
