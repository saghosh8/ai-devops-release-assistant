# Deployment Notes

## Docker build step

The `docker build -t app:latest .` step in `deploy.yml` uses the root `Dockerfile`.
As of PR #47, the base image is `node:20-slim`. Engines field in `package-lock.json`
has not yet been updated to match — if `npm ci` starts failing inside the Docker build
with a peer dependency or engine mismatch error, check whether `package-lock.json`
needs to be regenerated against Node 20 before investigating anything else.

## Deploy step

The `kubectl apply -f k8s/deployment.yaml` step deploys to EKS. As of PR #52 this step
has a 3-attempt retry wrapper for transient EKS API throttling errors. If this step
fails after 3 retries, it is very unlikely to be a transient issue — check the EKS
cluster status and IAM permissions instead.
