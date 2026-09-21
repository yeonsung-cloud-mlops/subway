# 한 칸 여유 — 이동 경로 프론트엔드

Next.js App Router + TypeScript + Tailwind CSS. 출발역부터 목적지역까지 여러 역·환승을 지나는 FastAPI 여정 예측에 연결합니다. 수치나 경로 예시를 내장하지 않고 실제 API 응답을 사용합니다.

## 화면 기획

- 검색: 탑승 노선·역 → 도착 노선·목적지역 → 예상시간 우선/환승 최소 → 급행 포함 여부 → 지금 출발/예정 일시.
- 기존 ‘다음 정차역’ 제한을 제거했습니다. 출발·도착 노선을 각각 선택하여 같은 이름의 환승역을 구분합니다. 같은 역은 조회를 막습니다.
- 노선·역 선택지는 API의 구간 데이터에서 파생합니다. 노선도를 프론트에서 수작업으로 정의하지 않습니다. 범위는 서울교통공사 1~8호선 운영구간과 서울 9호선 데이터 보유 구간으로 수도권 전 운영기관을 의미하지 않습니다.
- 경로 결과: 출발·도착, 가정 기반 소요시간, 환승/열차 변경 횟수, 구간별 예측시각·혼잡도. 환승은 별도 행이며 탑승 구간을 선택하면 해당 칸별 상세가 나타납니다.
- 경로 평균은 API의 예측 가능한 구간 탑승시간 가중 평균. 예측 자료 확보 구간 수를 함께 표시하고 누락을 0으로 채우지 않습니다.
- ‘탑승 열차별 칸 평균·최대’에서 환승 전후 열차를 분리한 칸별 집계를 확인합니다.
- cars 배열에 따라 4/6/8/10량 카드 표시. 작은 모바일에서는 두 열로 재배치하여 숫자가 칸 밖으로 넘치지 않게 합니다.
- 지금 출발은 at 생략. 예정 일시는 +09:00 명시. 각 구간의 추론 시각·경로·이동시간은 모델 API가 결정하며 프론트에서 보간하지 않습니다.
- 입력 변경 시 진행 중 요청 취소 및 늦은 응답 무시. 완료된 이전 결과에는 변경 안내를 표시합니다. 자료 없음, 일부 구간 없음, 연결 오류를 분리합니다.
- 칸별 배분은 검증 전 시나리오, 민감도 범위는 신뢰구간이 아님을 유지합니다. 시간 역시 실제 시간표가 아닌 가정 기반으로 표시합니다.
- 색상: 연성대학교 공식 RGB Magenta #EF238E, Blue #50B0D1, Lime #B5DC10, Ink #2D3437. 출처: https://yeonsung.ac.kr/en/845/subview.do

## 개발 실행

Node.js 22 LTS, 저장소 루트에서 전체 노선·여정 API를 먼저 실행합니다.

```sh
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

다른 터미널:

```sh
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

http://127.0.0.1:3000 에서 조회합니다. `METRO_API_URL`은 서버 전용 환경변수이며 기본값은 `http://127.0.0.1:8000`. 브라우저는 같은 출처 `/api/metro/*`를 호출하므로 내부 서버 주소나 CORS 설정을 노출하지 않습니다.

## API 연결

- `/api/metro/segments` → FastAPI `GET /v1/segments`: 호선·역 목록.
- `/api/metro/journey` → FastAPI `POST /v1/journeys/predict`: `{from_station,to_station,from_line,to_line,strategy,allow_express,at?}`.
- 여정 응답의 `steps`는 승차/환승, `legs`는 연속 탑승 열차 단위, `forecast`는 개별 구간 예측입니다. `available_segment_weighted_mean_pct`, `predicted_segments`, `ride_segments`, 경고도 그대로 표시합니다.
- 이전 `/api/metro/predict` → `POST /v1/predict`, `/api/metro/model` → `GET /v1/model` 프록시도 유지합니다.
- 프록시는 고정된 허용 경로만 사용합니다. 요청 크기 8KB, 일반 요청 15초·여정 요청 30초 타임아웃, no-store. 여정 API가 없을 때 프론트에서 임의 경로·수치를 생성하지 않습니다.

## 검증

```sh
npm run build
npm run typecheck
npx playwright install chromium
```

실제 API를 8011 포트에서 실행한 뒤:

```sh
# 저장소 루트, 별도 터미널
SQLITE_PATH=var/frontend-check.sqlite3 .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8011
# frontend
npm test
```

Playwright가 3011 포트에 프론트를 시작합니다. 기본 API는 8011이며 `METRO_API_URL`로 변경 가능합니다. 이미 실행 중인 프론트는 같은 백엔드 설정을 사용해야 합니다. `FRONTEND_TEST_URL`은 사전 실행한 대상 URL을 바꿉니다.

실제 API를 이용한 1~9호선 조회, 건대입구→고속터미널 여러 구간, 사당→고속터미널 환승, 성수지선 4량, 9호선 6량, 경로 선택 조건, 동일 역 차단, 미관측 구간, 오류·요청 취소, 320px 화면과 카드 넘침을 검사합니다.

## 운영 실행 준비

```sh
cd frontend
npm ci
npm run build
PORT=3000 METRO_API_URL=http://127.0.0.1:8000 npm start
```

빌드 후 standalone 서버에 정적 파일을 복사합니다. `npm start`는 standalone 서버를 사용하며 기본 바인딩은 0.0.0.0. 로컬만 노출하려면 `FRONTEND_HOST=127.0.0.1`을 설정하세요. `.env.local`은 개발용이며 운영에서는 환경변수를 직접 전달합니다.

동일 EC2에서 FastAPI를 localhost로 유지하고 프론트 포트만 외부에 노출하면 `http://EC2_IP:3000`으로 접근할 수 있습니다. 이 Phase에서는 AWS 자원 생성·방화벽 변경·서비스 등록을 하지 않았습니다. 비밀정보, SQLite, 원본 데이터, node_modules, 빌드·브라우저 검사 산출물은 커밋하지 않습니다.
