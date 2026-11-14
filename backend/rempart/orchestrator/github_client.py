"""GitHub REST client for issue-based ticketing (EF-COR-01/02)."""

import os
from typing import Any

import requests

#: Jetons acceptés, du plus spécifique (prod, injecté depuis Secrets Manager)
#: au plus générique (test local) — voir CONTRACT.md, variables d'environnement.
#: Vivait dans `orchestrator/lambda_handlers.py` ; la revue de code en a le même
#: besoin, donc une seule définition partagée (aucun duplicata à désynchroniser).
GITHUB_TOKEN_ENVS = ("REMPART_GITHUB_TOKEN", "GITHUB_TOKEN")


def github_token_from_env() -> str | None:
    """Premier jeton GitHub présent dans l'environnement, sinon ``None``."""
    for name in GITHUB_TOKEN_ENVS:
        token = os.environ.get(name)
        if token:
            return token
    return None


class GitHubClient:
    """Minimal GitHub API client using ``requests``."""

    def __init__(self, token: str, api: str = "https://api.github.com") -> None:
        self.token = token
        self.api = api.rstrip("/")

    def _headers(self, accept: str = "application/vnd.github+json") -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": accept,
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

    def fetch_diff(self, path: str) -> str:
        """Récupère un diff au format `application/vnd.github.diff`.

        `path` est relatif à l'API (ex. `repos/o/r/pulls/42`). C'est la seule
        façon d'obtenir le diff d'une PR sans recalculer soi-même les fichiers :
        GitHub fournit le diff exact que le merge introduirait.
        """
        url = f"{self.api}/{path.lstrip('/')}"
        resp = requests.get(
            url, headers=self._headers(accept="application/vnd.github.diff"), timeout=30
        )
        resp.raise_for_status()
        return resp.text
