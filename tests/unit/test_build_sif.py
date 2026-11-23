"""Tests for tools/build_sif.sbatch, run with a fake `apptainer` on PATH that records its calls."""

import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
from container_manifest import cache_filename

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "build_sif.sbatch"
JOB = "4242"

FAKE = f"""#!{sys.executable}
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write(json.dumps({{"argv": args, "tmpdir": os.environ.get("APPTAINER_TMPDIR"),
                         "cachedir": os.environ.get("APPTAINER_CACHEDIR")}}) + "\\n")
if args == ["--version"]:
    print("apptainer version 1.4.0-fake"); sys.exit(0)
if args[:2] == ["build", "--help"]:
    print("--mksquashfs-args string   extra arguments to pass to mksquashfs"); sys.exit(0)
if args[0] == "build":
    pos = [a for i, a in enumerate(args[1:], 1) if not a.startswith("-") and args[i - 1] != "--mksquashfs-args"]
    out = Path(pos[0])
    counter = Path(os.environ["FAKE_LOG"] + ".builds")
    n = int(counter.read_text()) + 1 if counter.exists() else 1
    counter.write_text(str(n))
    if os.environ.get("FAKE_FAIL_ALWAYS") or n <= int(os.environ.get("FAKE_FAIL_FIRST", "0")):
        out.write_text("half-written")
        print("FATAL: fake network error", file=sys.stderr); sys.exit(255)
    out.write_text("SIF_MAGIC fake image " + os.environ.get("FAKE_CONTENT", ""))
sys.exit(0)
"""


@pytest.fixture
def env(tmp_path):
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    fake = fakebin / "apptainer"
    fake.write_text(FAKE)
    fake.chmod(0o755)
    keep = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "LC_ALL")}
    return {
        **keep,
        "PATH": f"{fakebin}:{keep['PATH']}",
        "USER": "tester",
        "HOME": str(tmp_path / "home"),
        "TMPDIR": str(tmp_path / "tmpbase"),
        "APPTAINER_CACHEDIR": str(tmp_path / "cache"),
        "SLURM_JOB_ID": JOB,
        "SLURM_CPUS_PER_TASK": "16",
        "SLURM_MEM_PER_NODE": "32768",
        "BUILD_SIF_RETRY_SLEEP": "0",
        "FAKE_LOG": str(tmp_path / "calls.jsonl"),
    }


BASH = shutil.which("bash")


def run(env, *args, cwd):
    cmd = [BASH, str(SCRIPT), "--need-gb", "0", *args]
    return subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, text=True)  # noqa: S603  our script, test args


def calls(env):
    log = Path(env["FAKE_LOG"])
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def builds(env):
    return [c for c in calls(env) if c["argv"][0] == "build" and c["argv"][1:] != ["--help"]]


def make_tar(path, members):
    with tarfile.open(path, "w") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


