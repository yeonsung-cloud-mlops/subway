import { test, expect } from "@playwright/test";

test("scheduled route serves real door and facility data", async ({
  page,
  request,
}) => {
  const response = await request.post(
    `${process.env.ENRICHMENT_API_URL || "http://127.0.0.1:8011"}/v1/journeys/predict`,
    {
      data: {
        from_station: "건대",
        to_station: "고터",
        at: "2026-09-21T08:15:00+09:00",
      },
    },
  );
  expect(response.ok()).toBeTruthy();
  const result = await response.json();
  expect(result.timetable.route_search_basis).toBe(
    "time_expanded_earliest_arrival",
  );
  expect(result.arrival_alighting_guidance.points.length).toBeGreaterThan(0);
  // Use the live backend response while leaving other tasks' dev-server environment unchanged.
  await page.route("**/api/metro/journey", (route) =>
    route.fulfill({ json: result }),
  );
  await page.goto("/");
  const button = page.getByRole("button", {
    name: "이동 구간 혼잡도 조회",
    exact: true,
  });
  await expect(button).toBeEnabled();
  await button.click();
  await expect(
    page.getByText("도착 · 고속터미널 7호선 편의시설"),
  ).toBeAttached();
  const details = page.getByText("역 편의시설 · 문 위치 상세 출처", {
    exact: true,
  });
  if (await details.count()) {
    if (
      await details.evaluate(
        (el) => !(el.parentElement as HTMLDetailsElement).open,
      )
    )
      await details.click();
  }
  await expect(
    page.getByText("도착 · 고속터미널 7호선 편의시설"),
  ).toBeVisible();
  await expect(page.getByText(/시간표 기준 2025-09-30/).first()).toBeVisible();
  await expect(
    page.getByText(/특정 출구별 최단 문 자료와 칸별 실측값/),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/enrichment-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "test-results/enrichment-mobile.png",
    fullPage: true,
  });
});
