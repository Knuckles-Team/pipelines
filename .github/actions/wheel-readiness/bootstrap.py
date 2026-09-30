"""Bootstrap the reviewed resolver from one hash-pinned public wheel."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.request

PIN = json.loads(Path(__file__).with_name("resolver-pin.json").read_text())


def environment(home: Path) -> dict[str, str]:
    """Do not inherit caller indexes, proxies, Python imports, or pip config."""
    return {
        "PATH": os.defpath, "HOME": str(home), "USERPROFILE": str(home),
        "PIP_CONFIG_FILE": os.devnull, "PYTHONNOUSERSITE": "1",
        **({"SYSTEMROOT": os.environ["SYSTEMROOT"]} if "SYSTEMROOT" in os.environ else {}),
    }


def verify_pin(wheel: Path) -> None:
    payload = wheel.read_bytes()
    if len(payload) != PIN["size"] or hashlib.sha256(payload).hexdigest() != PIN["sha256"]:
        raise ValueError("resolver wheel does not match the reviewed pin")


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("resolver bootstrap redirects are forbidden")


def download(directory: Path) -> Path:
    # TLS defaults must not be redirected by caller certificate configuration.
    saved = {key: os.environ.pop(key) for key in ("SSL_CERT_FILE", "SSL_CERT_DIR") if key in os.environ}
    try:
        context = ssl.create_default_context()
    finally:
        os.environ.update(saved)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context), NoRedirects()
    )
    with opener.open(PIN["url"], timeout=60) as response:
        if response.status != 200:
            raise ValueError("resolver bootstrap did not return a wheel")
        payload = response.read(PIN["size"] + 1)
    wheel = directory / PIN["filename"]
    wheel.write_bytes(payload)
    verify_pin(wheel)
    return wheel


def create(directory: Path, pinned_wheel: Path) -> Path:
    verify_pin(pinned_wheel)
    env = environment(directory.parent)
    subprocess.run([sys.executable, "-I", "-m", "venv", str(directory)],
                   env=env, cwd=directory.parent, check=True, timeout=120)
    python = directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run(
        [str(python), "-I", "-m", "pip", "install", "--no-index", "--no-deps",
         "--disable-pip-version-check", "--no-cache-dir", "--force-reinstall", str(pinned_wheel)],
        env=env, cwd=directory.parent, check=True, timeout=120,
    )
    # Keep the verified input for subsequent profile venvs; they never fetch pip.
    destination = directory / PIN["filename"]
    if destination.resolve() != pinned_wheel.resolve():
        shutil.copyfile(pinned_wheel, destination)
    verify_pin(destination)
    return python


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="resolver-download-") as temporary:
        wheel = download(Path(temporary))
        directory = Path(tempfile.mkdtemp(prefix="wheel-checker-", dir=os.environ["RUNNER_TEMP"]))
        python = create(directory, wheel)
    with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as stream:
        stream.write(f"READINESS_PYTHON={python.as_posix()}\n")