def test_registry_builds_docker_ref_with_nextflow_name(env, tmp_path):
    out = tmp_path / "out"
    r = run(env, "docker.io/josenimo/nimbus:0.0.5", str(out), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    sif = out / "docker.io-josenimo-nimbus-0.0.5.img"
    assert sif.read_text().startswith("SIF_MAGIC")
    (b,) = builds(env)
    assert b["argv"][-1] == "docker://docker.io/josenimo/nimbus:0.0.5"
    assert b["argv"][1:3] == ["--mksquashfs-args", "-processors 16 -mem 16384M"]
    assert b["tmpdir"] == str(tmp_path / "tmpbase" / f"build_sif.{JOB}")
    assert not Path(b["tmpdir"]).exists(), "job temp dir is cleaned up"
    assert [p.name for p in out.iterdir()] == [sif.name], "no partial file left behind"
    assert f'rsync -av --ignore-existing {sif} "$NXF_SINGULARITY_CACHEDIR/"' in r.stdout
    assert "sha256:" in r.stdout


@pytest.mark.parametrize(
    "ref",
    [
        "docker.io/josenimo/nimbus:0.0.5",
        "docker://ghcr.io/schapirolabor/background_subtraction:v0.5.1",
        "quay.io/biocontainers/ashlar:1.19.0--pyhdfd78af_0",
    ],
)
def test_name_matches_container_manifest(env, tmp_path, ref):
    """Same rule as tools/container_manifest.py, which mirrors Nextflow's SingularityCache."""
    out = tmp_path / "out"
    assert run(env, ref, str(out), cwd=tmp_path).returncode == 0
    assert (out / cache_filename(ref.removeprefix("docker://"))).exists()


def test_untagged_ref_refused(env, tmp_path):
    r = run(env, "docker.io/josenimo/nimbus", str(tmp_path / "out"), cwd=tmp_path)
    assert r.returncode != 0 and "no tag" in r.stderr
    assert builds(env) == []


def test_docker_save_tar_uses_docker_archive(env, tmp_path):
    # Docker 25+ writes index.json and oci-layout too; manifest.json must still win.
    tar = make_tar(
        tmp_path / "nimbus.tar",
        {"manifest.json": b"[]", "index.json": b"{}", "oci-layout": b"{}", "repositories": b"{}"},
    )
    out = tmp_path / "out"
    r = run(env, "--name", "docker.io-josenimo-nimbus-0.0.5.img", str(tar), str(out), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    (b,) = builds(env)
    assert b["argv"][-1] == f"docker-archive://{tar.resolve()}"
    assert (out / "docker.io-josenimo-nimbus-0.0.5.img").exists()


def test_oci_archive_tar_uses_oci_archive(env, tmp_path):
    # Misleading extension on purpose: the contents decide.
    tar = make_tar(tmp_path / "image.docker.tar", {"./oci-layout": b"{}", "./index.json": b"{}"})
    r = run(env, "--name", "x.img", str(tar), str(tmp_path / "out"), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert builds(env)[0]["argv"][-1] == f"oci-archive://{tar.resolve()}"


def test_oci_layout_dir_uses_oci(env, tmp_path):
    layout = tmp_path / "layout"
    (layout / "blobs" / "sha256").mkdir(parents=True)
    (layout / "oci-layout").write_text("{}")
    (layout / "index.json").write_text("{}")
    r = run(env, "--name", "x.img", str(layout), str(tmp_path / "out"), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert builds(env)[0]["argv"][-1] == f"oci://{layout.resolve()}"


def test_local_source_needs_name(env, tmp_path):
    tar = make_tar(tmp_path / "nimbus.tar", {"manifest.json": b"[]"})
    r = run(env, str(tar), str(tmp_path / "out"), cwd=tmp_path)
    assert r.returncode != 0 and "--name is required" in r.stderr
    assert builds(env) == []


def test_unknown_tar_refused(env, tmp_path):
    tar = make_tar(tmp_path / "random.tar", {"hello.txt": b"hi"})
    r = run(env, "--name", "x.img", str(tar), str(tmp_path / "out"), cwd=tmp_path)
    assert r.returncode != 0 and "neither manifest.json" in r.stderr
    assert builds(env) == []


def test_existing_sif_is_a_noop(env, tmp_path):
    sif = tmp_path / "already.sif"
    sif.write_bytes(b"#!/usr/bin/env run-singularity\n\x00SIF_MAGIC\x00rest")
    r = run(env, str(sif), str(tmp_path / "out"), cwd=tmp_path)
    assert r.returncode == 0 and "nothing to build" in r.stdout
    assert builds(env) == []


def test_refuses_overwrite_without_force(env, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    existing = out / "docker.io-josenimo-nimbus-0.0.5.img"
    existing.write_text("old")
    r = run(env, "docker.io/josenimo/nimbus:0.0.5", str(out), cwd=tmp_path)
    assert r.returncode != 0 and "already exists" in r.stderr and "--force" in r.stderr
    assert existing.read_text() == "old"
    assert builds(env) == []

    env["FAKE_CONTENT"] = "new"
    r = run(env, "--force", "docker.io/josenimo/nimbus:0.0.5", str(out), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert existing.read_text().endswith("new")


def test_failed_build_leaves_no_file(env, tmp_path):
    env["FAKE_FAIL_ALWAYS"] = "1"
    env["BUILD_SIF_ATTEMPTS"] = "2"
    out = tmp_path / "out"
    r = run(env, "docker.io/josenimo/nimbus:0.0.5", str(out), cwd=tmp_path)
    assert r.returncode != 0
    assert "failed 2 times for docker://docker.io/josenimo/nimbus:0.0.5" in r.stderr
    assert len(builds(env)) == 2
    assert list(out.iterdir()) == [], "neither the final name nor a partial file"
    assert not (tmp_path / "tmpbase" / f"build_sif.{JOB}").exists()


def test_failed_local_build_leaves_no_file(env, tmp_path):
    env["FAKE_FAIL_ALWAYS"] = "1"
    tar = make_tar(tmp_path / "nimbus.tar", {"manifest.json": b"[]"})
    out = tmp_path / "out"
    r = run(env, "--name", "x.img", str(tar), str(out), cwd=tmp_path)
    assert r.returncode != 0 and "apptainer build failed" in r.stderr
    assert len(builds(env)) == 1, "no retries for a local source"
    assert list(out.iterdir()) == []


def test_registry_retries_transient_failure(env, tmp_path):
    env["FAKE_FAIL_FIRST"] = "2"
    out = tmp_path / "out"
    r = run(env, "docker.io/josenimo/nimbus:0.0.5", str(out), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert len(builds(env)) == 3
    assert "attempt 2 of 4 failed" in r.stdout
    assert (out / "docker.io-josenimo-nimbus-0.0.5.img").read_text().startswith("SIF_MAGIC")


def test_never_writes_to_nxf_cache(env, tmp_path):
    cache = tmp_path / "shared_cache"
    cache.mkdir()
    env["NXF_SINGULARITY_CACHEDIR"] = str(cache)
    assert run(env, "docker.io/josenimo/nimbus:0.0.5", str(tmp_path / "out"), cwd=tmp_path).returncode == 0
    for target in (cache, cache / "sub"):
        r = run(env, "docker.io/josenimo/nimbus:0.0.5", str(target), cwd=tmp_path)
        assert r.returncode != 0 and "inside NXF_SINGULARITY_CACHEDIR" in r.stderr
    env["TMPDIR"] = str(cache)
    assert run(env, "docker.io/josenimo/nimbus:0.0.5", str(tmp_path / "out2"), cwd=tmp_path).returncode != 0
    assert list(cache.iterdir()) == []
    assert all(not str(a).startswith(str(cache)) for c in calls(env) for a in c["argv"])


def test_credentials_never_printed(env, tmp_path):
    env["APPTAINER_DOCKER_USERNAME"] = "someuser"
    env["APPTAINER_DOCKER_PASSWORD"] = "s3cr3t-token"  # noqa: S105  fake value
    r = run(env, "docker.io/josenimo/nimbus:0.0.5", str(tmp_path / "out"), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "s3cr3t-token" not in r.stdout + r.stderr
    assert "someuser" not in r.stdout + r.stderr
