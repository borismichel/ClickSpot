from datetime import datetime
from unittest.mock import MagicMock, patch
from resources.hubspot import HubSpotResource, API_VERSION


def make_resource():
    return HubSpotResource(access_token="test-token")


def _mock_properties_response():
    """Mock response for _get_all_properties call."""
    resp = MagicMock()
    resp.json.return_value = {
        "results": [{"name": "email"}, {"name": "firstname"}]
    }
    return resp


# --- CRM List (full load) ---

@patch("resources.hubspot.time.sleep")
@patch("resources.hubspot.requests.request")
def test_fetch_crm_full_load_uses_versioned_list_api(mock_request, mock_sleep):
    """Full load (no since) uses the versioned List API with all properties."""
    props_resp = _mock_properties_response()
    resp1 = MagicMock()
    resp1.json.return_value = {
        "results": [{"id": "1"}],
        "paging": {"next": {"after": "cursor-2"}},
    }
    resp2 = MagicMock()
    resp2.json.return_value = {"results": [{"id": "2"}]}

    mock_request.side_effect = [props_resp, resp1, resp2]

    res = make_resource()
    batches = list(res.fetch_crm_objects_batched("contacts"))

    assert batches == [[{"id": "1"}], [{"id": "2"}]]
    # 1 properties call + 2 list pages
    assert mock_request.call_count == 3
    # First call is properties, second is the list API
    assert f"crm/objects/{API_VERSION}/contacts" in mock_request.call_args_list[1][0][1]
    # Verify properties are passed
    list_params = mock_request.call_args_list[1][1].get("params", {})
    assert "properties" in list_params


# --- CRM Search (incremental) ---

@patch("resources.hubspot.time.sleep")
@patch("resources.hubspot.requests.request")
def test_fetch_crm_always_uses_list_api(mock_request, mock_sleep):
    """Full load always uses the List API (no Search API dependency)."""
    props_resp = _mock_properties_response()

    resp = MagicMock()
    resp.json.return_value = {
        "results": [{"id": "1"}],
    }

    mock_request.side_effect = [props_resp, resp]

    res = make_resource()
    batches = list(res.fetch_crm_objects_batched("contacts"))

    assert batches == [[{"id": "1"}]]
    # First call is properties (GET), second is list (GET)
    call_method = mock_request.call_args_list[1][0][0]
    call_url = mock_request.call_args_list[1][0][1]
    assert call_method == "GET"
    assert f"crm/objects/{API_VERSION}/contacts" in call_url
    assert "search" not in call_url


# --- Marketing list ---

@patch("resources.hubspot.time.sleep")
@patch("resources.hubspot.requests.request")
def test_fetch_marketing_list_yields_all_pages(mock_request, mock_sleep):
    resp1 = MagicMock()
    resp1.json.return_value = {
        "results": [{"id": "c1"}],
        "paging": {"next": {"after": "tok2"}},
    }
    resp2 = MagicMock()
    resp2.json.return_value = {"results": [{"id": "c2"}]}

    mock_request.side_effect = [resp1, resp2]

    res = make_resource()
    batches = list(res.fetch_marketing_list("/marketing/v3/campaigns", results_key="results"))

    assert batches == [[{"id": "c1"}], [{"id": "c2"}]]
    assert mock_request.call_count == 2


# --- Associations ---

@patch("resources.hubspot.time.sleep")
@patch("resources.hubspot.requests.request")
def test_fetch_associations_batched(mock_request, mock_sleep):
    resp = MagicMock()
    resp.json.return_value = {
        "results": [
            {
                "from": {"id": "101"},
                "to": [
                    {"id": "201", "associationTypes": [{"label": "Primary"}]},
                    {"id": "202", "associationTypes": [{"label": ""}]},
                ],
            }
        ]
    }
    mock_request.return_value = resp

    res = make_resource()
    batches = list(res.fetch_associations_batched("contacts", "companies", ["101"]))

    assert len(batches) == 1
    assert batches[0] == [
        {"from_id": "101", "to_id": "201", "association_type": "Primary"},
        {"from_id": "101", "to_id": "202", "association_type": ""},
    ]
    call_url = mock_request.call_args_list[0][0][1]
    assert f"crm/associations/{API_VERSION}/contacts/companies/batch/read" in call_url


# --- fetch_all_object_ids ---

@patch("resources.hubspot.time.sleep")
@patch("resources.hubspot.requests.request")
def test_fetch_all_object_ids(mock_request, mock_sleep):
    resp = MagicMock()
    resp.json.return_value = {"results": [{"id": "1"}, {"id": "2"}]}
    mock_request.return_value = resp

    res = make_resource()
    ids = res.fetch_all_object_ids("contacts")

    assert ids == ["1", "2"]
