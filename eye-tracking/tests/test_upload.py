"""Upload client against a local stub HTTP server (no network, no Supabase)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from eyetrack.upload import create_session, upload_batch

SEEN = []


class Stub(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append((self.path, self.headers["Authorization"], body))
        if self.headers["Authorization"] != "Bearer dk_test":
            code, out = 401, {"error": "invalid or revoked device key"}
        elif self.path == "/api/v1/sessions":
            code, out = 201, {"session_id": "00000000-0000-4000-8000-0000000000aa"}
        else:
            code, out = 201, {"recording_id": "r1", "n_measurements": len(body["measurements"])}
        data = json.dumps(out).encode()
        self.send_response(code); self.send_header("Content-Length", str(len(data))); self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.fixture()
def server():
    srv = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_session_then_upload(server):
    sid = create_session("SYN-001", api_url=server, key="dk_test")
    batch = {"schema_version": "1.0", "session_id": sid, "recording": {}, "measurements": [{"name": "x"}]}
    r = upload_batch(batch, api_url=server, key="dk_test")
    assert r["n_measurements"] == 1
    assert SEEN[-1][0] == "/api/v1/ingest" and SEEN[-1][1] == "Bearer dk_test"
    assert SEEN[-2][2] == {"participant_code": "SYN-001", "protocol": "eye_v1"}


def test_bad_key_is_a_clear_error(server):
    with pytest.raises(SystemExit, match="401"):
        upload_batch({"session_id": "s", "measurements": []}, api_url=server, key="dk_wrong")


def test_missing_config_is_a_clear_error(monkeypatch, tmp_path):
    import eyetrack.upload as up
    monkeypatch.setattr(up, "ENV_FILE", tmp_path / "missing.env")  # ignore a real .env on this machine
    monkeypatch.delenv("EYETRACK_API_URL", raising=False)
    monkeypatch.delenv("EYETRACK_DEVICE_KEY", raising=False)
    with pytest.raises(SystemExit, match="EYETRACK_API_URL"):
        upload_batch({"session_id": "s"})


def test_reads_eye_tracking_env_file(tmp_path, monkeypatch):
    import eyetrack.upload as up
    env = tmp_path / ".env"
    env.write_text('# comment\nEYETRACK_API_URL="http://example.test/"\nEYETRACK_DEVICE_KEY=dk_fromfile\n')
    monkeypatch.setattr(up, "ENV_FILE", env)
    monkeypatch.delenv("EYETRACK_API_URL", raising=False)
    monkeypatch.delenv("EYETRACK_DEVICE_KEY", raising=False)
    assert up._cfg(None, None) == ("http://example.test", "dk_fromfile")
    monkeypatch.setenv("EYETRACK_DEVICE_KEY", "dk_env")       # real env var wins
    assert up._cfg(None, None)[1] == "dk_env"
