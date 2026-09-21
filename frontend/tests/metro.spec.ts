import { test, expect, type Page } from "@playwright/test";
import type { Journey } from "../src/lib/journey";
import { lowerCrowdingCars, crowdColor, legDoors } from "../src/lib/boarding";
async function ready(page: Page) {
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "이동 구간 혼잡도 조회", exact: true }),
  ).toBeEnabled();
}
async function schedule(page: Page, time = "2026-09-22T08:15") {
  await page.getByRole("button", { name: "일시 선택", exact: true }).click();
  await page.getByLabel("날짜와 시간", { exact: true }).fill(time);
}
async function search(page: Page) {
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/metro/journey") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "이동 구간 혼잡도 조회", exact: true })
    .click();
  return response;
}
async function route(
  page: Page,
  line: number,
  origin: string,
  toLine: number,
  dest: string,
) {
  await page
    .getByRole("button", { name: new RegExp(`^${line} ${line}호선$`) })
    .click();
  await page
    .getByLabel("탑승역", { exact: true })
    .selectOption({ label: origin });
  await page
    .getByLabel("도착 노선", { exact: true })
    .selectOption(String(toLine));
  await page
    .getByLabel("목적지역", { exact: true })
    .selectOption({ label: dest });
}
test("Konkuk to Express Bus Terminal predicts all intervening segments and selects details", async ({
  page,
}) => {
  await ready(page);
  await schedule(page);
  const r = await search(page);
  expect(r.status()).toBe(200);
  const j = await r.json();
  expect(j.ride_segments).toBeGreaterThan(1);
  expect(r.request().postDataJSON()).toMatchObject({
    from_station: "건대입구",
    to_station: "고속터미널",
    from_line: 7,
    to_line: 7,
    at: "2026-09-22T08:15:00+09:00",
  });
  await expect(page.locator(".map-segment")).toHaveCount(j.ride_segments);
  const ride = j.steps
    .filter((s: { kind: string }) => s.kind === "ride")
    .at(-1);
  await page.locator(".map-segment").last().click();
  await expect(page.locator(".map-crowding-value").last()).toContainText(
    ride.forecast.train_mean_congestion_pct.toFixed(1),
  );
  await expect(page.locator(".map-readout")).toHaveCount(0);
  await expect(page.locator(".train-car")).toHaveCount(8);
});
test("all nine lines call real API and render returned car count", async ({
  page,
  request,
}) => {
  const data = await (await request.get("/api/metro/segments")).json();
  await ready(page);
  await schedule(page);
  for (let line = 1; line <= 9; line++) {
    const s = data.segments.find(
      (s: { line: number; service: string }) =>
        s.line === line && s.service === "일반",
    );
    await route(page, line, s.from_station, line, s.to_station);
    const r = await search(page);
    expect(r.status()).toBe(200);
    const j = await r.json();
    const first = j.steps.find((s: { kind: string }) => s.kind === "ride");
    await expect(page.locator(".train-car")).toHaveCount(
      first.forecast.cars.length,
    );
  }
});
test("transfer journey displays transfer steps separately", async ({
  page,
}) => {
  await ready(page);
  await schedule(page);
  await route(page, 2, "사당", 3, "고속터미널");
  const r = await search(page);
  expect(r.status()).toBe(200);
  const j = await r.json();
  expect(j.transfer_count).toBeGreaterThan(0);
  await expect(page.locator(".map-transfer")).toHaveCount(
    j.steps.filter((s: { kind: string }) => s.kind === "transfer").length,
  );
});
test("branch has four cars and changed inputs label previous result", async ({
  page,
}) => {
  await ready(page);
  await schedule(page);
  await route(page, 2, "성수", 2, "신설동");
  expect((await search(page)).status()).toBe(200);
  await expect(page.locator(".train-car")).toHaveCount(4);
  await page.getByRole("button", { name: /^8 8호선$/ }).click();
  await expect(page.locator("main").getByRole("status")).toContainText(
    "이전 조회 결과",
  );
});
test("9 express route preference and same-station validation", async ({
  page,
}) => {
  await ready(page);
  await schedule(page);
  await route(page, 9, "김포공항", 9, "여의도");
  await page.getByRole("button", { name: "환승 최소", exact: true }).click();
  const r = await search(page);
  expect(r.status()).toBe(200);
  expect(r.request().postDataJSON()).toMatchObject({
    strategy: "fewest_transfers",
    allow_express: true,
  });
  await expect(page.locator(".train-car")).toHaveCount(6);
  await page
    .getByLabel("목적지역", { exact: true })
    .selectOption({ label: "김포공항" });
  await expect(
    page.getByRole("button", { name: "이동 구간 혼잡도 조회", exact: true }),
  ).toBeDisabled();
});
test("unavailable journey never manufactures zero congestion", async ({
  page,
  request,
}) => {
  const j: Journey = await (
    await request.post("/api/metro/journey", {
      data: {
        from_station: "건대입구",
        to_station: "고속터미널",
        from_line: 7,
        to_line: 7,
        at: "2026-09-22T08:15:00+09:00",
      },
    })
  ).json();
  j.status = "unavailable";
  j.predicted_segments = 0;
  j.available_segment_weighted_mean_pct = null;
  for (const l of j.legs) {
    l.cars = [];
    l.predicted_segments = 0;
    l.coverage = 0;
  }
  for (const step of j.steps)
    if (step.kind === "ride") {
      step.forecast = null;
      step.status = "unavailable";
      step.unavailable_reason = "테스트: 관측 자료 없음";
    }
  await ready(page);
  await page.route("**/api/metro/journey", (r) => r.fulfill({ json: j }));
  await search(page);
  await expect(page.locator(".boarding-advice")).toContainText(
    "추천 자료가 없습니다",
  );
  await expect(page.locator(".train-car").first()).toContainText("—");
});
test("now omits at and failed server remains retryable", async ({ page }) => {
  await ready(page);
  await page.route("**/api/metro/journey", (r) =>
    r.fulfill({
      status: 502,
      json: { detail: "예측 서버에 연결하지 못했습니다." },
    }),
  );
  const r = await search(page);
  expect(r.request().postDataJSON()).not.toHaveProperty("at");
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "연결하지 못했습니다",
  );
  await expect(
    page.getByRole("button", { name: "이동 구간 혼잡도 조회", exact: true }),
  ).toBeEnabled();
});
test("320px mobile has no page or car-value overflow", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 850 });
  await ready(page);
  await schedule(page);
  await search(page);
  await expect(page.locator(".train-car")).toHaveCount(8);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  expect(
    await page
      .locator(".car")
      .evaluateAll((els) => els.every((e) => e.scrollWidth <= e.clientWidth)),
  ).toBeTruthy();
  await page.screenshot({ path: "test-results/mobile.png", fullPage: true });
});
test("late response is ignored after route change", async ({ page }) => {
  await ready(page);
  await page.route("**/api/metro/journey", async (r) => {
    await new Promise((resolve) => setTimeout(resolve, 500));
    await r
      .fulfill({ status: 502, json: { detail: "오래된 요청 오류" } })
      .catch(() => {});
  });
  await page
    .getByRole("button", { name: "이동 구간 혼잡도 조회", exact: true })
    .click();
  await page.getByRole("button", { name: /^1 1호선$/ }).click();
  await page.waitForTimeout(650);
  await expect(page.locator("main").getByRole("alert")).toHaveCount(0);
});

