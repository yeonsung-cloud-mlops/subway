"use client";
import { useState } from "react";
import { ArrowRight, Info } from "lucide-react";
import type { Journey } from "@/lib/journey";
import { lineColors, timeLabel } from "@/lib/metro";
import { crowdColor, lowerCrowdingCars, legDoors } from "@/lib/boarding";
import { JourneyDetails, TransferDoors } from "./journey-details";

export default function JourneyExperience({ journey }: { journey: Journey }) {
  const [legIndex, setLegIndex] = useState(0),
    [selectedCar, setSelectedCar] = useState<number | null>(null),
    [pinned, setPinned] = useState<number | null>(null),
    [hover, setHover] = useState<number | null>(null);
  const leg = journey.legs[legIndex];
  const best = leg ? lowerCrowdingCars(leg) : [];
  const car = leg?.cars.find((c) => c.car === (selectedCar ?? best[0] ?? 1));
  const guidance = leg ? legDoors(journey, legIndex) : null;
  const chosen = hover ?? pinned;
  const step = chosen === null ? null : journey.steps[chosen];
  const convenient = guidance?.points.filter((p) => best.includes(p.car)) || [];
  function selectStep(i: number) {
    setPinned(i);
    const l = journey.legs.findIndex((l) => l.step_indices.includes(i));
    if (l >= 0) {
      setLegIndex(l);
      setSelectedCar(null);
    }
  }
  return (
    <div className="journey-experience">
      <header className="experience-heading">
        <span className="eyebrow">YOUR JOURNEY</span>
        <h2 className="trip-title">
          {journey.from_station}
          <ArrowRight size={22} />
          {journey.to_station}
        </h2>
        <p className="helper">
          {timeLabel(journey.departure_at)} 출발 · 약{" "}
          {Math.round(journey.estimated_minutes)}분 · 환승/열차 변경{" "}
          {journey.transfer_count}회
        </p>
        <p className="helper">
          {journey.timetable?.status === "snapshot"
            ? "공개 시간표"
            : journey.timetable?.status === "mixed"
              ? "시간표·가정"
              : "가정"}{" "}
          기반 · 실시간 운행 및 좌석 현황이 아닙니다.
        </p>
      </header>
      <div className="experience-layout">
        <section className="route-schematic" aria-label="이동 경로 노선도">
          <h3>이동 경로</h3>
          <p className="helper">구간을 누르거나 가리켜 보세요</p>
          <p className="route-crowding-key">열차 평균 · 초록 0 → 빨강 200%+</p>
          <div className="route-track">
            {journey.steps.map((s, i) =>
              s.kind === "transfer" ? (
                <div className="map-transfer" key={i}>
                  <span className="transfer-node" />
                  <span>
                    {s.from_station}
                    <small>
                      {s.from_line} → {s.to_line}호선 환승
                    </small>

                  </span>
                </div>
              ) : (
                <button
                  type="button"
                  className="map-segment"
                  key={i}
                  style={
                    {
                      "--route-color": lineColors[s.line],
                    } as React.CSSProperties
                  }
                  aria-pressed={pinned === i}
                  aria-label={`${s.from_station}에서 ${s.to_station}, ${s.line}호선 혼잡도 보기`}
                  onClick={() => selectStep(i)}
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                  onFocus={() => setHover(i)}
                  onBlur={() => setHover(null)}
                >
                  <span className="map-rail" />
                  <span className="map-node" />
                  <span className="map-station">
                    {s.from_station}
                    <small>
                      {s.line}호선 {s.service}
                      {s.train_change_wait_minutes > 0 ? " · 열차 변경" : ""}
                    </small>
                    <span className="map-crowding">
                      <span
                        className="map-crowding-scale"
                        data-missing={!s.forecast}
                        aria-hidden="true"
                      >
                        {s.forecast && (
                          <span
                            className="map-crowding-marker"
                            style={{
                              left: `${Math.max(0, Math.min(200, s.forecast.train_mean_congestion_pct)) / 2}%`,
                            }}
                          />
                        )}
                      </span>
                      <span className="map-crowding-value">
                        {s.forecast
                          ? `${s.forecast.train_mean_congestion_pct.toFixed(1)}%`
                          : "자료 없음"}
                      </span>
                    </span>
                  </span>
                  {hover === i && (
                    <span className="map-tooltip" role="tooltip">
                      {s.from_station} → {s.to_station}
                      <b>
                        {s.forecast
                          ? `${s.forecast.train_mean_congestion_pct.toFixed(1)}%`
                          : "자료 없음"}
                      </b>
                      <small>{timeLabel(s.forecast_at)} 기준</small>
                    </span>
                  )}
                </button>
              ),
            )}
            <div className="map-destination">
              <span className="map-node" />
              <b>{journey.to_station}</b>
            </div>
          </div>
          <div className="map-readout" aria-live="polite">
            {step?.kind === "ride" ? (
              <>
                <strong>
                  {step.from_station} → {step.to_station}
                </strong>
                <span>
                  {step.forecast
                    ? `열차 평균 ${step.forecast.train_mean_congestion_pct.toFixed(1)}%`
                    : "예측 자료 없음"}
                </span>
                <small>{timeLabel(step.forecast_at)} 기준</small>
              </>
            ) : step?.kind === "transfer" ? (
              <>
                <strong>{step.from_station} 환승</strong>
                <TransferDoors guidance={step.door_guidance} />
              </>
            ) : (
              <span>
                노선 위 구간을 선택하면
                <br />
                시간대별 혼잡도가 표시됩니다.
              </span>
            )}
          </div>
        </section>
        <section className="boarding-view" aria-label="탑승할 열차와 호차 안내">
          <h3>어느 칸에 탈까요?</h3>
          <div className="leg-tabs" aria-label="탑승 열차 선택">
            {journey.legs.map((l, i) => (
              <button
                type="button"
                key={i}
                aria-pressed={legIndex === i}
                onClick={() => {
                  setLegIndex(i);
                  setSelectedCar(null);
                }}
              >
                <span style={{ background: lineColors[l.line] }}>{l.line}</span>
                {l.from_station} → {l.to_station}
                <small>
                  {l.service} · {l.car_count}량
                </small>
              </button>
            ))}
          </div>
          {leg && (
            <>
              <div className="boarding-advice" aria-live="polite">
                <span className="advice-label">혼잡도를 우선하면</span>
                <strong>
                  {!leg.cars.length
                    ? "추천 자료가 없습니다"
                    : best.length
                      ? `${best.join(" · ")}호차가 상대적으로 여유로워요`
                      : "칸별 차이를 구분할 수 없어요"}
                </strong>
                <p>
                  {best.length
                    ? "예측 가능한 이동 구간의 평균 혼잡도가 가장 낮은 칸입니다."
                    : "같은 값이거나 자료가 없어 특정 칸을 추천하지 않습니다."}
                </p>
                <p className="seat-note">
                  좌석 잔여량 데이터가 없어 착석 가능 여부·확률은 알 수
                  없습니다.
                </p>
              </div>
              <div className="train-heading">
                <span>
                  {leg.line}호선 {leg.service} · 연결된 열차
                </span>
                <small>호차 번호순 도식 · 실제 앞/뒤 방향 아님</small>
              </div>
              <div
                className="train-scroll"
                aria-label="연결된 열차, 좌우로 스크롤"
              >
                <div className="connected-train">
                  {Array.from({ length: leg.car_count }, (_, i) => {
                    const c = leg.cars.find((c) => c.car === i + 1);
                    return (
                      <button
                        type="button"
                        key={i}
                        className="train-car"
                        aria-pressed={car?.car === i + 1}
                        aria-label={`${i + 1}호차 ${c ? c.estimated_mean_congestion_pct.toFixed(1) + "%" : "자료 없음"}`}
                        style={
                          {
                            "--car-fill": c
                              ? crowdColor(c.estimated_mean_congestion_pct)
                              : "#e0e7eb",
                          } as React.CSSProperties
                        }
                        onClick={() => setSelectedCar(i + 1)}
                      >
                        <span className="train-roof" />
                        <span className="train-number">{i + 1}호차</span>
                        <strong>
                          {c
                            ? c.estimated_mean_congestion_pct.toFixed(1) + "%"
                            : "—"}
                        </strong>
                        <span className="train-windows" aria-hidden="true">
                          <i />
                          <i />
                          <i />
                        </span>
                        <span className="train-wheels" aria-hidden="true" />
                        {best.includes(i + 1) && (
                          <span className="train-recommend">추천</span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div className="heat-legend">
                <span>혼잡도 낮음</span>
                <span className="heat-ramp" />
                <span>높음</span>
                <small>0% → 100% → 200% 이상</small>
              </div>
              <p className="helper">
                {leg.predicted_segments}/{leg.total_segments}개 구간의 탑승시간
                가중 평균 · 부분 자료는 전체 이동을 대표하지 않을 수 있습니다.
              </p>
              {car && (
                <div className="selected-car-detail" aria-live="polite">
                  <h4>
                    {car.car}호차{" "}
                    <span>
                      구간 평균 {car.estimated_mean_congestion_pct.toFixed(1)}%
                      · 최대 {car.estimated_peak_congestion_pct.toFixed(1)}%
                    </span>
                  </h4>
                  <div
                    className="door-strip"
                    aria-label={`${car.car}호차 문 위치`}
                  >
                    {[1, 2, 3, 4].map((d) => {
                      const point = guidance?.points.find(
                        (p) => p.car === car.car && p.door === d,
                      );
                      return (
                        <div
                          className={
                            point ? "door-position known" : "door-position"
                          }
                          key={d}
                        >
                          <span className="door-drawing" aria-hidden="true" />
                          <strong>
                            {car.car}-{d}
                          </strong>
                          <small>
                            {point ? point.purpose : "문별 혼잡도 미측정"}
                          </small>
                        </div>
                      );
                    })}
                  </div>
                  <p className="helper">
                    문 번호는 위치 확인용 도식입니다. 문마다 승객이 얼마나
                    몰리는지는 알 수 없습니다.
                  </p>
                </div>
              )}
              <div className="door-advice">
                <h3>어떤 문이 편할까요?</h3>
                <dl>
                  <dt>{guidance?.purpose}</dt>
                  <dd>
                    {guidance?.points.length
                      ? guidance.points
                          .map((p) => `${p.car}호차 ${p.door}번 문`)
                          .join(" · ")
                      : "이 방면의 문 위치 자료가 없습니다."}
                  </dd>
                  <dt>여유 있는 칸 + 편한 이동</dt>
                  <dd>
                    {convenient.length
                      ? convenient
                          .map((p) => `${p.car}호차 ${p.door}번 문`)
                          .join(" · ")
                      : !guidance?.points.length
                        ? "확인된 문 위치가 없어 함께 추천할 수 없습니다."
                        : best.length
                          ? "추천 칸과 확인된 접근 문이 겹치지 않습니다. 혼잡도와 동선 중 우선순위를 선택하세요."
                          : "칸별 우열 또는 문 위치를 확인할 수 없습니다."}
                  </dd>
                  <dt>혼잡도가 가장 낮은 문</dt>
                  <dd>
                    문별 혼잡도 데이터가 없어 특정 문을 추천할 수 없습니다.
                  </dd>
                </dl>
                {guidance?.guidance?.note && (
                  <p className="helper">
                    {guidance.guidance.note}{" "}
                    {guidance.guidance.as_of &&
                      `자료 기준 ${guidance.guidance.as_of}`}
                  </p>
                )}
                {guidance?.guidance?.routes?.length ? (
                  <TransferDoors guidance={guidance.guidance} />
                ) : null}
              </div>
            </>
          )}
        </section>
      </div>
      <p className="evidence-note">
        <Info size={16} />
        칸별 색상과 추천은 실측 검증 전 추정치입니다. 좌석 확보나 실제 혼잡도를
        보장하지 않습니다.
      </p>
      <details className="method">
        <summary>역 편의시설 · 문 위치 상세 출처</summary>
        <JourneyDetails journey={journey} />
      </details>
      <details className="method">
        <summary>경로·시간 계산 기준</summary>
        <ul>
          {journey.warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      </details>
    </div>
  );
}
