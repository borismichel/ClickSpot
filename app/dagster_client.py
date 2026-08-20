"""Thin Dagster GraphQL client shared by the Settings reload path and the
Sync tab.

Two addresses matter, and they are different audiences:

  DAGSTER_GRAPHQL_URL — where *this backend* reaches Dagster. In compose that
      is the service name (`http://dagster:8194/graphql`), which is meaningless
      to a browser.
  DAGSTER_UI_URL — where the *operator's browser* reaches the Dagster UI, used
      to build "open this run" links. Defaults to loopback (both the source
      setup and the compose manifest publish the UI at localhost:8194);
      deployments behind a hostname or reverse proxy set it explicitly. It is
      deliberately NOT derived from the incoming request — that breaks behind a
      proxy, on a non-standard port mapping, and where the UI port is not
      published at all.
"""

from __future__ import annotations

import os
from typing import Any

import requests
from fastapi import HTTPException

# Dagster statuses that mean "this run is not finished yet".
IN_PROGRESS_STATUSES = ("QUEUED", "NOT_STARTED", "STARTING", "STARTED", "CANCELING")


def graphql_url() -> str:
    return os.environ.get("DAGSTER_GRAPHQL_URL", "http://localhost:8194/graphql")


def ui_url() -> str:
    return os.environ.get("DAGSTER_UI_URL", "http://localhost:8194").rstrip("/")


def run_url(run_id: str) -> str:
    """Browser-facing link to one run's page in the Dagster UI."""
    return f"{ui_url()}/runs/{run_id}"


def dagster_post(query: str, variables: dict | None = None, timeout: int = 30) -> dict:
    """POST to Dagster GraphQL, surfacing both transport and GraphQL errors."""
    url = graphql_url()
    try:
        resp = requests.post(
            url,
            json={"query": query, "variables": variables or {}},
            timeout=timeout,
        )
    except requests.exceptions.RequestException as e:
        raise HTTPException(503, f"Dagster GraphQL unreachable at {url}: {e}")
    if resp.status_code >= 500:
        raise HTTPException(502, f"Dagster GraphQL {resp.status_code}: {resp.text[:300]}")
    try:
        data = resp.json()
    except Exception:
        raise HTTPException(502, f"Dagster GraphQL returned non-JSON: {resp.text[:300]}")
    if data.get("errors"):
        # GraphQL query/mutation errors come back as 200 + an `errors` array OR
        # 400 + an `errors` array. Either way, surface the first message.
        msgs = "; ".join(e.get("message", str(e)) for e in data["errors"])
        raise HTTPException(500, f"Dagster GraphQL error: {msgs}")
    return data.get("data") or {}


_LIST_LOCATIONS_QUERY = """
{
  workspaceOrError {
    ... on Workspace {
      locationEntries {
        name
        loadStatus
        locationOrLoadError {
          __typename
          ... on RepositoryLocation {
            repositories { name }
          }
          ... on PythonError {
            message
          }
        }
      }
    }
    ... on PythonError { message }
  }
}
""".strip()

_RELOAD_MUTATION = """
mutation($name: String!) {
  reloadRepositoryLocation(repositoryLocationName: $name) {
    __typename
    ... on WorkspaceLocationEntry { name loadStatus }
    ... on ReloadNotSupported { message }
    ... on RepositoryLocationNotFound { message }
    ... on PythonError { message }
  }
}
""".strip()

_LAUNCH_RUN_MUTATION = """
mutation($selector: JobOrPipelineSelector!, $runConfigData: RunConfigData, $tags: [ExecutionTag!]) {
  launchPipelineExecution(
    executionParams: {
      selector: $selector
      runConfigData: $runConfigData
      mode: "default"
      executionMetadata: { tags: $tags }
    }
  ) {
    __typename
    ... on LaunchRunSuccess { run { runId status } }
    ... on PythonError { message }
    ... on InvalidStepError { invalidStepKey }
    ... on InvalidOutputError { stepKey invalidOutputName }
    ... on RunConfigValidationInvalid { errors { message } }
    ... on RunConflict { message }
    ... on PresetNotFoundError { message }
    ... on ConflictingExecutionParamsError { message }
  }
}
""".strip()

_RUNS_QUERY = """
query($filter: RunsFilter!, $limit: Int!) {
  runsOrError(filter: $filter, limit: $limit) {
    __typename
    ... on Runs {
      results {
        runId
        status
        jobName
        startTime
        endTime
        tags { key value }
      }
    }
    ... on InvalidPipelineRunsFilterError { message }
    ... on PythonError { message }
  }
}
""".strip()

