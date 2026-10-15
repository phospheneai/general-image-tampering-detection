# Train on AWS SageMaker

This guide trains the image-tampering model on a rented AWS graphics card
(GPU) instead of your own computer. You click a button in GitHub; AWS starts a
GPU machine, trains the model on the dataset stored in AWS, saves the results,
and switches the machine off.

There are three buttons (GitHub "workflows"): **Build training image**,
**Smoke test** and **Run training**. Already set up and just want to train?
See the one-page [aws-infra/README.md](../aws-infra/README.md).

To train on your own computer instead, see the [main README](../README.md).

Follow the steps in order. **Part A is done once per AWS account.** After
that, a training run is only Part B.

**What you need before you start**

- Admin access to the AWS account `200283853008` (an access key and secret
  key). Ask your team lead.
- Admin access to this GitHub repository (to add a secret and run workflows).
- A computer with a terminal (Ubuntu, or macOS).
- The pipeline files must be on the repository's **default branch**
  (`general-image-forgery-datasets`). GitHub only shows the "Run workflow"
  button for workflows that exist there. If the Actions tab does not list the
  three workflows named in this guide, the `sagemaker-pipeline` branch has not
  been merged yet — ask for that first.

Everything runs in the AWS region **us-east-1** (N. Virginia), because that is
where the dataset is stored.

---

# Part A — One-time setup

## Step 1 — Install the AWS command-line tool and sign in

Check whether it is already installed:

```bash
aws --version
```

If that prints a version, skip the install block. Otherwise (Ubuntu):

```bash
sudo apt-get update && sudo apt-get install -y unzip curl
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip -q awscliv2.zip
sudo ./aws/install
rm -rf aws awscliv2.zip
```

Sign in:

```bash
aws configure
```

| Question | What to type |
|---|---|
| AWS Access Key ID | your access key |
| AWS Secret Access Key | your secret key |
| Default region name | `us-east-1` |
| Default output format | `json` |

Check it:

```bash
aws sts get-caller-identity
```

You should see a few lines that include `"Account": "200283853008"`.

## Step 2 — Download the code

```bash
cd ~
git clone https://github.com/phospheneai/general-image-tampering-detection.git
cd general-image-tampering-detection
```

Every command in this guide is run from inside this folder.

## Step 3 — Check that the account is allowed to rent the GPU

1. Open <https://us-east-1.console.aws.amazon.com/servicequotas/home/services/sagemaker/quotas>
   and sign in.
2. In the search box type `ml.g6e.2xlarge for`. Two lines matter:
   - `ml.g6e.2xlarge for training job usage` — used by the Smoke test
   - `ml.g6e.2xlarge for spot training job usage` — used by Run training,
     which runs on cheaper *spot* machines by default
3. For each of the two, look at the column **Applied account-level quota
   value**.

Both must be `1` or more. If one is `0`: click its name, click **Request
increase at account level**, enter `1`, and submit. AWS usually answers within
a day. You can continue with Steps 4 to 6 while you wait, but the test in
Step 8 (or the real run in Step 9) fails until the quota is approved.

## Step 4 — Create the AWS resources

```bash
bash aws-infra/setup-aws.sh
```

This creates the permissions and the image storage the pipeline needs. It is
safe to run more than once. It ends with a box that starts with `Done.` and
shows a line like:

```
Value: arn:aws:iam::200283853008:role/forgery-github-actions-role
```

Copy that value. You need it in the next step.

## Step 5 — Give GitHub permission to use AWS

1. Open the repository on GitHub.
2. Click **Settings** → **Secrets and variables** → **Actions**.
3. Click **New repository secret**.
4. Fill in:
   - **Name:** `AWS_ROLE_ARN`
   - **Secret:** the value you copied in Step 4
5. Click **Add secret**.

This is the only secret. No AWS keys are stored in GitHub.

## Step 6 — Check that the data is in AWS

The pipeline needs two things in storage besides the dataset: the starting
model and a small test dataset. Check whether they are there:

```bash
aws s3 ls s3://authenta-data-rnd/image-tampering-detection/artifacts/dinov3-vitl16/
aws s3 ls s3://authenta-data-rnd/image-tampering-detection/smoke/train/
aws s3 ls s3://authenta-data-rnd/image-tampering-detection/smoke/test/
```

