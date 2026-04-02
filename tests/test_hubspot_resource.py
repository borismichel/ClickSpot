from datetime import datetime
from unittest.mock import MagicMock, patch, call
from resources.hubspot import HubSpotResource


def make_resource():
    return HubSpotResource(access_token="test-token")


# --- CRM Search ---

@patch("resources.hubspot.requests.get")
def test_fetch_crm_full_load_uses_list_api(mock_get):
    """Full load (no since) uses the List API, not Search."""
    resp1 = MagicMock()
    resp1.json.return_value = {
        "results": [{"id": "1"}],
        "paging": {"next": {"after": "cursor-2"}},
    }
    resp2 = MagicMock()
    resp2.json.return_value = {"results": [{"id": "2"}]}

    mock_get.side_effect = [resp1, resp2]

    res = make_resource()
    batches = list(res.fetch_crm_objects_batched("contacts"))

    assert batches == [[{"id": "1"}], [{"id": "2"}]]
    assert mock_get.call_count == 2
    # Verify it called the List API URL
    assert "crm/v3/objects/contacts" in mock_get.call_args_list[0][0][0]


@patch("resources.hubspot.hubspot.Client.create")
@patch("resources.hubspot.time.sleep")
def test_fetch_crm_applies_since_filter(mock_sleep, mock_create):
    page = MagicMock()
    page.results = [MagicMock(to_dict=lambda: {"id": "1"})]
    page.paging = None

    mock_client = MagicMock()
    mock_client.crm.objects.search_api.do_search.return_value = page
    mock_create.return_value = mock_client

    since = datetime(2024, 1, 15, 12, 0, 0)
    res = make_resource()
    list(res.fetch_crm_objects_batched("contacts", since=since))

    call_kwargs = mock_client.crm.objects.search_api.do_search.call_args
    body = call_kwargs.kwargs["public_object_search_request"]
    assert body["filterGroups"][0]["filters"][0]["operator"] == "GTE"
    assert body["filterGroups"][0]["filters"][0]["propertyName"] == "lastmodifieddate"


# --- Marketing list ---

@patch("resources.hubspot.requests.get")
def test_fetch_marketing_list_yields_all_pages(mock_get):
    resp1 = MagicMock()
    resp1.json.return_value = {
        "results": [{"id": "c1"}],
        "paging": {"next": {"after": "tok2"}},
    }
    resp2 = MagicMock()
    resp2.json.return_value = {"results": [{"id": "c2"}]}

    mock_get.side_effect = [resp1, resp2]

    res = make_resource()
    batches = list(res.fetch_marketing_list("/marketing/v3/campaigns", results_key="results"))

    assert batches == [[{"id": "c1"}], [{"id": "c2"}]]
    assert mock_get.call_count == 2
