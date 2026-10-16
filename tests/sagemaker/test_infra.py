"""
Static checks for the SageMaker pipeline: the pieces live in different files
(launcher, configs, IAM, workflows, Dockerfile, setup script) and only work if
they agree. Each test pins one of those agreements. Needs only pyyaml +
pytest; the metric-format test also runs when torch/peft are installed.

    pytest tests/sagemaker -q
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
INFRA = ROOT / "aws-infra"
SM = ROOT / "aws-sagemaker"
WORKFLOWS = ROOT / ".github" / "workflows"

ACCOUNT, REGION = "123456789012", "us-east-1"
SAGEMAKER_ROLE = "forgery-sagemaker-role"
ECR_REPOSITORY = "forgery-train"

# the configs the workflows run: smoke (Smoke test) + every Run training choice
SMOKE_CONFIG = "config/smoke.yml"


def render(path: Path) -> str:
    # the Python twin of aws-infra/render.sh
    return path.read_text(encoding="utf-8").replace("${AWS_ACCOUNT_ID}", ACCOUNT).replace("${AWS_REGION}", REGION)


def config(rel: str) -> dict:
    return yaml.safe_load((SM / rel).read_text(encoding="utf-8"))


def workflow(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def workflow_text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def run_training_configs() -> list[str]:
    return workflow("run-training.yml")[True]["workflow_dispatch"]["inputs"]["config"]["options"]


def all_configs() -> list[str]:
    return [SMOKE_CONFIG] + run_training_configs()


def metric_definitions() -> list[dict]:
    tree = ast.parse((SM / "launch.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "METRIC_DEFS" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("launch.py has no METRIC_DEFS literal")


# ------------------------------------------------------------------
# The three workflows
# ------------------------------------------------------------------

def test_exactly_the_three_aws_workflows_exist():
    names = {workflow(f.name)["name"] for f in WORKFLOWS.glob("*.yml")}
    assert {"Build training image", "Smoke test", "Run training"} <= names
    assert "Deploy pipelines" not in names
    for f in WORKFLOWS.glob("*.yml"):
        assert "stepfunctions" not in f.read_text(encoding="utf-8"), f.name


def test_build_image_uses_the_moved_dockerfile_and_builds_on_push():
    on = workflow("build-image.yml")[True]
    assert "workflow_dispatch" in on
    assert set(on["push"]["paths"]) == {"authgenforge/**", "aws-sagemaker/**"}
    assert "file: aws-sagemaker/Dockerfile" in workflow_text("build-image.yml")


@pytest.mark.parametrize("wf", ["smoke-test.yml", "run-training.yml"])
def test_smoke_and_run_launch_the_image_directly(wf):
    text = workflow_text(wf)
    assert "python aws-sagemaker/launch.py" in text
    assert '--image-uri "$IMAGE"' in text
    # blank image tag -> most recently pushed image
    assert workflow(wf)[True]["workflow_dispatch"]["inputs"]["image_tag"]["required"] is False
    assert "sort_by(imageDetails,&imagePushedAt)" in text
    assert f"role/{SAGEMAKER_ROLE}" in text


def _commands(wf: str) -> str:
    """The workflow text without comment lines."""
    return "\n".join(l for l in workflow_text(wf).splitlines() if not l.lstrip().startswith("#"))


def test_smoke_waits_and_runs_the_smoke_config():
    text = _commands("smoke-test.yml")
    assert f"--config {SMOKE_CONFIG}" in text
    assert "--no-wait" not in text          # the SDK must block and fail the workflow
    assert "--no-spot" in text


def test_run_training_returns_at_once_and_offers_spot():
    text = _commands("run-training.yml")
    inputs = workflow("run-training.yml")[True]["workflow_dispatch"]["inputs"]
    assert "--no-wait" in text
    assert inputs["no_spot"]["type"] == "boolean" and inputs["no_spot"]["default"] is False


def test_run_training_offers_only_configs_in_the_image():
    for opt in run_training_configs():
        assert (SM / opt).is_file(), opt


# ------------------------------------------------------------------
# Image <-> launcher <-> config
# ------------------------------------------------------------------

def test_image_layout_matches_the_launch_entrypoint():
    dockerfile = (SM / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY aws-sagemaker/ /opt/ml/code/sagemaker/" in dockerfile
    assert "COPY authgenforge/ /opt/ml/code/authgenforge/" in dockerfile
    launch = (SM / "launch.py").read_text(encoding="utf-8")
    assert '"/opt/ml/code/sagemaker/train.py"' in launch
    assert (SM / "train.py").is_file()


def _channel_paths(cfg: dict) -> set[str]:
    paths = []
    for split in ("train", "test"):
        root = cfg["datasets"][split]["dataroot"]
        paths += root if isinstance(root, list) else [root]
    paths.append(cfg["structure"]["backbone"]["model_path"])
    return set(paths)


@pytest.mark.parametrize("cfg", all_configs())
def test_every_config_path_is_a_mounted_channel(cfg):
    """launch.py mounts each sagemaker.inputs entry `x` at /opt/ml/input/data/x."""
    c = config(cfg)
    channels = set(c["sagemaker"]["inputs"])
    wanted = set()
    for path in _channel_paths(c):
        m = re.fullmatch(r"/opt/ml/input/data/([^/]+)/?", path)
        assert m, f"{cfg}: {path} is not a channel mount"
        wanted.add(m.group(1))
    assert wanted == channels


@pytest.mark.parametrize("cfg", all_configs())
def test_checkpoints_go_where_sagemaker_syncs(cfg):
    launch = (SM / "launch.py").read_text(encoding="utf-8")
    assert '"checkpoint_local_path": "/opt/ml/checkpoints"' in launch
    assert config(cfg)["train_settings"]["save_checkpoint_folder_path"] == "/opt/ml/checkpoints"


@pytest.mark.parametrize("cfg", all_configs())
def test_configs_read_our_bucket_in_our_region(cfg):
    sm = config(cfg)["sagemaker"]
    assert sm["region"] == REGION
    for spec in sm["inputs"].values():
        assert spec["uri"].startswith("s3://authenta-data-rnd/image-tampering-detection/"), spec
        assert spec.get("mode") in ("FastFile", "File"), spec


# ------------------------------------------------------------------
# IAM grants cover what the jobs and the workflows touch
# ------------------------------------------------------------------

@pytest.mark.parametrize("path", sorted(INFRA.glob("**/*.json")), ids=lambda p: p.name)
def test_templates_render_to_valid_json(path):
    text = render(path)
    assert "${" not in text, f"undefined placeholder in {path.name}"
    json.loads(text)


def _resources(policy: dict, action: str) -> list[str]:
    out = []
    for st in policy["Statement"]:
        actions = st["Action"] if isinstance(st["Action"], list) else [st["Action"]]
        if action in actions:
            res = st["Resource"] if isinstance(st["Resource"], list) else [st["Resource"]]
            out += res
    return out


def _covered(uri: str, resources: list[str]) -> bool:
    key = uri.removeprefix("s3://")
    return any(key.startswith(r.removeprefix("arn:aws:s3:::").rstrip("*")) for r in resources)


@pytest.mark.parametrize("cfg", all_configs())
def test_sagemaker_role_can_read_inputs_and_write_outputs(cfg):
    policy = json.loads(render(INFRA / "iam" / "sagemaker-policy.json"))
    sm = config(cfg)["sagemaker"]
    for spec in sm["inputs"].values():
        assert _covered(spec["uri"], _resources(policy, "s3:GetObject")), spec["uri"]
    for key in ("checkpoint_prefix", "output_prefix"):
        uri = f"s3://{sm['output_bucket']}/{sm[key]}/job/"
        assert _covered(uri, _resources(policy, "s3:PutObject")), uri


def test_github_role_can_launch_and_follow_jobs():
    gh = json.loads(render(INFRA / "iam" / "github-policy.json"))
    for action in ("sagemaker:CreateTrainingJob", "sagemaker:DescribeTrainingJob", "sagemaker:AddTags",
                   "logs:GetLogEvents", "logs:FilterLogEvents", "ecr:DescribeImages", "ecr:PutImage"):
        assert _resources(gh, action), action
    assert _resources(gh, "iam:PassRole") == [f"arn:aws:iam::{ACCOUNT}:role/{SAGEMAKER_ROLE}"]
    assert any(r.endswith(f"repository/{ECR_REPOSITORY}") for r in _resources(gh, "ecr:PutImage"))


def test_names_agree_across_setup_and_workflows():
    setup = (INFRA / "setup-aws.sh").read_text(encoding="utf-8")
    for role in ("forgery-github-actions-role", SAGEMAKER_ROLE):
        assert f"make_role {role}" in setup
    assert "stepfunctions" not in setup
    assert f"--repository-name {ECR_REPOSITORY}" in setup
    for wf in ("build-image.yml", "smoke-test.yml", "run-training.yml"):
        assert workflow(wf)["env"]["ECR_REPOSITORY"] == ECR_REPOSITORY


def test_workflows_use_one_region():
    regions = {workflow(f.name)["env"]["AWS_REGION"] for f in WORKFLOWS.glob("*.yml") if "AWS_REGION" in workflow(f.name).get("env", {})}
    assert regions == {REGION}
    assert f"AWS_REGION:-{REGION}" in (INFRA / "setup-aws.sh").read_text(encoding="utf-8")


# ------------------------------------------------------------------
# Metrics regexes <-> trainer log format
# ------------------------------------------------------------------

def test_metric_regexes_match_the_trainer_format():
    pytest.importorskip("torch")
    pytest.importorskip("peft")
    pytest.importorskip("streaming")
    from authgenforge.training.trainer import SegmentationTrainer

    class Stub:
        lines: list[str] = []

        def _log(self, msg):
            self.lines.append(msg)

    stub = Stub()
    metrics = dict(loss=0.25, iou=0.5, f1=0.625, precision=0.75, recall=0.5, accuracy=0.875)
    SegmentationTrainer._print_metrics(stub, "Train", 3, metrics)
    SegmentationTrainer._print_metrics(stub, "Val", 3, metrics)
    log = "\n".join(f"2026-10-01 12:00:00 | INFO | forge | {line}" for line in stub.lines)

    expected = {"loss": 0.25, "iou": 0.5, "f1": 0.625, "precision": 0.75, "recall": 0.5, "accuracy": 0.875}
    for m in metric_definitions():
        found = re.findall(m["Regex"], log)
        assert len(found) == 1, m
        assert float(found[0]) == expected[m["Name"].split(":")[1]], m


# ------------------------------------------------------------------
# train.py config patching (spot resume / missing init weights)
# ------------------------------------------------------------------

@pytest.fixture(scope="module")
def train_module():
    spec = importlib.util.spec_from_file_location("sm_train", SM / "train.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_cfg(tmp_path, ckpt_root, want_load=False, init=""):
    cfg = {
        "name": "exp",
        "train_settings": {"save_checkpoint_folder_path": str(ckpt_root), "resume_dataloader": False},
        "pretraining_settings": {"want_load": want_load, "checkpoint_path": init},
    }
    path = tmp_path / "cfg.yml"
    path.write_text(yaml.safe_dump(cfg))
    return path


def test_fresh_run_uses_the_config_unchanged(train_module, tmp_path):
    path = _write_cfg(tmp_path, tmp_path / "ckpt")
    assert train_module._effective_config(path) == path


def test_restored_checkpoint_turns_on_resume(train_module, tmp_path):
    latest = tmp_path / "ckpt" / "exp" / "latest_checkpoint.pth"
    latest.parent.mkdir(parents=True)
    latest.write_bytes(b"x")
    eff = train_module._effective_config(_write_cfg(tmp_path, tmp_path / "ckpt"))
    patched = yaml.safe_load(eff.read_text())
    eff.unlink()
    assert patched["train_settings"]["load_checkpoint_file_path"] == str(latest)
    assert patched["train_settings"]["resume_dataloader"] is True


def test_missing_init_weights_disable_want_load(train_module, tmp_path):
    eff = train_module._effective_config(
        _write_cfg(tmp_path, tmp_path / "ckpt", want_load=True, init=str(tmp_path / "nope.pth")))
    patched = yaml.safe_load(eff.read_text())
    eff.unlink()
    assert patched["pretraining_settings"]["want_load"] is False
