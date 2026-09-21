#!/bin/bash
# Installed by CloudFormation; SSM can only supply a validated immutable image tag.
set -Eeuo pipefail
exec 9>/var/lock/subway-deploy.lock
flock -n 9 || { echo 'Another deployment is running'; exit 1; }
source /etc/subway.conf
COMMIT_SHA=${1:?Git commit SHA required}
[[ $COMMIT_SHA =~ ^[0-9a-f]{40}$ ]] || exit 2
test -f /opt/subway/bootstrap-ready
mountpoint -q /srv/subway
cd /opt/subway
REGISTRY="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
export AWS_DEFAULT_REGION="$AWS_REGION"
export DOCKER_CONFIG
DOCKER_CONFIG=$(mktemp -d)
trap 'rm -rf "$DOCKER_CONFIG"' EXIT
aws ecr get-login-password | docker login --username AWS --password-stdin "$REGISTRY" >/dev/null
cat > next.env <<ENV
BACKEND_IMAGE=$REGISTRY/subway/backend:$COMMIT_SHA
FRONTEND_IMAGE=$REGISTRY/subway/frontend:$COMMIT_SHA
ENV
compose() { docker compose --env-file "$1" -f compose.yaml "${@:2}"; }
compose next.env pull --quiet
PREVIOUS=0
if [ -f current.env ]; then
  cp current.env previous.env
  PREVIOUS=1
fi
DB_EXISTED=0
SNAPSHOT_READY=0
BACKUP="/srv/subway/backups/predeploy-$(date -u +%Y%m%dT%H%M%SZ)-$COMMIT_SHA.sqlite3"
rollback() {
  status=$?
  trap - ERR
  set +e
  echo 'Deployment failed; restoring previous database and images.'
  compose next.env stop backend
  if [ "$SNAPSHOT_READY" = 1 ]; then
    rm -f /srv/subway/data/subway.sqlite3-wal /srv/subway/data/subway.sqlite3-shm
    cp "$BACKUP" /srv/subway/data/subway.sqlite3
    chown 10001:10001 /srv/subway/data/subway.sqlite3
  fi
  if [ "$PREVIOUS" = 1 ]; then
    compose previous.env up -d --no-build --wait --wait-timeout 240
  fi
  exit "$status"
}
trap rollback ERR
if [ -f /srv/subway/data/subway.sqlite3 ]; then
  DB_EXISTED=1
  if [ "$PREVIOUS" = 1 ]; then compose current.env stop backend; fi
  python3 - "$BACKUP" <<'PY'
import sqlite3, sys
source=sqlite3.connect('file:/srv/subway/data/subway.sqlite3?mode=ro', uri=True)
target=sqlite3.connect(sys.argv[1])
source.backup(target)
assert target.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
target.close(); source.close()
PY
  SNAPSHOT_READY=1
  aws s3 cp "$BACKUP" "s3://$BACKUP_BUCKET/backups/$(basename "$BACKUP")" --only-show-errors
fi
# Import official originals only on the initial deployment. The seed is already bundled.
if [ ! -f /srv/subway/originals-ready ]; then
  compose next.env run --rm --no-deps backend python -m scripts.bootstrap --download --db /app/var/subway.sqlite3
  touch /srv/subway/originals-ready
fi
compose next.env up -d --no-build --wait --wait-timeout 240
compose next.env exec -T backend python -m scripts.smoke_compose --url http://nginx:8080 --require-originals
cp next.env current.env
trap - ERR
printf '%s\n' "$COMMIT_SHA" > /srv/subway/deployed-commit
# Keep two local snapshots; S3 retention is 14 days.
python3 - <<'PY'
from pathlib import Path
for old in sorted(Path('/srv/subway/backups').glob('predeploy-*.sqlite3'), reverse=True)[2:]:
    old.unlink()
PY
# Old images remain in ECR for rollback; reclaim only unused local application images.
docker image prune -af --filter until=24h >/dev/null
printf 'DEPLOYMENT_SUCCESS %s\n' "$COMMIT_SHA"
