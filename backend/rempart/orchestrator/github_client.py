"""GitHub REST client for issue-based ticketing (EF-COR-01/02)."""

from typing import Any

import requests


class GitHubClient:
    """Minimal GitHub API client using ``requests``."""

    def __init__(self, token: str, api: str = "https://api.github.com") -> None:
        self.token = token
        self.api = api.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        labels: list[str],
    ) -> dict[str, Any]:
        """Create an issue and return the API response (contains ``html_url``)."""
        url = f"{self.api}/repos/{owner}/{repo}/issues"
        payload = {"title": title, "body": body, "labels": list(labels)}
        resp = requests.post(url, json=payload, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()

    def close_issue(self, owner: str, repo: str, number: int, comment: str) -> None:
        """Post a closing comment then close the issue (R6 audit proof)."""
        base = f"{self.api}/repos/{owner}/{repo}/issues/{number}"
        if comment:
            c_resp = requests.post(
                f"{base}/comments",
                json={"body": comment},
                headers=self._headers(),
                timeout=30,
            )
            c_resp.raise_for_status()
        resp = requests.patch(
            base,
            json={"state": "closed"},
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
