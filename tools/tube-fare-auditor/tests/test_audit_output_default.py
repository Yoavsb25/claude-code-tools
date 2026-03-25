import importlib.util
import sys
from pathlib import Path


def load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if not spec or not spec.loader:
        raise ImportError(f"Could not load module {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_default_output_uses_secure_temp_dir(tmp_path, monkeypatch):
    script_dir = Path(__file__).resolve().parents[1] / "scripts"
    audit_path = script_dir / "audit.py"
    audit = load_module("audit_test_output_default", audit_path)

    called = {"prefix": None}
    out_dir = tmp_path / "tube_audit_output_default"

    def fake_mkdtemp(prefix):
        called["prefix"] = prefix
        return str(out_dir)

    monkeypatch.setattr(audit.tempfile, "mkdtemp", fake_mkdtemp)

    captured = {}

    def fake_run_audit(oyster_files, card_file, railcard_key, output_dir, tfl_api_key):
        captured["output_dir"] = output_dir

    monkeypatch.setattr(audit, "run_audit", fake_run_audit)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audit.py",
            "--oyster",
            "dummy.csv",
        ],
    )

    audit.main()

    if called["prefix"] != "tube_audit_output_":
        raise AssertionError(f"Expected tempfile prefix 'tube_audit_output_', got: {called['prefix']}")
    if captured["output_dir"] != str(out_dir):
        raise AssertionError(f"Expected output_dir '{out_dir}', got: {captured['output_dir']}")

