"""Tests for the GitHub ticketing client (EF-COR-01/02, R6)."""

from rempart.orchestrator.github_client import GitHubClient


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.status_code = 201

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_create_issue_posts_and_returns_url(monkeypatch):
    seen: dict = {}

    def _post(url, json=None, headers=None, timeout=None):
        seen["url"] = url
        seen["json"] = json
        seen["headers"] = headers
        return _FakeResponse({"html_url": "https://github.com/acme/shop/issues/1", "number": 1})

    monkeypatch.setattr("rempart.orchestrator.github_client.requests.post", _post)
    client = GitHubClient(token="tok")
    issue = client.create_issue(
        owner="acme", repo="shop", title="[P1] IDOR", body="details", labels=["security"]
    )
    assert issue["html_url"].endswith("/issues/1")
    assert seen["url"] == "https://api.github.com/repos/acme/shop/issues"
    assert seen["json"]["labels"] == ["security"]
    assert seen["headers"]["Authorization"] == "Bearer tok"


def test_close_issue_posts_comment_then_patches(monkeypatch):
    calls: list[tuple[str, str]] = []

    def _post(url, json=None, headers=None, timeout=None):
        calls.append(("post", url))
        return _FakeResponse({})

    def _patch(url, json=None, headers=None, timeout=None):
        calls.append(("patch", url))
        return _FakeResponse({})

    monkeypatch.setattr("rempart.orchestrator.github_client.requests.post", _post)
    monkeypatch.setattr("rempart.orchestrator.github_client.requests.patch", _patch)
    client = GitHubClient(token="tok")
    client.close_issue("acme", "shop", 42, "closed by Rempart")
    assert calls[0][0] == "post"
    assert calls[0][1].endswith("/issues/42/comments")
    assert calls[1][0] == "patch"
    assert calls[1][1].endswith("/issues/42")


def test_base_url_is_normalised():
    client = GitHubClient(token="tok", api="https://ghe.example.com/")
    assert client.api == "https://ghe.example.com"