_STEP_STATS_QUERY = """
query($runId: ID!) {
  runOrError(runId: $runId) {
    __typename
    ... on Run {
      runId
      status
      stepStats { stepKey status }
    }
    ... on RunNotFoundError { message }
    ... on PythonError { message }
  }
}
""".strip()


def list_locations() -> list[dict[str, Any]]:
    """Workspace location entries, raw from GraphQL."""
    data = dagster_post(_LIST_LOCATIONS_QUERY)
    workspace = data.get("workspaceOrError") or {}
    return workspace.get("locationEntries") or []


def primary_repo() -> tuple[str, str | None]:
    """(location, repository) pair used for job launches."""
    entries = list_locations()
    if not entries:
        raise HTTPException(500, "No Dagster code locations found")
    loc = entries[0]["name"]
    repos = (entries[0].get("locationOrLoadError") or {}).get("repositories") or []
    return loc, (repos[0]["name"] if repos else None)


def reload_location(name: str) -> dict[str, Any]:
    data = dagster_post(_RELOAD_MUTATION, {"name": name})
    result = data.get("reloadRepositoryLocation") or {}
    tn = result.get("__typename")
    if tn in ("ReloadNotSupported", "RepositoryLocationNotFound", "PythonError"):
        raise HTTPException(
            500,
            f"Reload of '{name}' failed: {tn} — {result.get('message', '')}",
        )
    return result


def reload_all_locations() -> list[dict[str, Any]]:
    """Reload every code location so definitions pick up the saved config.

    Returns [{"name", "load_status"}, ...]; raises HTTPException on any failure.
    """
    entries = list_locations()
    if not entries:
        raise HTTPException(500, "No Dagster code locations found")
    results: list[dict[str, Any]] = []
    for entry in entries:
        result = reload_location(entry["name"])
        results.append(
            {"name": entry["name"], "load_status": result.get("loadStatus", "UNKNOWN")}
        )
    return results


def launch_job(job_name: str, tags: dict[str, str] | None = None) -> str:
    """Launch a job by name, return its run id. Raises HTTPException on failure."""
    loc, repo = primary_repo()
    if not repo:
        raise HTTPException(500, "Could not determine Dagster repository name")
    data = dagster_post(
        _LAUNCH_RUN_MUTATION,
        {
            "selector": {
                "repositoryLocationName": loc,
                "repositoryName": repo,
                "jobName": job_name,
            },
            "runConfigData": {},
            "tags": [{"key": k, "value": v} for k, v in (tags or {}).items()],
        },
    )
    result = data.get("launchPipelineExecution") or {}
    if result.get("__typename") != "LaunchRunSuccess":
        raise HTTPException(
            502,
            f"Dagster refused to launch {job_name}: "
            f"{result.get('__typename')} — {result.get('message', result)}",
        )
    return (result.get("run") or {}).get("runId") or ""


def _query_runs(filter_: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    data = dagster_post(_RUNS_QUERY, {"filter": filter_, "limit": limit})
    result = data.get("runsOrError") or {}
    if result.get("__typename") != "Runs":
        raise HTTPException(
            502,
            f"Dagster runs query failed: {result.get('__typename')} — {result.get('message', '')}",
        )
    runs = result.get("results") or []
    for run in runs:
        run["tags"] = {t["key"]: t["value"] for t in run.get("tags") or []}
    return runs


def runs_by_tag(key: str, value: str, limit: int = 50) -> list[dict[str, Any]]:
    """Runs carrying the given tag, newest first, tags flattened to a dict."""
    return _query_runs({"tags": [{"key": key, "value": value}]}, limit)


def in_progress_runs(job_names: tuple[str, ...]) -> list[dict[str, Any]]:
    """Unfinished runs of the given jobs, whatever started them (UI sync,
    Dagster UI, or the hourly schedule)."""
    runs = _query_runs({"statuses": list(IN_PROGRESS_STATUSES)}, 50)
    return [r for r in runs if r.get("jobName") in job_names]


def run_step_stats(run_id: str) -> list[dict[str, Any]]:
    """Per-step status for one run: [{"stepKey": ..., "status": ...}, ...]."""
    data = dagster_post(_STEP_STATS_QUERY, {"runId": run_id})
    result = data.get("runOrError") or {}
    if result.get("__typename") != "Run":
        return []
    return result.get("stepStats") or []
