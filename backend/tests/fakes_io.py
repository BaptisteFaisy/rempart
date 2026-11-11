"""Fakes d'entrées/sorties : GitHub (tickets) et S3 (rapports)."""

import uuid
from dataclasses import dataclass
from typing import Any


class FakeGitHub:
    """In-memory GitHub client fake."""

    def __init__(self, token: str = "fake-token", api: str = "https://api.github.com") -> None:
        self.token = token
        self.api = api
        self.issues: list[dict[str, Any]] = []

    def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        labels: list[str],
    ) -> dict[str, Any]:
        issue_number = len(self.issues) + 1
        url = f"https://github.com/{owner}/{repo}/issues/{issue_number}"
        issue = {
            "number": issue_number,
            "owner": owner,
            "repo": repo,
            "title": title,
            "body": body,
            "labels": labels,
            "state": "open",
            "html_url": url,
            "comments": [],
        }
        self.issues.append(issue)
        return {"html_url": url, "number": issue_number}

    def close_issue(self, owner: str, repo: str, number: int, comment: str) -> None:
        for it in self.issues:
            if it["owner"] == owner and it["repo"] == repo and it["number"] == number:
                it["state"] = "closed"
                it["comments"].append(comment)
                return


@dataclass
class FakeS3Object:
    key: str
    body: bytes
    content_type: str


class FakeS3:
    """In-memory S3 client fake for report uploads."""

    def __init__(self) -> None:
        self.objects: dict[str, FakeS3Object] = {}

    def put_object(
        self,
        Bucket: str,
        Key: str,
        Body: bytes | str,
        ContentType: str = "application/octet-stream",
        **kwargs: Any,
    ) -> dict[str, Any]:
        data = Body.encode("utf-8") if isinstance(Body, str) else Body
        self.objects[f"{Bucket}/{Key}"] = FakeS3Object(
            key=Key,
            body=data,
            content_type=ContentType,
        )
        return {"ETag": f'"{uuid.uuid4().hex}"'}

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        obj = self.objects.get(f"{Bucket}/{Key}")
        if not obj:
            raise KeyError(f"Key not found: {Key}")
        return {"Body": obj.body, "ContentType": obj.content_type}
