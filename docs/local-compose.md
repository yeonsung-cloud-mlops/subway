# Docker Compose 로컬 실행

Docker Desktop(또는 Docker Engine + Compose v2 이상)이 실행 중이면 됩니다. 호스트에 Node/Python 패키지 설치는 필요하지 않습니다. 아래 명령은 저장소 루트 기준입니다.

```sh
./scripts/compose.sh up -d --build --wait --wait-timeout 240
./scripts/compose.sh ps
```

- 화면: http://localhost:8080
- API 문서: http://localhost:8080/docs
- 모델 상태: http://localhost:8080/health
- 전체 경로 예측: `POST http://localhost:8080/v1/journeys/predict`

`compose.sh`는 현재처럼 한글/공백이 포함된 경로에서 Docker Desktop BuildKit의 `x-docker-expose-session-sharedkey` 오류를 피하기 위해 `/tmp/subway-compose-<uid>/`에 영문 심볼릭 링크를 만들어 Compose를 실행합니다. 원본 파일은 이동하지 않습니다. 일반 영문 경로에서는 `docker compose`로 동일하게 실행할 수 있습니다. Mac 재부팅 후에는 이 스크립트로 다시 실행해 별칭을 복구하세요.

## 구성

```text
브라우저 → 127.0.0.1:8080 → Nginx
                           ├─ /, /api/metro/* → Next.js:3000
                           │                    └─ FastAPI:8000
                           └─ /v1/*, /health, /docs, /openapi.json → FastAPI:8000
                                                                    └─ SQLite 볼륨
```

Nginx만 호스트 포트를 공개합니다. Next.js의 서버 측 API 프록시는 `METRO_API_URL=http://backend:8000`을 런타임에 사용하므로 브라우저에 내부 주소를 넣거나 CORS를 따로 구성할 필요가 없습니다. Nginx는 Docker DNS로 컨테이너 주소를 재조회합니다. 백엔드와 프론트엔드 상태 확인을 통과한 뒤 프록시를 시작합니다.

Next.js는 standalone 프로덕션 빌드, FastAPI는 단일 worker로 실행합니다. 소스 변경 후에는 위 빌드 명령을 다시 실행하세요. 컨테이너 로그에는 회전 정책을 적용했습니다. API/Next.js는 일반 사용자로 실행하고, DB와 모델은 분리했습니다.