- The first command should list `config.json` and `model.safetensors`.
- The second and third should each list `index.json` and a `shard.00000.mds`.

If all three look like that, go to Step 7. If something is missing, see
[Uploading the starting model and test data](#uploading-the-starting-model-and-test-data).

---

# Part B — Train

All three actions below are buttons in GitHub. To find them: open the
repository on GitHub and click the **Actions** tab. The workflows are listed
on the left.

To run one: click its name on the left, then click **Run workflow** on the
right. A small form opens. In **Use workflow from**, choose the branch that
has the code you want to train (normally the default branch). Fill in the
form as described in each step, then click the green **Run workflow** button.

A new line appears in the list after a few seconds. Click it to watch. A
yellow dot means running, a green tick means it worked, a red cross means it
failed.

## Step 7 — Build the training image

The *image* is a package containing the training code and everything it needs.

1. Run the workflow **Build training image**. Leave the box "Extra tag to
   push" empty.
2. Wait for the green tick. This takes about 15 to 20 minutes.

That's all. The next two steps use the newest image automatically when you
leave their image tag box empty.

**You rarely need to click this yourself.** Once the code is on the default
branch, this workflow runs by itself every time someone pushes a change to
the training code (`authgenforge/` or `aws-sagemaker/`). Run it by hand only
for the first build, or to build code from another branch.

## Step 8 — Run the test

This trains on 96 images for one round on the real AWS GPU. It proves that
everything works before you pay for a long run. It takes about 10 to 15
minutes and costs well under one US dollar.

1. Run the workflow **Smoke test**. Leave the box "ECR tag to test" empty.
2. Wait for it to finish. The workflow stays yellow while the job runs and
   shows the training log as it goes.

- **Green tick:** everything works. Go to Step 9.
- **Red cross:** click the run and scroll to the summary. It shows the reason
  and the last lines of the training log. Look the message up in
  [If something goes wrong](#if-something-goes-wrong).

**Do not start a real run until this test is green.**

## Step 9 — Start the real training

1. Run the workflow **Run training**.
2. Fill in the form:

   | Box (its label starts with…) | What to type |
   |---|---|
   | "Run name" | a short name for this run, letters, numbers and dashes only, for example `first-run` |
   | "ECR tag to run" | leave empty (uses the newest image) |
   | "Training config inside the image" | leave as `config/train_forensics.yml` |
   | "Stop after this epoch" | how many rounds over the dataset to train. `1` is the default |
   | "Hard time limit for the training itself" | the job is stopped after this many hours of training. `72` is the default |
   | "On-demand instead of spot" | leave unticked (see below) |

3. Click **Run workflow**.

This workflow finishes in under a minute: it only *starts* the training. The
training itself runs in AWS for hours or days.

4. Click the finished run and scroll to the summary. It shows a table. **Copy
   the value in the `job` row** (for example `first-run-20261006-101500`).
   That is the name of your training job, and you need it to find the
   results.

**Spot or on-demand.** By default the job runs on a *spot* machine: spare AWS
capacity, much cheaper, but AWS can take it back at any time. When that
happens the job waits for a new machine and continues from its last saved
checkpoint by itself; you do not need to do anything. Tick "On-demand instead
of spot" if the run must not be interrupted.

One round over the full dataset is about 457,000 batches. If the time limit is
reached first, the job is stopped; what was saved up to then is kept.

## Step 10 — Watch the training

1. Open <https://us-east-1.console.aws.amazon.com/sagemaker/home?region=us-east-1#/jobs>.
2. Click your job name.

- **Status** shows `InProgress`, then `Completed` (or `Failed`).
- The **Monitor** section has a **View logs** link that shows what the
  training prints.
- The **Metrics** section shows graphs of loss, IoU, F1, precision, recall and
  accuracy. They get a new point at the end of each round.

To stop a run early, click **Stop** at the top of the job page. What was saved
so far is kept.

## Step 11 — Get the results

Results are saved in AWS storage while the job runs. To download them to your
computer, replace `<job>` with the job name from Step 9:

```bash
aws s3 sync \
  s3://authenta-data-rnd/image-tampering-detection/sagemaker/checkpoints/<job>/ \
  ./results/<job>/
```

You get:

```
results/<job>/train_forensics_v1/
├── train_forensics_v1_best.pth     the best model so far  ← the one to use
├── latest_checkpoint.pth           the most recent state
├── epoch1.pth, epoch2.pth, …       the model at the end of each round
├── metrics.csv                     one row per round: loss, IoU, F1, precision, recall, accuracy
└── <date_time>/
    ├── logs/log.txt                everything that was printed
    └── predictions/val_epoch_<N>.csv   one row per test image
```

The per-image file has these columns:

| Column | Meaning |
|---|---|
| `image_name` | which image |
| `ground_truth` | the correct answer: `0` = not edited, `1` = edited |
| `probability` | how sure the model is that the image was edited (0 to 1) |
| `predicted_class` | the model's answer: `0` = not edited, `1` = edited |
| `iou` | how well the predicted edited area overlaps the real one (0 to 1; higher is better) |

The model files are about 1.3 GB each. To download only the small files:

```bash
aws s3 sync \
  s3://authenta-data-rnd/image-tampering-detection/sagemaker/checkpoints/<job>/ \
  ./results/<job>/ --exclude "*.pth"
```

---

# If something goes wrong

| Where it fails | What it usually means | What to do |
|---|---|---|
| Any workflow, at "Configure AWS credentials" | The `AWS_ROLE_ARN` secret is wrong or missing | Redo Step 5. Check the value has no spaces before or after it. |
| The three workflows are not in the Actions tab | The pipeline files are not on the default branch | Merge the `sagemaker-pipeline` branch, then reload the page. |
| Build training image, at a line with `763104351884` | The base image could not be downloaded | Run the workflow again. |
| Smoke test or Run training: `no images in forgery-train` | No image has been built yet | Step 7. |
| Smoke test or Run training: an error from `describe-images` | The image tag you typed does not exist | Leave the box empty, or copy the tag exactly from a Build training image summary. |
| Smoke test: `missing …/smoke/…` or `missing …/artifacts/…` | The test data or starting model is not in AWS | See [Uploading the starting model and test data](#uploading-the-starting-model-and-test-data). |
| `AccessDenied` … `iam:PassRole` or `sagemaker:CreateTrainingJob` | The AWS setup is incomplete | Run Step 4 again. |
| Job fails with `ResourceLimitExceeded` | The account is not allowed to rent the GPU yet | Step 3. For spot runs the quota is called `ml.g6e.2xlarge for spot training job usage`. |
| Job fails with `AccessDenied` on S3 | The training job cannot read the data | Run Step 4 again. If the bucket is encrypted with its own key, an admin must add that key to `aws-infra/iam/sagemaker-policy.json`. |
| Job fails with `config not found` | The image is older than the code | Redo Step 7, then run again with the image tag empty. |
| Job fails with `failed to open MDS dataset` | A data folder in AWS is empty | Check the three commands in Step 6. |
| Job fails with a Python traceback | A bug in the training code | The Smoke test summary shows the last log lines; the full log is under **View logs** in Step 10. |

# What to rerun after a change

| You changed | Build image (7) | Smoke test (8) | Run training (9) |
|---|:-:|:-:|:-:|
| Nothing — just train again | | | ✓ |
| Run name, rounds, time limit or spot | | | ✓ |
| Training code (`authgenforge/`, `aws-sagemaker/train.py`) | ✓ (automatic on the default branch) | ✓ | ✓ |
| A setting in `aws-sagemaker/config/*.yml` | ✓ (automatic on the default branch) | ✓ | ✓ |
| `aws-sagemaker/requirements.txt` or `aws-sagemaker/Dockerfile` | ✓ (automatic on the default branch) | ✓ | ✓ |
| A dataset location (`sagemaker:` block of a config) | ✓ (automatic on the default branch) | ✓ | ✓ |

**The settings files are packed into the image.** Editing a `.yml` file has no
effect until a new image is built (Step 7).

# Uploading the starting model and test data

Needed only if Step 6 showed something missing.

**The starting model** (DINOv3 ViT-L/16). It is published on Hugging Face and
needs an account that has accepted its licence:

```bash
pip install -U "huggingface_hub[cli]"
hf auth login
bash scripts/download_artifacts.sh
aws s3 cp --recursive artifacts/mirror/dinov3-vitl16/ \
    s3://authenta-data-rnd/image-tampering-detection/artifacts/dinov3-vitl16/ \
    --exclude '*' --include config.json --include model.safetensors
```

**The test data** (64 training and 32 test images taken from the real
dataset; downloads about 1 GB first):

```bash
bash scripts/install_deps.sh
python scripts/make_smoke_mds.py --upload
```

---

# Reference

Everything below is background for people changing the pipeline. You do not
need it to train.

## How it fits together

```
 GitHub Actions                                     AWS (us-east-1)
 ──────────────                                     ───────────────
 Build training image ──docker push────────────►   ECR  forgery-train:<sha>
 (by hand, or on push to the default branch)

 Smoke test / Run training
   python aws-sagemaker/launch.py --image-uri <image> --config <yml>
         └── SageMaker CreateTrainingJob ──────►   SageMaker
                                                     1. starts a GPU instance (ml.g6e.2xlarge, 1× L40S 48 GB)
                                                     2. pulls the image from ECR
                                                     3. mounts S3 → /opt/ml/input/data/{train,test,artifacts}/
                                                     4. runs  python /opt/ml/code/sagemaker/train.py --config <yml> --end-epoch N
                                                     5. syncs /opt/ml/checkpoints/ ↔ S3

 Pipeline checks (every push/PR, no AWS): agreement tests + the real image
 built on a CPU base and run SageMaker-style.
```

The workflows run `launch.py` on the GitHub runner; it creates the training
job directly through the SageMaker Python SDK. Everything about the job (S3
channels, checkpoint and output folders, region) comes from the `sagemaker:`
block of the chosen config, so one image serves any config. The dataset is
mounted, not copied: the training code reads it as ordinary local files.

## Terms

| Term | Meaning |
|---|---|
| **ECR** | AWS's Docker registry. Stores the training image. |
| **Image tag** | Version label of an image. Every build is tagged with its git commit SHA (plus `latest` when built from the default branch). A blank tag in Smoke test / Run training means the most recently pushed image. |
| **Channel** | One S3 prefix given to the job. Channel `train` appears in the container at `/opt/ml/input/data/train/`. |
| **FastFile** | Channel mode that mounts the S3 prefix and fetches objects when they are read — no upfront copy of the 1.1 TB train split. |
| **Spot** | Spare AWS capacity at a lower price; the job can be interrupted and resumes from its last checkpoint. |
| **MDS** | The dataset's file format (`index.json` + `shard.*.mds`), read in place from the mount. |
| **OIDC** | Lets GitHub log into AWS with a short-lived token instead of stored access keys. |

## Files

| File | What it is |
|---|---|
| `aws-sagemaker/launch.py` | Creates the training job. Used by the Smoke test and Run training workflows (`--image-uri`) and for laptop runs. |
| `aws-sagemaker/train.py` | Training entry point inside the job (`--config`, `--end-epoch`). Detects a restored checkpoint and resumes. |
| `aws-sagemaker/config/train_forensics.yml` | Real training settings: hyperparameters, `/opt/ml/...` paths, and the `sagemaker:` block (S3 channels and output folders) |
| `aws-sagemaker/config/smoke.yml` | Tiny settings: smoke slice, 1 epoch, batch 2 |
| `aws-sagemaker/backbone/dinov3-vitl16/config.json` | DINOv3 ViT-L/16 config (the weights come from S3) |
| `aws-sagemaker/requirements.txt` | Python packages installed into the image |
| `aws-sagemaker/Dockerfile` | The image: AWS PyTorch 2.3 container + `authgenforge/` + `aws-sagemaker/` |
| `.dockerignore` | Keeps weights, data and unrelated folders out of the image |
| `aws-infra/setup-aws.sh` | One-time AWS setup (GitHub login, two roles, ECR) |
| `aws-infra/iam/*.json` | The two roles' trust and permission policies |
| `aws-infra/render.sh` | Fills `${AWS_ACCOUNT_ID}` / `${AWS_REGION}` into a policy template |
| `aws-infra/README.md` | One-page "I just want to train" guide |
| `scripts/make_smoke_mds.py` | Builds and uploads the smoke slice of the dataset |
| `tests/sagemaker/` | Agreement tests, SageMaker-style container test, local emulator |
| `.github/workflows/build-image.yml` | **Build training image** |
| `.github/workflows/smoke-test.yml` | **Smoke test** |
| `.github/workflows/run-training.yml` | **Run training** |
| `.github/workflows/pipeline-checks.yml` | **Pipeline checks** — automatic on every push, no AWS |

`aws-sagemaker/config/` is a SageMaker-specific copy of the repo's `configs/` —
hyperparameter changes there do **not** propagate here.

Inside the image the folder is called `sagemaker/`, so every relative path in
the configs works the same as in the repo:

```
/opt/ml/code/
├── authgenforge/
└── sagemaker/   (= aws-sagemaker/)  train.py  config/  backbone/  requirements.txt
```

## What Step 4 creates

| # | What | Why |
|---|---|---|
| 1 | GitHub OIDC provider | Actions logs in without access keys |
| 2 | Role `forgery-github-actions-role` | Actions: push to ECR, create training jobs, follow their logs |
| 3 | Role `forgery-sagemaker-role` | The job: pull the image, read the data, write `sagemaker/*` |
| 4 | ECR repository `forgery-train` | Stores the image |

```
GitHub ──OIDC──► forgery-github-actions-role   push to ECR, create training jobs (launch.py)
                        │ passes
SageMaker job ──► forgery-sagemaker-role       pull image, read data, write checkpoints
```

A repository secret `SAGEMAKER_ROLE_ARN` overrides the role the jobs run as;
without it they use `forgery-sagemaker-role`.

## S3 layout

```
s3://authenta-data-rnd/image-tampering-detection/
├── processed-v1/{train,test}/        the dataset (MDS)                 channel train / test
├── smoke/{train,test}/               smoke slice (MDS)                 smoke channels
├── artifacts/dinov3-vitl16/          config.json + model.safetensors   channel artifacts
└── sagemaker/                        everything the jobs write
    ├── checkpoints/<job>/<experiment>/   .pth files, metrics.csv, logs, predictions
    ├── output/<job>/
    └── smoke/{checkpoints,output}/<job>/
```

The SageMaker role can read `image-tampering-detection/*` but write only
`image-tampering-detection/sagemaker/*` — a job can never overwrite the dataset.

## Container contract

| Path in the container | From | Config key |
|---|---|---|
| `/opt/ml/input/data/train/` | `…/processed-v1/train/` (FastFile mount) | `datasets.train.dataroot` |
| `/opt/ml/input/data/test/` | `…/processed-v1/test/` (FastFile mount) | `datasets.test.dataroot` |
| `/opt/ml/input/data/artifacts/` | `…/artifacts/dinov3-vitl16/` (File) | `structure.backbone.model_path` |
| `/opt/ml/checkpoints/` | synced both ways with `…/sagemaker/checkpoints/<job>/` | `train_settings.save_checkpoint_folder_path` |
| `/opt/ml/output/failure` | written by `train.py` on a crash → the job's FailureReason | |

Channel names (`sagemaker.inputs`) and `dataroot`s must match;
`pytest tests/sagemaker` fails if they drift.

## How train.py behaves

- **Restart / spot resume** — if `<save_checkpoint_folder_path>/<name>/latest_checkpoint.pth`
  exists at startup (SageMaker restored it from S3), the effective config gets
  `load_checkpoint_file_path` = that file and `resume_dataloader: true`, and
  training continues from the saved epoch and step.
- **Init weights** — `pretraining_settings.want_load: true` with a
  `checkpoint_path` that isn't there is downgraded to `want_load: false`
  (backbone-only start) instead of failing.
- **Provenance** — logs `git_sha` (baked into the image) and the image URI.
- **Metrics** — the trainer prints `[Train|Val] Epoch N | loss … | IoU … | F1 … | precision … | recall … | accuracy …`;
  the patterns that scrape them are `METRIC_DEFS` in `launch.py`.
- Extra arguments SageMaker may append are ignored (`parse_known_args`).

## Test job vs real job — same image, different job

| | Smoke test | Run training |
|---|---|---|
| `--config` | `config/smoke.yml` (fixed) | chosen in the form |
| Data | `smoke/{train,test}` (96 samples) | `processed-v1/{train,test}` (1.83 M / 27.6 k samples) |
| Backbone | `artifacts/dinov3-vitl16` | same |
| Machine | on-demand | spot by default |
| Time limit / disk | 1 h / 50 GB | form input (default 72 h) / 200 GB |
| Output | `…/sagemaker/smoke/…` | `…/sagemaker/…` |
| Workflow | waits for the result | starts the job and returns |

One epoch of processed-v1 is about 457 k batches at batch 4 (about 57 k
optimizer steps with grad-accum 8). Size the time limit for the epochs you
ask for, or the job is stopped mid-run. The last `latest_checkpoint.pth` is
then in S3; start a new run from it via `pretraining_settings.checkpoint_path`.

The run name becomes the job name and the S3 folder; the workflow appends a
UTC timestamp because job names can't be reused.

## Where to make changes

| I want to… | Edit | Then |
|---|---|---|
| change a hyperparameter | `aws-sagemaker/config/train_forensics.yml` | Build → Smoke → Run |
| change training code | `authgenforge/…` | Build → Smoke → Run |
| add a Python package | `aws-sagemaker/requirements.txt` | Build → Smoke → Run |
| point at a new dataset | `sagemaker.inputs` in the yml (and the matching `dataroot`) | Build → Smoke → Run |
| change instance / disk | `--instance-type` / `--volume-size` in `run-training.yml` (and `smoke-test.yml`) | Run |
| add a second training config | new yml under `aws-sagemaker/config/`, add it to `options:` in `run-training.yml` | Build → Run |

The **Pipeline checks** workflow fails if these drift apart: a channel without
a matching `dataroot`, an S3 path the SageMaker role can't read or write, a
metric pattern that no longer matches the trainer's log line, a Run training
config that isn't in the image, or mismatched role or repository names.

## Testing without AWS

```bash
pytest tests/sagemaker -q                         # agreement tests, seconds
bash tests/sagemaker/container_test.sh            # needs Docker; several minutes on CPU
python tests/sagemaker/emulate_training_job.py prepare --root /tmp/smjob
python tests/sagemaker/emulate_training_job.py local   --root /tmp/smjob   # no Docker
```

`container_test.sh` builds `aws-sagemaker/Dockerfile` on a CPU stand-in for
the AWS base image, then runs the image with the same entrypoint and
arguments `launch.py --image-uri` gives the job — baked-in `smoke.yml`,
channels mounted read-only — on synthetic MDS data and a random-init
backbone. It checks the exit code, the checkpoints, the two result CSVs, that
every metric pattern matches the log, and that a second launch resumes from
the first one's checkpoint. On a machine without a usable GPU, add
`--crop-size 224` to the `local` command to keep it quick.

## Manual launcher (without GitHub)

For one-off runs from a laptop with AWS credentials. Same `launch.py`, same
configs.

```bash
pip install "sagemaker>=2.240,<3" pyyaml boto3
export SAGEMAKER_ROLE=arn:aws:iam::200283853008:role/forgery-sagemaker-role

python aws-sagemaker/launch.py --dry-run --run-name test-run      # print the plan, submit nothing
python aws-sagemaker/launch.py --run-name <name>                  # spot by default
python aws-sagemaker/launch.py --run-name <name> --no-spot --no-wait
python aws-sagemaker/launch.py --run-name <name> \
    --image-uri 200283853008.dkr.ecr.us-east-1.amazonaws.com/forgery-train:<tag>   # an image built by the workflow
python aws-sagemaker/launch.py --config config/smoke.yml --run-name smoke-1 --max-run-hours 1   # smoke slice, 1 epoch
```

Without `--image-uri`, the estimator ships `aws-sagemaker/` as `source_dir`
(→ `/opt/ml/code/`) on the managed PyTorch container and `authgenforge/` as a
dependency; `train.py` handles both that layout and the image's. Run names
are job names and S3 sub-prefixes and cannot be reused.
