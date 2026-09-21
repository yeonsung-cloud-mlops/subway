"use client";

import JourneyExperience from "./journey-experience";
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
import { api, koreanNow, lineColors, type Segment } from "@/lib/metro";

import type { Journey } from "@/lib/journey";

export default function SubwayApp() {
  const [journey, setJourney] = useState<Journey | null>(null);
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
    [at, setAt] = useState("");
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
    } catch (e) {
      if (sequence.current === serial && !controller.signal.aborted)
        setError((e as Error).message);
    } finally {
      if (sequence.current === serial) setPending(false);
    }
  }
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
                공개 시간표와 환승 보행시간 기준이며 실시간 지연은 반영하지 않습니다.
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
                <JourneyExperience
                  key={
                    journey.departure_at +
                    journey.from_station +
                    journey.to_station
                  }
                  journey={journey}
                />
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
