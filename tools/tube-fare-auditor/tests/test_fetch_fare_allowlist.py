import importlib.util
from pathlib import Path


def load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if not spec or not spec.loader:
        raise ImportError(f"Could not load module {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_api_get_rejects_wrong_scheme(tmp_path, monkeypatch):
    script_dir = Path(__file__).resolve().parents[1] / "scripts"
    fetch_fare_path = script_dir / "fetch_fare.py"
    fetch_fare = load_module("fetch_fare_test_scheme", fetch_fare_path)

    monkeypatch.setattr(fetch_fare, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(fetch_fare, "STOP_CACHE_FILE", fetch_fare.CACHE_DIR / "stop_ids.json")
    monkeypatch.setattr(fetch_fare, "FARE_CACHE_FILE", fetch_fare.CACHE_DIR / "fares.json")

    monkeypatch.setattr(fetch_fare, "TFL_API_BASE", "http://api.tfl.gov.uk")

    fetcher = fetch_fare.TflFareFetcher(api_key=None)
    result = fetcher._api_get("/StopPoint/search/test")
    if result is not None:
        raise AssertionError(f"Expected None for wrong scheme, got: {result}")


def test_api_get_rejects_wrong_host(tmp_path, monkeypatch):
    script_dir = Path(__file__).resolve().parents[1] / "scripts"
    fetch_fare_path = script_dir / "fetch_fare.py"
    fetch_fare = load_module("fetch_fare_test_host", fetch_fare_path)

    monkeypatch.setattr(fetch_fare, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(fetch_fare, "STOP_CACHE_FILE", fetch_fare.CACHE_DIR / "stop_ids.json")
    monkeypatch.setattr(fetch_fare, "FARE_CACHE_FILE", fetch_fare.CACHE_DIR / "fares.json")

    monkeypatch.setattr(fetch_fare, "TFL_API_BASE", "https://example.com")

    fetcher = fetch_fare.TflFareFetcher(api_key=None)
    result = fetcher._api_get("/StopPoint/search/test")
    if result is not None:
        raise AssertionError(f"Expected None for wrong host, got: {result}")


def test_api_get_allows_expected_host_and_calls_urlopen(tmp_path, monkeypatch):
    script_dir = Path(__file__).resolve().parents[1] / "scripts"
    fetch_fare_path = script_dir / "fetch_fare.py"
    fetch_fare = load_module("fetch_fare_test_allow", fetch_fare_path)

    monkeypatch.setattr(fetch_fare, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(fetch_fare, "STOP_CACHE_FILE", fetch_fare.CACHE_DIR / "stop_ids.json")
    monkeypatch.setattr(fetch_fare, "FARE_CACHE_FILE", fetch_fare.CACHE_DIR / "fares.json")

    calls = {"count": 0}

    def fake_urlopen(req, timeout=15):
        calls["count"] += 1

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                # Minimal valid JSON response.
                return b'{"ok": true}'

        return FakeResponse()

    monkeypatch.setattr(fetch_fare.urllib.request, "urlopen", fake_urlopen)

    fetcher = fetch_fare.TflFareFetcher(api_key=None)
    result = fetcher._api_get("/StopPoint/search/test", params=None)
    if result != {"ok": True}:
        raise AssertionError(f"Unexpected _api_get result: {result}")
    if calls["count"] != 1:
        raise AssertionError(f"Expected 1 urlopen call, got: {calls['count']}")

