"use client";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  ArrowRight,
  ArrowLeftRight,
  TrainFront,
  Clock3,
  Info,
  RefreshCw,
  ChevronRight,
  MapPin,
  LoaderCircle,
} from "lucide-react";
import {
  api,
  koreanNow,
  lineColors,
  timeLabel,
  type Segment,
  type Prediction,
} from "@/lib/metro";

import type { Journey } from "@/lib/journey";

export default function SubwayApp() {
  const [journey, setJourney] = useState<Journey | null>(null),
    [legIndex, setLegIndex] = useState(0);
  const [segments, setSegments] = useState<Segment[]>([]),
    [catalogError, setCatalogError] = useState(""),
    [catalogLoading, setCatalogLoading] = useState(true);
  const [line, setLine] = useState(7),
    [toLine, setToLine] = useState(7),
    [strategy, setStrategy] = useState("estimated_fastest"),
    [allowExpress, setAllowExpress] = useState(true),
    [origin, setOrigin] = useState(""),
    [destination, setDestination] = useState("");
  const [scheduled, setScheduled] = useState(false),
    [at, setAt] = useState(""),
    [result, setResult] = useState<Prediction | null>(null),
    [selectedCar, setSelectedCar] = useState(1);
  const [pending, setPending] = useState(false),
    [error, setError] = useState(""),
    [dirty, setDirty] = useState(false);
  const request = useRef<AbortController | null>(null),
    sequence = useRef(0);
  async function load() {
    setCatalogLoading(true);
    setCatalogError("");
    try {
      const data = await api<{ segments: Segment[] }>("segments");
      if (!data.segments.length || data.segments.some((s) => !s.id || !s.line))
        throw new Error(
          "전체 노선 API 준비 중입니다. 잠시 후 다시 연결해 주세요.",
        );
      setSegments(data.segments);
      const first =
        data.segments.find(
          (s) => s.line === 7 && s.from_station === "건대입구",
        ) || data.segments[0];
      setLine(first.line);
      setToLine(first.line);
      setOrigin(first.from_id);
      setDestination(
        data.segments.find(
          (s) => s.line === first.line && s.to_station === "고속터미널",
        )?.to_id || first.to_id,
      );
    } catch (e) {
      setCatalogError((e as Error).message);
    } finally {
      setCatalogLoading(false);
    }
  }
  useEffect(() => {
    void load();
    setAt(koreanNow());
    return () => request.current?.abort();
  }, []);
  const lines = useMemo(
    () => [...new Set(segments.map((s) => s.line))].sort((a, b) => a - b),
    [segments],
  );
  const stationsFor = (n: number) => [
    ...new Map(
      segments
        .filter((s) => s.line === n)
        .flatMap(
          (s) =>
            [
              [s.from_id, { id: s.from_id, name: s.from_station }],
              [s.to_id, { id: s.to_id, name: s.to_station }],
            ] as [string, { id: string; name: string }][],
        ),
    ).values(),
  ];
  const stations = stationsFor(line),
    destinations = stationsFor(toLine);
  const originStation = stations.find((s) => s.id === origin),
    destinationStation = destinations.find((s) => s.id === destination);
  function changed() {
    request.current?.abort();
    sequence.current++;
    setPending(false);
    setDirty(!!journey);
    setError("");
  }
  function chooseLine(value: number) {
    changed();
    setLine(value);
    setOrigin(stationsFor(value)[0].id);
  }
  function chooseOrigin(value: string) {
    changed();
    setOrigin(value);
  }
  async function predict(e: FormEvent) {
    e.preventDefault();
    if (!originStation || !destinationStation) return;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    const serial = ++sequence.current;
    setPending(true);
    setError("");
    setResult(null);
    setJourney(null);
    setDirty(false);
    try {
      const data = await api<Journey>(
        "journey",
        {
          from_line: line,
          to_line: toLine,
          strategy,
          allow_express: allowExpress,
          from_station: originStation.name,
          to_station: destinationStation.name,
          ...(scheduled ? { at: at + ":00+09:00" } : {}),
        },
        controller.signal,
      );
      if (sequence.current !== serial) return;
      setJourney(data);
      const first = data.steps.findIndex((s) => s.kind === "ride");
      const step = data.steps[first];
      setLegIndex(first);
      setResult(step?.kind === "ride" ? step.forecast : null);
      setSelectedCar(1);
    } catch (e) {
      if (sequence.current === serial && !controller.signal.aborted)
        setError((e as Error).message);
    } finally {
      if (sequence.current === serial) setPending(false);
    }
  }
  const car = result?.cars.find((c) => c.car === selectedCar),
    mean = result?.train_mean_congestion_pct || 0;
  const same =
    !!result &&
    result.cars.every(
      (c) =>
        Math.abs(
          c.estimated_congestion_pct - result.cars[0].estimated_congestion_pct,
        ) < 0.001,
    );
  const lineStationCount = new Set(
    segments
      .filter((s) => s.line === line)
      .flatMap((s) => [s.from_id, s.to_id]),
  ).size;
  return (
    <div className="min-h-screen">
      <header className="site-header">
        <div className="shell flex items-center justify-between gap-4">
          <a className="brand flex items-center gap-3" href="/">
            <span className="brand-icon">
              <TrainFront size={23} />
            </span>
            한 칸 여유<span className="beta">BETA</span>
          </a>
          <div className="school">
            YEONSUNG UNIVERSITY<span>클라우드 MLOps 프로젝트</span>
          </div>
        </div>
      </header>
      <main className="shell pb-10">
        <section className="intro">
          <div className="eyebrow">A LITTLE MORE ROOM, A BETTER RIDE</div>
          <h1>
            타기 전에, <span>칸별로 한눈에.</span>
          </h1>
          <p>출발부터 목적지까지, 이동 구간별 칸의 혼잡도를 비교하세요.</p>
          <div className="coverage">
            <span className="status-dot" />
            공개 조사자료 기반
            <span className="divider" />
            1–9호선 데이터 보유 구간
          </div>
        </section>
        <div className="app-grid">
          <aside>
            <form className="panel search-panel" onSubmit={predict}>
              <div className="flex items-center gap-2 mb-5">
                <MapPin size={18} />
                <h2>탑승 정보</h2>
              </div>
              {catalogLoading ? (
                <div className="py-10 text-center" role="status">
                  <LoaderCircle className="spin inline mr-2" size={18} />
                  지원 구간을 불러오고 있어요
                </div>
              ) : catalogError ? (
                <div role="alert">
                  <p>{catalogError}</p>
                  <button
                    className="secondary mt-4"
                    type="button"
                    onClick={() => void load()}
                  >
                    <RefreshCw size={15} />
                    다시 연결
                  </button>
                </div>
              ) : (
                <>
                  <fieldset>
                    <legend className="field-label">탑승 노선</legend>
                    <div className="line-grid">
                      {lines.map((n) => (
                        <button
                          type="button"
                          key={n}
                          onClick={() => chooseLine(n)}
                          aria-pressed={line === n}
                          className="line-choice"
                          style={
                            {
                              "--line-color": lineColors[n],
                            } as React.CSSProperties
                          }
                        >
                          <span>{n}</span>
                          {n}호선
                        </button>
                      ))}
                    </div>
                  </fieldset>
                  <p className="helper mt-3 mb-5">
                    현재 선택 노선 · {lineStationCount}개 역 데이터
                  </p>
                  <div className="route-fields">
                    <label className="field-label">
                      탑승역
                      <select
                        aria-label="탑승역"
                        value={origin}
                        onChange={(e) => chooseOrigin(e.target.value)}
                      >
                        {stations.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="flex items-center justify-between my-2">
                      <span className="helper">출발·도착을 바꿀 수 있어요</span>
                      <button
                        className="swap"
                        type="button"
                        aria-label="반대 방향으로 변경"
                        disabled={!destinationStation}
                        onClick={() => {
                          changed();
                          setLine(toLine);
                          setToLine(line);
                          setOrigin(destination);
                          setDestination(origin);
                        }}
                      >
                        <ArrowLeftRight size={15} />
                      </button>
                    </div>
                    <label className="field-label">
                      도착 노선
                      <select
                        aria-label="도착 노선"
                        value={toLine}
                        onChange={(e) => {
                          changed();
                          const n = Number(e.target.value);
                          setToLine(n);
                          setDestination(stationsFor(n)[0].id);
                        }}
                      >
                        {lines.map((n) => (
                          <option key={n} value={n}>
                            {n}호선
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="field-label">
                      목적지역
                      <select
                        aria-label="목적지역"
                        value={destination}
                        onChange={(e) => {
                          changed();
                          setDestination(e.target.value);
                        }}
                      >
                        {destinations.map((s) => (
                          <option value={s.id} key={s.id}>
                            {s.name}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <fieldset className="mt-5">
                    <legend className="field-label">경로 기준</legend>
                    <div className="segmented">
                      <button
                        type="button"
                        aria-pressed={strategy === "estimated_fastest"}
                        onClick={() => {
                          changed();
                          setStrategy("estimated_fastest");
                        }}
                      >
                        예상시간 우선
                      </button>
                      <button
                        type="button"
                        aria-pressed={strategy === "fewest_transfers"}
                        onClick={() => {
                          changed();
                          setStrategy("fewest_transfers");
                        }}
                      >
                        환승 최소
                      </button>
                    </div>
                    <label className="express-option">
                      <input
                        type="checkbox"
                        checked={allowExpress}
                        onChange={(e) => {
                          changed();
                          setAllowExpress(e.target.checked);
                        }}
                      />
                      9호선 급행 포함
                    </label>
                  </fieldset>
                  <fieldset className="mt-6">
                    <legend className="field-label flex items-center gap-2">
                      <Clock3 size={15} />
                      탑승 예정 일시
                    </legend>
                    <div className="segmented">
                      <button
                        type="button"
                        aria-pressed={!scheduled}
                        onClick={() => {
                          changed();
                          setScheduled(false);
                        }}
                      >
                        지금 출발
                      </button>
                      <button
                        type="button"
                        aria-pressed={scheduled}
                        onClick={() => {
                          changed();
                          setScheduled(true);
                        }}
                      >
                        일시 선택
                      </button>
                    </div>
                    {scheduled && (
                      <label className="field-label mt-3">
                        날짜와 시간
                        <input
                          aria-label="날짜와 시간"
                          type="datetime-local"
                          value={at}
                          required
                          onChange={(e) => {
                            changed();
                            setAt(e.target.value);
                          }}
                        />
                      </label>
                    )}
                    <p className="helper mt-2">
                      {scheduled
                        ? "선택한 일시 기준"
                        : "조회 버튼을 누른 시각 기준"}{" "}
                      · 한국 시간
                    </p>
                  </fieldset>
                  <button
                    type="submit"
                    className="primary mt-6 w-full"
                    disabled={
                      pending ||
                      !destinationStation ||
                      originStation?.name === destinationStation.name
                    }
                  >
                    {pending ? (
                      <LoaderCircle size={18} className="spin" />
                    ) : (
                      <TrainFront size={18} />
                    )}{" "}
                    {pending ? "혼잡도 계산 중" : "이동 구간 혼잡도 조회"}
                    {!pending && <ArrowRight size={17} />}
                  </button>
                </>
              )}
            </form>
            <p className="scope-note">
              <Info size={15} />
              <span>
                공개 데이터가 있는 노선과 환승 경로를 지원합니다. 소요시간은
                모델의 가정이며 실제 시간표와 다릅니다.
              </span>
            </p>
          </aside>
          <section
            className="panel result-panel"
            aria-label="혼잡도 조회 결과"
            aria-busy={pending}
          >
            {pending ? (
              <div className="empty-state" role="status">
                <LoaderCircle size={32} className="spin" />
                <h2>선택한 시간의 혼잡도를 계산하고 있어요</h2>
                <p>구간별 조사 패턴과 승강장 접근 위치를 확인합니다.</p>
              </div>
            ) : error ? (
              <div className="empty-state" role="alert">
                <Info size={32} />
                <h2>예측 결과를 가져올 수 없어요</h2>
                <p>{error}</p>
                <p>조건을 확인한 뒤 다시 조회해 주세요.</p>
              </div>
            ) : !journey ? (
              <div className="empty-state">
                <div className="empty-train">
                  <TrainFront size={38} />
                </div>
                <span className="eyebrow mt-6">YOUR NEXT RIDE</span>
                <h2>어느 칸에 여유가 있을까요?</h2>
                <p>
                  노선과 탑승할 구간을 선택하면
                  <br />
                  칸별 예상 혼잡도를 한눈에 비교할 수 있어요.
                </p>
                <div className="empty-steps">
                  <span>01 구간 선택</span>
                  <ChevronRight size={14} />
                  <span>02 시간 선택</span>
                  <ChevronRight size={14} />
                  <span>03 칸별 비교</span>
                </div>
              </div>
            ) : (
              <>
                {dirty && (
                  <p className="change-notice" role="status">
                    입력 조건이 변경됐습니다. 아래는 이전 조회 결과입니다.
                  </p>
                )}
                <div className="journey-overview">
                  <span className="pill">이동 경로 예측</span>
                  <h2 className="trip-title">
                    {journey.from_station}
                    <ArrowRight size={21} />
                    {journey.to_station}
                  </h2>
                  <p className="helper">
                    {timeLabel(journey.departure_at)} 출발 · 한국 시간
                  </p>
                  <div className="journey-summary">
                    <span>
                      약 {Math.round(journey.estimated_minutes)}분 · 가정 기반
                    </span>
                    <span>환승/열차 변경 {journey.transfer_count}회</span>
                    <span>{journey.ride_segments}개 이동 구간</span>
                  </div>
                  <p className="helper mt-3">
                    {journey.route_strategy === "fewest_transfers"
                      ? "환승 최소"
                      : "예상시간 우선"}{" "}
                    경로 · 도착 예상 {timeLabel(journey.estimated_arrival_at)}
                    <br />
                    실제 시간표·대기·지연을 반영한 도착 안내가 아닙니다.
                  </p>
                  <div className="journey-aggregate">
                    <span>예측 가능한 구간의 평균 혼잡도</span>
                    <strong>
                      {journey.available_segment_weighted_mean_pct === null
                        ? "자료 없음"
                        : journey.available_segment_weighted_mean_pct.toFixed(
                            1,
                          ) + "%"}
                    </strong>
                    <small>
                      {journey.predicted_segments}/{journey.ride_segments}개
                      구간 · 탑승시간 가중 평균
                    </small>
                  </div>
                  {journey.status !== "complete" && (
                    <p className="change-notice" role="status">
                      일부 구간에 예측 자료가 없습니다. 평균은 예측 가능한
                      구간만 포함합니다.
                    </p>
                  )}
                  <div
                    className="journey-segments"
                    aria-label="이동 경로 구간 선택"
                  >
                    {journey.steps.map((step, i) =>
                      step.kind === "transfer" ? (
                        <div className="transfer-step" key={i}>
                          {step.from_station} 환승 · {step.from_line}호선 →{" "}
                          {step.to_line}호선
                          <span>
                            도보·대기 약 {Math.round(step.estimated_minutes)}분
                            (가정)
                          </span>
                        </div>
                      ) : (
                        <button
                          type="button"
                          className="journey-segment"
                          key={i}
                          aria-pressed={i === legIndex}
                          onClick={() => {
                            setLegIndex(i);
                            setResult(step.forecast);
                            setSelectedCar(1);
                          }}
                        >
                          <span
                            className="step-line"
                            style={{ color: lineColors[step.line] }}
                          >
                            {step.line}호선 · {step.service}
                            {step.train_change_wait_minutes > 0
                              ? " · 열차 변경"
                              : ""}
                          </span>
                          {step.from_station} → {step.to_station}
                          <span>{timeLabel(step.forecast_at)} 기준</span>
                          <strong>
                            {step.forecast
                              ? step.forecast.train_mean_congestion_pct.toFixed(
                                  1,
                                ) + "%"
                              : "자료 없음"}
                          </strong>
                        </button>
                      ),
                    )}
                  </div>
                  <details className="method">
                    <summary>탑승 열차별 칸 평균·최대 혼잡도</summary>
                    <p className="helper mt-2">
                      같은 열차를 타는 구간끼리 집계합니다. 환승 전후의 호차는
                      서로 다른 열차입니다.
                    </p>
                    {journey.legs.map((leg, i) => (
                      <div key={i} className="leg-summary">
                        <strong>
                          {leg.line}호선 {leg.service} · {leg.from_station} →{" "}
                          {leg.to_station}
                        </strong>
                        <p className="helper">
                          {leg.predicted_segments}/{leg.total_segments}개 구간에
                          자료 있음 · 평균은 유효 구간의 탑승시간 가중값
                        </p>
                        {leg.cars.length ? (
                          <table>
                            <thead>
                              <tr>
                                <th>호차</th>
                                <th>평균</th>
                                <th>최대</th>
                              </tr>
                            </thead>
                            <tbody>
                              {leg.cars.map((c) => (
                                <tr key={c.car}>
                                  <td>{c.car}호차</td>
                                  <td>
                                    {c.estimated_mean_congestion_pct.toFixed(1)}
                                    %
                                  </td>
                                  <td>
                                    {c.estimated_peak_congestion_pct.toFixed(1)}
                                    %
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        ) : (
                          <p>자료 없음</p>
                        )}
                      </div>
                    ))}
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
                {!result ? (
                  <div role="status" className="empty-state">
                    <Info size={25} />
                    <h2>이 구간의 예측값이 없습니다</h2>
                    <p>
                      {journey.steps[legIndex]?.kind === "ride"
                        ? journey.steps[legIndex].unavailable_reason
                        : "탑승 구간을 선택하세요."}
                    </p>
                    <p>다른 구간을 선택하면 확인할 수 있어요.</p>
                  </div>
                ) : (
                  <>
                    <div className="result-heading">
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <span
                            className="line-badge"
                            style={{ background: lineColors[result.line] }}
                          >
                            {result.line}호선
                          </span>
                          <span className="pill">
                            {result.service || "일반"}
                          </span>
                          <span className="pill">칸별 추정</span>
                        </div>
                        <h2 className="trip-title">
                          {result.from_station}
                          <ArrowRight size={21} />
                          {result.to_station}
                        </h2>
                        <p className="helper">
                          {timeLabel(result.requested_at)} · {result.direction}
                        </p>
                      </div>
                      <span className="subtle-label">
                        {result.cars.length}량 편성
                      </span>
                    </div>
                    <div className="mean-row">
                      <div>
                        <span className="field-label">
                          열차 평균 예상 혼잡도
                        </span>
                        <div className="mean-value">
                          {mean.toFixed(1)}
                          <small>%</small>
                        </div>
                      </div>
                      <div className="mean-note">
                        {result.daytype} · {result.time_bin} 시간대
                        <br />
                        개별 열차의 실측값이 아닙니다
                      </div>
                    </div>
                    <div className="flex items-center justify-between gap-3 flex-wrap mt-7 mb-4">
                      <h3>칸별 혼잡도 비교</h3>
                      <span className="helper">
                        호차 번호순 · 칸을 눌러 상세 보기
                      </span>
                    </div>
                    <div
                      className="car-grid"
                      style={
                        {
                          "--columns":
                            result.cars.length === 4
                              ? 4
                              : result.cars.length === 6
                                ? 3
                                : result.cars.length === 8
                                  ? 4
                                  : 5,
                        } as React.CSSProperties
                      }
                    >
                      {result.cars.map((c) => (
                        <button
                          type="button"
                          className="car"
                          key={c.car}
                          aria-pressed={selectedCar === c.car}
                          aria-label={`${c.car}호차 ${c.estimated_congestion_pct.toFixed(1)}%, 상세 보기`}
                          onClick={() => setSelectedCar(c.car)}
                        >
                          <span className="car-number">{c.car}호차</span>
                          <strong>
                            {c.estimated_congestion_pct.toFixed(1)}
                            <small>%</small>
                          </strong>
                          <span className="car-track">
                            <span
                              style={{
                                width:
                                  Math.min(
                                    (c.estimated_congestion_pct /
                                      Math.max(
                                        150,
                                        ...result.cars.map(
                                          (x) => x.estimated_congestion_pct,
                                        ),
                                      )) *
                                      100,
                                    100,
                                  ) + "%",
                              }}
                            />
                          </span>
                        </button>
                      ))}
                    </div>
                    {same && (
                      <p className="helper mt-3">
                        이 결과에서는 모든 칸에 동일한 값이 배분되었습니다. 칸별
                        우열을 구분하지 않습니다.
                      </p>
                    )}
                    {car && (
                      <div className="car-detail" aria-live="polite">
                        <div className="flex justify-between gap-3 flex-wrap">
                          <strong>{car.car}호차 상세</strong>
                          <span>
                            열차 평균 대비{" "}
                            {car.estimated_congestion_pct - mean > 0 ? "+" : ""}
                            {(car.estimated_congestion_pct - mean).toFixed(1)}%p
                          </span>
                        </div>
                        <p>
                          위치 배분 가정에 따른 범위{" "}
                          <b>
                            {car.scenario_range_pct[0].toFixed(1)}–
                            {car.scenario_range_pct[1].toFixed(1)}%
                          </b>
                        </p>
                        <span className="helper">
                          이 범위는 통계적 신뢰구간이 아닙니다.
                        </span>
                        {result.location_features?.transfer_board_cars.includes(
                          car.car,
                        ) && (
                          <p className="location-note">
                            환승 후 승차 위치가 인접한 호차입니다.
                          </p>
                        )}
                        {result.location_features?.access_cars.includes(
                          car.car,
                        ) && (
                          <p className="location-note">
                            에스컬레이터 접근 위치가 인접한 호차입니다.
                          </p>
                        )}
                      </div>
                    )}
                    <div className="evidence-note">
                      <Info size={16} />
                      <p>
                        칸별 값은 공개 혼잡도와 위치 정보를 결합한 추정
                        시나리오입니다. 실제 칸별 관측값으로 검증되지
                        않았습니다.
                      </p>
                    </div>
                    <details className="method">
                      <summary>예측 기준과 데이터 확인</summary>
                      <ul>
                        {result.warnings.map((w, i) => (
                          <li key={i}>{w}</li>
                        ))}
                      </ul>
                      <dl>
                        <dt>운행일</dt>
                        <dd>{result.service_date}</dd>
                        <dt>모델 버전</dt>
                        <dd>{result.model_version}</dd>
                        {Object.entries(result.evidence).map(([k, v]) => (
                          <div className="contents" key={k}>
                            <dt>
                              {(
                                {
                                  available_after: "조회 가능 기준일",
                                  next_profile_last_period: "다음 시간대 조사",
                                  trained_through: "학습 기준",
                                  profile_last_period: "최근 조사",
                                  profile_snapshot_count: "조사 건수",
                                  car_ground_truth_count: "칸별 실측 정답 수",
                                } as Record<string, string>
                              )[k] || k}
                            </dt>
                            <dd>{String(v)}</dd>
                          </div>
                        ))}
                      </dl>
                    </details>
                  </>
                )}
              </>
            )}
          </section>
        </div>
        <footer className="page-footer">
          <span>YEONSUNG · 한 칸 여유</span>
          <span>공개 교통 데이터 기반 · 연구용 추정 서비스</span>
        </footer>
      </main>
    </div>
  );
}
