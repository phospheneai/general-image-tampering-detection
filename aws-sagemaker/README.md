# SageMaker training

Run the forgery-segmentation model as a SageMaker Training job: MDS shards in
from S3, checkpoints out to S3. This `aws-sagemaker/` directory is the whole
addition; nothing under `authgenforge/` or `configs/` changes.

Just want to press the buttons in GitHub? See [aws-infra/README.md](../aws-infra/README.md).
To train on your own GPU instead, see the [main README](../README.md).

## Case 1 — smoke test (do this before trusting a real run)

```bash
pip install "sagemaker>=2.240,<3" pyyaml boto3
export SAGEMAKER_ROLE=arn:aws:iam::200283853008:role/forgery-sagemaker-role

python aws-sagemaker/launch.py --config config/smoke.yml --run-name smoke-1 --end-epoch 1 --max-run-hours 1 --no-spot
```
96 images, 1 epoch: ~10–15 min, under $1.

## Case 2 — full training run

```bash
python aws-sagemaker/launch.py --run-name <name> --end-epoch 1
```
`--dry-run` prints everything and launches nothing. Spot is the default
(`--no-spot` for on-demand); `--no-wait` submits and returns.

## Case 3 — run an image already built by GitHub Actions

```bash
python aws-sagemaker/launch.py --run-name <name> \
    --image-uri 200283853008.dkr.ecr.us-east-1.amazonaws.com/forgery-train:<tag>
```
One image, any `--config`; nothing about the config is baked into the build
(see `.github/workflows/build-image.yml` / `aws-sagemaker/Dockerfile`). This
is what the **Smoke test** and **Run training** workflows do.

---

## One-time setup

- Run `bash aws-infra/setup-aws.sh` with admin credentials. It creates the
  GitHub login (OIDC), the roles `forgery-github-actions-role` and
  `forgery-sagemaker-role`, and the ECR repository `forgery-train`.
- Add the repository secret it prints: **Settings → Secrets and variables →
  Actions**, name `AWS_ROLE_ARN`.
- `ml.g6e.2xlarge` quota ≥ 1 in us-east-1, for both *training job usage*
  (smoke test, on-demand) and *spot training job usage* (Run training):
  [Service Quotas → SageMaker](https://us-east-1.console.aws.amazon.com/servicequotas/home/services/sagemaker/quotas).
- S3 data, one split per prefix (see `sagemaker.inputs` in the config). All of
  it is already uploaded:
  ```
  s3://authenta-data-rnd/image-tampering-detection/
  ├── processed-v1/{train,test}/     the dataset (MDS)
  ├── smoke/{train,test}/            96-image smoke slice              ← python scripts/make_smoke_mds.py --upload
  └── artifacts/dinov3-vitl16/       config.json + model.safetensors   ← bash scripts/download_artifacts.sh, then aws s3 cp
  ```

## How it works, briefly

- Everything (region, bucket, S3 channels, checkpoint path) comes from the
  `sagemaker:` block of whichever `--config` you pick. Nothing is hardcoded in
  `launch.py`.
- `--run-name` is the job name *and* the S3 sub-prefix; it can't be reused
  (prompted if you omit it). The Run training workflow appends a timestamp.
  Checkpoints sync both ways with S3, so a spot interruption resumes
  automatically from the last saved step.
- No `--image-uri` → ships `authgenforge/` + `aws-sagemaker/` fresh on every
  launch via the managed PyTorch container. With `--image-uri` → runs a
  pre-built image, `--config`/`--end-epoch` passed as container arguments.
- The configs are copied into the image: after editing a `.yml` under
  `aws-sagemaker/config/`, rebuild the image before running it.
  `aws-sagemaker/config/` is separate from the repo's `configs/`.
- One epoch of processed-v1 is ~457 k batches; set `--max-run-hours` (or the
  workflow's time limit) to fit the epochs you ask for.
- Single GPU only (`ml.g6e.2xlarge`, 1× L40S 48 GB); the trainer is single-process.

## Outputs

```
checkpoints  s3://authenta-data-rnd/image-tampering-detection/sagemaker/checkpoints/<run-name>/train_forensics_v1/
               train_forensics_v1_best.pth, latest_checkpoint.pth, epoch<N>.pth, metrics.csv,
               <date_time>/predictions/val_epoch_<N>.csv   (per image: ground_truth, probability, predicted_class, iou)
smoke runs   s3://authenta-data-rnd/image-tampering-detection/sagemaker/smoke/checkpoints/<run-name>/
logs/metrics SageMaker console → Training jobs → <run-name>
```

## Testing without AWS

```bash
pytest tests/sagemaker -q                    # launcher / config / IAM / workflow agreement
bash tests/sagemaker/container_test.sh       # needs Docker: builds the image, runs it SageMaker-style, checks resume
```
Both run automatically in the **Pipeline checks** workflow.

Need more (checkpoint layout, init-weights fallback, spot-resume mechanics)?
Read `launch.py`/`train.py` directly; their comments carry the reasoning.
