from package_github_dwh_blue.extract import GitHub


class Response:
    def __init__(self, data, next_url=None):
        self._data = data
        self.links = {"next": {"url": next_url}} if next_url else {}
    def raise_for_status(self): pass
    def json(self): return self._data


def test_pages_handles_github_lists(monkeypatch):
    client = GitHub("token")
    responses = iter([Response([{"id": 1}], "https://next"), Response([{"id": 2}])])
    monkeypatch.setattr(client.session, "get", lambda *a, **k: next(responses))
    assert [x["id"] for x in client.pages("/orgs/getcolors/repos")] == [1, 2]


def test_pages_handles_workflow_envelope(monkeypatch):
    client = GitHub("token")
    monkeypatch.setattr(client.session, "get", lambda *a, **k: Response({"workflow_runs": [{"id": 7}]}))
    assert list(client.pages("/repos/getcolors/blue/actions/runs")) == [{"id": 7}]