[Compose 시작 순서 공식 문서](https://docs.docker.com/compose/how-tos/startup-order/), [Next.js standalone Docker 배포 안내](https://docs.docker.com/guides/nextjs/)를 참고한 구성입니다.

## 데이터

`subway_sqlite-data`라는 Docker 볼륨이 `/app/var`에 연결됩니다. 처음 시작할 때 저장소에 포함된 시드로 **역 315개, 구간 640개, 혼잡도 원본 관측 610,209개**를 적재합니다. 학습된 모델은 이미지에 포함되어 요청마다 추론하며 컨테이너 시작 시 재학습하지 않습니다.

새 볼륨에는 대용량 승하차 원문과 공식 파일 바이너리가 없습니다. 모두 적재하려면 서비스를 잠시 중지하고 다음 명령을 실행합니다. 출처의 해시가 바뀐 파일은 검토 전까지 가져오지 않습니다.

```sh
./scripts/compose.sh stop backend
./scripts/compose.sh run --rm --no-deps backend python -m scripts.bootstrap --download --db /app/var/subway.sqlite3
./scripts/compose.sh up -d --wait --wait-timeout 240
```

이번 로컬 환경에는 기존 `var/subway.sqlite3`를 SQLite backup API로 스냅샷한 뒤 볼륨에 복사하여 **승하차 원문 597,970행과 원본 21개**도 적재했습니다. 호스트 DB와 컨테이너 DB는 별개이며 이후 자동 동기화하지 않습니다. 런타임 DB, 다운로드 원본, 인증정보는 Git과 이미지 빌드 대상에 포함하지 않습니다.

중지/컨테이너 재생성 시 데이터는 유지됩니다. `down -v`는 볼륨을 지우므로 데이터를 초기화할 때만 사용하세요. 칸별 값은 검증 전 배분 시나리오이며 시간표 기반 이동시간이 아닙니다.

## 검증

```sh
# 컨테이너 내 백엔드 테스트. 서비스 DB와 별개로 실행합니다.
./scripts/compose.sh --profile test run --build --rm tests

# 실제 Nginx/Next.js/FastAPI 경로, 관측 API, 요청 검증까지 확인합니다.
./scripts/compose.sh exec -T backend python -m scripts.smoke_compose --url http://nginx:8080

# 대용량 원본까지 적재된 환경에서만 추가 확인
./scripts/compose.sh exec -T backend python -m scripts.smoke_compose --url http://nginx:8080 --require-originals
```

실행 중인 Compose 환경을 대상으로 기존 프론트엔드 브라우저 테스트도 실행할 수 있습니다(호스트 Node.js 필요). 이 설정은 별도 개발 서버를 띄우지 않습니다.

```sh
npm --prefix frontend ci
(cd frontend && npx playwright install chromium)
frontend/node_modules/.bin/playwright test --config docker/playwright.compose.config.mjs
```

2026-09-21 로컬 검증: 백엔드 42개, 실제 Compose 대상 브라우저 9개 통과. 1~9호선, 환승, 4/6/8/10량, 오류 처리, 320px 화면을 확인했습니다. 원본 조회 포함 통합 검사와 이미지 재빌드/컨테이너 재생성 후 DB 유지도 확인했습니다.

프론트엔드 이미지는 빌드 중 TypeScript 검사와 Next.js 프로덕션 빌드를 수행합니다. 호스트에 Python 3가 있으면 `python3 scripts/smoke_compose.py --require-originals`로 외부 공개 포트도 검증할 수 있습니다.

## 운영 명령과 포트 변경

```sh
./scripts/compose.sh logs -f --tail=100
./scripts/compose.sh stop
./scripts/compose.sh up -d --wait
./scripts/compose.sh down
```

포트 충돌 시 `.env.example`을 `.env`로 복사하고 `HTTP_PORT=8081` 등으로 변경합니다. 기본 주소는 로컬 전용 `127.0.0.1`입니다. 향후 EC2 IP로 공개할 때는 `BIND_ADDRESS=0.0.0.0`, `HTTP_PORT=80` 및 보안 그룹을 별도로 설정합니다.

## 다음 GitHub Actions / EC2 단계

이 Phase는 로컬 실행 환경까지입니다. AWS 배포 워크플로·리소스·자격증명은 아직 구성하지 않았습니다. 다음 단계에서는 다음 순서로 연결합니다.

1. CI에서 백엔드 테스트, 프론트엔드 타입 검사/빌드, Compose 통합 검증 실행.
2. EC2 아키텍처에 맞는 이미지를 Git SHA 태그로 GHCR 또는 ECR에 푸시. 작은 EC2에서 빌드/학습하지 않기.
3. CD에서 `BACKEND_IMAGE`, `FRONTEND_IMAGE`를 검증된 이미지 태그로 지정하고 `compose pull`, `compose up -d --no-build --wait` 수행.
4. SQLite 볼륨 백업 후 배포하고 `/health` 및 여정 예측을 검증. 실패 시 이전 이미지 태그로 복귀. 스키마 변경은 DB 복구 계획까지 별도 검토.

현재 베이스 이미지 태그는 보안 패치를 받을 수 있는 버전 계열 태그입니다. CI/CD 구축 시 검증한 digest를 고정하고 갱신 주기를 관리하세요. 최소 EC2 크기는 배포할 아키텍처와 실제 메모리·동시 요청 측정 후 결정합니다.
