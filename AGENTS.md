# Project agreements

- End each completed work Phase with relevant tests, a commit, and a push to origin (user authorized).
- Current remote: https://github.com/yeonsung-cloud-mlops/subway.git.
- Never commit credentials, SQLite runtime databases, virtualenvs, or large raw datasets.
- Future production stack: smallest practical EC2, SQLite (no RDS), FastAPI, Next.js, Tailwind CSS, Yeonsung University official logo palette, access by IP until a domain exists.
- Never describe the location-based car allocation as validated car-level prediction. Preserve the model's evidence and scenario labels until genuine car observations are available.
- Unrelated energy/electricity review folders in this shared workspace are outside this repository's task scope.

- Primary prediction API is /v1/journeys/predict: full origin-to-destination route with transfers and time-progressed forecasts. /v1/predict remains a lower-level next-stop endpoint.
- Serve station details and original observations from SQLite; compute predictions per request. Coverage is Seoul Metro 1–8 operating sections plus all of Seoul Line 9 (local/express), not all suburban operators.