test("connected train recommends journey average, highlights known door, and does not promise seats", async ({
  page,
  request,
}) => {
  const j: Journey = await (
    await request.post("/api/metro/journey", {
      data: {
        from_station: "건대입구",
        to_station: "고속터미널",
        from_line: 7,
        to_line: 7,
        at: "2026-09-22T08:15:00+09:00",
      },
    })
  ).json();
  j.legs[0].cars = j.legs[0].cars.map((c) => ({
    ...c,
    estimated_mean_congestion_pct: c.car === 2 ? 30 : 90,
    estimated_peak_congestion_pct: c.car === 2 ? 50 : 120,
  }));
  j.arrival_alighting_guidance = {
    status: "available",
    note: "테스트용 문 위치",
    points: [
      { car: 2, door: 3, facility: "에스컬레이터", toward_station: "반포" },
    ],
  };
  await ready(page);
  await page.route("**/api/metro/journey", (r) => r.fulfill({ json: j }));
  await search(page);
  await expect(page.locator(".boarding-advice")).toContainText(
    "2호차가 상대적으로",
  );
  await expect(page.locator(".seat-note")).toContainText("알 수 없습니다");
  await expect(page.locator(".selected-car-detail,.door-strip")).toHaveCount(0);
  for (const train of await page.locator(".train-car").all()) {
    await expect(train.locator(".train-doors i")).toHaveCount(4);
  }
  await page.locator(".train-car").first().click();
  await expect(page.locator(".door-strip")).toHaveCount(0);
  await expect(page.locator(".door-advice")).toContainText("2호차 3번 문");
  await expect(page.locator(".journey-segment,.car-grid")).toHaveCount(0);
  const colors = await page
    .locator(".train-car")
    .evaluateAll((nodes) =>
      nodes.map((e) => getComputedStyle(e).backgroundColor),
    );
  expect(colors[0]).not.toBe(colors[1]);
  await page.locator(".map-segment").first().hover();
  await expect(page.getByRole("tooltip")).toBeVisible();
  await expect(page.locator(".map-readout")).toHaveCount(0);
});
test("equal estimates do not create false recommendations; colours use fixed scale", () => {
  const leg = {
    cars: [
      {
        car: 1,
        estimated_mean_congestion_pct: 50,
        estimated_peak_congestion_pct: 80,
      },
      {
        car: 2,
        estimated_mean_congestion_pct: 50,
        estimated_peak_congestion_pct: 80,
      },
    ],
  } as Journey["legs"][number];
  expect(lowerCrowdingCars(leg)).toEqual([]);
  leg.cars[1].estimated_mean_congestion_pct = 30;
  expect(lowerCrowdingCars(leg)).toEqual([2]);
  expect(crowdColor(250)).toBe(crowdColor(200));
  expect(crowdColor(0)).not.toBe(crowdColor(100));
});

test("door guidance belongs to the selected train, not the next train", () => {
  const journey = {
    legs: [
      { car_count: 10, step_indices: [0] },
      { car_count: 8, step_indices: [2] },
    ],
    steps: [
      { kind: "ride" },
      {
        kind: "transfer",
        door_guidance: {
          routes: [
            {
              alight: { car: 10, door: 4, label: "10호차 4번 문" },
              board: { car: 7, door: 4, label: "7호차 4번 문" },
            },
          ],
        },
      },
      { kind: "ride" },
    ],
    arrival_alighting_guidance: {
      points: [{ car: 2, door: 3, facility: "에스컬레이터" }],
    },
  } as unknown as Journey;
  expect(legDoors(journey, 0).points).toEqual([
    { car: 10, door: 4, purpose: "빠른 환승" },
  ]);
  expect(legDoors(journey, 1).points[0]).toMatchObject({
    car: 2,
    door: 3,
    purpose: "하차 접근",
  });
});
