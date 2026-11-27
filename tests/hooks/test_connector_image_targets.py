"""Additional named image targets of a connector (PIPE-RELEASE-R001.15 to R001.17)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

from pipelines_hooks.connector import container
from pipelines_hooks.core.errors import CannotRun
from tests.git_fixture_environment import fixture_git_environment

ROOT = Path(__file__).parents[2]
WORKFLOWS = ROOT / ".github/workflows"
SHA = "b7d09d1aa7c346fed1e56390e815dbf1589d47324734fbad9e2007fe75ca0b8d"

PYPROJECT = f"""[project]
name = "demo-mcp"
version = "1.2.3"
[project.optional-dependencies]
mcp = []
[project.scripts]
demo-mcp = "demo_mcp.mcp_server:main"
[project.entry-points."scion_sdk.connector"]
demo-mcp = "demo_mcp"
[tool.pipelines.container.targets.studio]
template = "gui-runtime"
version = "4.5.17"
command = ["studio", "--python", "/opt/gui/startup.py"]
apt = ["libxi6", "python3"]
setup = ["mkdir -p /etc/studio-addons"]
licenses = "GPL-3.0-or-later"
notice = ["Studio is free software.", "Source: https://example.invalid/studio-${{version}}"]
viewer = true
[tool.pipelines.container.targets.studio.app]
url = "https://example.invalid/studio-${{version}}-linux-x64.tar.xz"
sha256 = "{SHA}"
link = "studio"
[tool.pipelines.container.targets.studio.env]
STUDIO_MODE = "headless"
[[tool.pipelines.container.targets.studio.files]]
source = "image/startup.py"
target = "/opt/gui/startup.py"
"""


def _repo(tmp_path: Path, pyproject: str = PYPROJECT) -> Path:
    root = tmp_path / "demo-mcp"
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    return root


@pytest.mark.spec("PIPE-RELEASE-R001.15")
def test_a_declared_target_renders_a_dockerfile_and_an_entrypoint(tmp_path: Path) -> None:
    files = container.render(_repo(tmp_path))
    assert {"studio.Dockerfile", "studio.entrypoint.sh", "Dockerfile", "mcp.compose.yml"} <= set(files)
    assert "@@" not in files["studio.Dockerfile"] + files["studio.entrypoint.sh"]
    assert "COPY --chmod=0644 image/startup.py /opt/gui/startup.py" in files["studio.Dockerfile"]
    assert "studio-4.5.17-linux-x64.tar.xz" in files["studio.Dockerfile"]
    assert "exec studio --python /opt/gui/startup.py" in files["studio.entrypoint.sh"]
    assert "ENV STUDIO_MODE=headless" in files["studio.Dockerfile"]


@pytest.mark.spec("PIPE-RELEASE-R001.15")
def test_target_render_is_deterministic_and_commits_nothing(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    assert container.render(root) == container.render(root)
    no_target = _repo(tmp_path / "plain", PYPROJECT.split("[tool.pipelines.container.targets.studio]")[0])
    assert set(container.render(no_target)) == {"Dockerfile", "debug.Dockerfile", "mcp.compose.yml"}


@pytest.mark.spec("PIPE-RELEASE-R001.15")
@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('template = "gui-runtime"', 'template = "other"', "template"),
        ('template = "gui-runtime"', 'template = "gui-runtime"\nsurprise = 1', "unknown keys"),
        (f'sha256 = "{SHA}"', 'sha256 = "abc"', "app.sha256"),
        ('url = "https://example', 'url = "http://example', "https URL"),
        ('command = ["studio", "--python", "/opt/gui/startup.py"]', "", "command is required"),
        ('target = "/opt/gui/startup.py"', 'target = "/opt/../startup.py"', "files.target"),
        ('template = "gui-runtime"', 'template = "gui-runtime"\nuid = 0', "uid"),
        ('template = "gui-runtime"', 'template = "gui-runtime"\nbase = "ubuntu:24.04"', "digest"),
        ("targets.studio]", "targets.mcp]", "reserved"),
    ],
)
def test_a_bad_target_table_refuses_before_any_file_is_written(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    root = _repo(tmp_path, PYPROJECT.replace(old, new))
    with pytest.raises(CannotRun, match=message):
        container.render(root)
    assert not (root / "docker").exists()


@pytest.mark.spec("PIPE-RELEASE-R001.15")
def test_check_fails_a_committed_target_rendering(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path)
    assert container.main(["--root", str(root), "--out", str(root / "docker")]) == 0
    assert container.main(["--root", str(root), "--check"]) == 0
    env = fixture_git_environment()
    subprocess.run(["git", "-C", str(root), "init", "-q"], env=env, check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "add", "--", "docker/studio.Dockerfile"], env=env, check=True)
    assert container.main(["--root", str(root), "--check"]) == 1
    assert "docker/studio.Dockerfile is committed" in capsys.readouterr().out


@pytest.mark.spec("PIPE-RELEASE-R001.16")
def test_the_connector_pipeline_publishes_each_declared_target_after_the_primary_image() -> None:
    jobs = yaml.safe_load((WORKFLOWS / "connector_pipeline.yml").read_text(encoding="utf-8"))["jobs"]
    listing, targets = jobs["image-target-list"], jobs["docker-targets"]
    assert "tool.pipelines" not in str(listing["steps"][0]) and "targets" in listing["outputs"]
    assert {"publish-docker", "image-target-list", "auto-tag"} <= set(targets["needs"])
    assert "needs.publish-docker.result == 'success'" in targets["if"]
    assert targets["uses"].endswith("/container_pipeline.yml@main")
    with_ = targets["with"]
    assert with_["image_target"] == "${{ matrix.target }}"
    assert with_["dockerfile"] == "docker/${{ matrix.target }}.Dockerfile" and with_["build_target"] == "default"
    assert targets["strategy"]["matrix"]["target"] == "${{ fromJSON(needs.image-target-list.outputs.targets) }}"
    assert not any(name.startswith("publish-") for name in ("image-target-list", "docker-targets"))
    assert {"image-target-list", "docker-targets"} <= set(jobs["ci-required"]["needs"])
    assert all(scope != "write" for job in (listing, targets) for scope in job["permissions"].values())


@pytest.mark.spec("PIPE-RELEASE-R001.16")
def test_the_container_pipeline_suffixes_every_tag_and_verifies_the_suffixed_tag() -> None:
    text = (WORKFLOWS / "container_pipeline.yml").read_text(encoding="utf-8")
    document = yaml.safe_load(text)
    assert document[True]["workflow_call"]["inputs"]["image_target"]["default"] == ""
    steps = document["jobs"]["publish-docker"]["steps"]
    meta = next(step for step in steps if step.get("id") == "meta")
    assert (
        "suffix=${{ inputs.image_target != '' && format('-{0}', inputs.image_target) || '' }}" in meta["with"]["flavor"]
    )
    verify = next(step for step in steps if step.get("name") == "Verify the release artifacts")
    assert 'tag="${tag}${IMAGE_SUFFIX}"' in verify["run"] and "IMAGE_SUFFIX" in verify["env"]
    target = next(step for step in steps if step.get("id") == "target")
    assert "docker/${IMAGE_TARGET}.Dockerfile" in target["run"]
    builds = [step for step in steps if "docker/build-push-action@" in step.get("uses", "")]
    assert len(builds) == 3 and builds[0]["with"] == builds[1]["with"] == builds[2]["with"]


def _target_files(tmp_path: Path, pyproject: str = PYPROJECT) -> dict[str, str]:
    return container.render(_repo(tmp_path, pyproject))


@pytest.mark.spec("PIPE-RELEASE-R001.17")
def test_the_gui_runtime_dockerfile_verifies_the_archive_and_runs_non_root(tmp_path: Path) -> None:
    docker = _target_files(tmp_path)["studio.Dockerfile"]
    assert re.search(r"^FROM ubuntu:24\.04@sha256:[0-9a-f]{64}$", docker, re.MULTILINE)
    assert f'echo "{SHA}  /tmp/app.archive" | sha256sum -c -' in docker
    assert docker.index("sha256sum -c") < docker.index("tar -xJf")
    assert "ln -s /opt/app/studio /usr/local/bin/studio" in docker
    assert "NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics" in docker
    assert "org.opencontainers.image.licenses=GPL-3.0-or-later" in docker
    assert "/usr/share/doc/studio-image/NOTICE" in docker and "studio-4.5.17" in docker
    assert docker.rstrip().splitlines()[-3] == "USER 10001" and "xvfb-run" not in docker
    assert "libxi6" in docker and "xserver-xorg-core" in docker and "x11vnc" in docker


@pytest.mark.spec("PIPE-RELEASE-R001.17")
def test_the_entrypoint_starts_the_display_directly_with_a_mode_switch(tmp_path: Path) -> None:
    script = _target_files(tmp_path)["studio.entrypoint.sh"]
    assert not [line for line in script.splitlines() if "xvfb-run" in line and not line.startswith("#")]
    assert 'Xvfb "$DISPLAY_NAME" -screen 0' in script and "/usr/lib/xorg/Xorg" in script
    for mode in ("auto", "nvidia", "xvfb"):
        assert f"{mode})" in script
    assert 'Driver "nvidia"' in script and 'Option "AllowEmptyInitialConfiguration"' in script
    assert "nvidia-smi --query-gpu=pci.bus_id" in script


@pytest.mark.spec("PIPE-RELEASE-R001.17")
def test_the_entrypoint_falls_back_to_software_and_refuses_an_unknown_mode(tmp_path: Path) -> None:
    script = _target_files(tmp_path)["studio.entrypoint.sh"]
    assert "falling back to software" in script and "no GPU display available; using software" in script
    assert "display mode nvidia requested but no GPU display is available" in script
    path = tmp_path / "entry.sh"
    path.write_text(script, encoding="utf-8")
    result = subprocess.run(
        ["sh", str(path), "app"],
        env={"GUI_DISPLAY_MODE": "bogus", "HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 2 and "unknown GUI_DISPLAY_MODE: bogus" in result.stdout


@pytest.mark.spec("PIPE-RELEASE-R001.17")
def test_the_viewer_mode_is_rendered_only_when_declared(tmp_path: Path) -> None:
    on = _target_files(tmp_path / "on")
    off = _target_files(tmp_path / "off", PYPROJECT.replace("viewer = true\n", ""))
    assert "x11vnc" in on["studio.Dockerfile"] and "x11vnc" not in off["studio.Dockerfile"]
    script = on["studio.entrypoint.sh"]
    assert "-localhost" in script and "GUI_VNC_PASSWORD_FILE" in script and "authenticating gateway" in script
    assert "websockify --web /usr/share/novnc" in script
    assert script.count("viewer)") == 1
