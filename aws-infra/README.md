# Train the model on AWS (GitHub Actions)

Go to the **Actions** tab → pick a workflow → **Run workflow**.

## I just want to train

1. **Run training**
2. Fill in:
   - `Run name` — any name, e.g. `my-run-1`
   - `Stop after this epoch` — how many rounds over the dataset
   - leave the image tag empty (= the newest image)
   - leave everything else as it is
3. Done. The summary shows the job name; results go to
   `s3://authenta-data-rnd/image-tampering-detection/sagemaker/checkpoints/<job>/`.

## I just want to smoke test the pipeline

1. **Smoke test** → Run workflow
2. Leave the image tag empty
3. Wait ~10–15 min — goes ✅ or ❌

## I changed code — now I want to train with it

1. **Build training image** → wait till it finishes
   (on the default branch this runs by itself after a push)
2. **Smoke test** → wait till it goes green
3. **Run training** → same as above

That's the whole thing.

---

First time ever setting this up, or something failed? See the step-by-step
guide in [aws-sagemaker/README.md](../aws-sagemaker/README.md) (Part A is the
one-time setup, using `aws-infra/setup-aws.sh`).
