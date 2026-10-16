# Train the model on AWS (GitHub Actions)

Go to the **Actions** tab → pick a workflow → **Run workflow**.

## I just want to train

1. **Run training**
2. Fill in:
   - `run_name`: any name, e.g. `my-run-1`
   - `end_epoch`: how many rounds over the dataset (default `1`)
   - leave `image_tag` empty
3. Done. Results go to
   `s3://authenta-data-rnd/image-tampering-detection/sagemaker/checkpoints/<job>/`.

## I just want to smoke test the pipeline

1. **Smoke test** → Run workflow
2. Leave `image_tag` empty
3. Wait ~10–15 min: it goes ✅ or ❌

## I changed code and pushed — now I want to train with it

1. **Build training image** → wait till it finishes
   (runs by itself on a push to the default branch)
2. **Smoke test** → wait till it goes green
3. **Run training** → same as above

That's the whole thing.

---

First time ever setting this up? See `aws-infra/setup-aws.sh` and [aws-sagemaker/README.md](../aws-sagemaker/README.md).
