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
        """Paginate the CRM Search API for a given object type.

        Yields lists (batches) of raw API response dicts.
        Applies a lastmodifieddate >= since filter when since is provided.
        Sleeps 0.1s between pages to stay within the 150 req/10s rate limit.
        """
        client = self._client()
        filters = []
        if since:
            filters = [{
                "propertyName": "lastmodifieddate",
                "operator": "GTE",
                "value": str(int(since.timestamp() * 1000)),
            }]

        after = None
        while True:
            body: dict = {
                "filterGroups": [{"filters": filters}] if filters else [],
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
