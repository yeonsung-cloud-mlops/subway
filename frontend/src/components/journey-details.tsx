import type { DoorGuidance, Journey, StationFacilities } from "../lib/journey";

export function TransferDoors({ guidance }: { guidance?: DoorGuidance }) {
  if (!guidance) return null;
  return (
    <div className="mt-2 text-sm">
      {guidance.routes?.length ? (
        guidance.routes.map((r) => (
          <p key={r.source_route_id}>
            빠른 환승: <strong>{r.alight.label}에서 하차</strong> →{" "}
            <strong>{r.board.label}에서 승차</strong>
            <br />
            <small>
              {r.from_direction} → {r.to_direction} · 자료 기준 {guidance.as_of}
            </small>
          </p>
        ))
      ) : (
        <p>{guidance.note}</p>
      )}
    </div>
  );
}
function AccessDoors({
  title,
  guidance,
}: {
  title: string;
  guidance?: DoorGuidance;
}) {
  if (!guidance) return null;
  return (
    <section className="mt-4">
      <h3 className="font-semibold">{title}</h3>
      {guidance.points?.length ? (
        <p className="mt-2 flex flex-wrap gap-2">
          {guidance.points.map((p, i) => (
            <span className="pill" key={i}>
              {p.car}호차 {p.door}번 문 · {p.facility}
            </span>
          ))}
        </p>
      ) : (
        <p className="helper mt-1">해당 방면의 호차·문 위치 자료가 없습니다.</p>
      )}
      <p className="helper mt-2">{guidance.note}</p>
    </section>
  );
}
function Facilities({
  title,
  station,
}: {
  title: string;
  station: StationFacilities;
}) {
  const available = Object.entries(station.features).filter(
    ([, value]) => value === true,
  );
  return (
    <section className="leg-summary">
      <h3 className="font-semibold">
        {title} · {station.station_name} {station.line}호선 편의시설
      </h3>
      {station.status === "available" ? (
        <>
          <p className="mt-2 flex flex-wrap gap-2">
            {available.length
              ? available.map(([name]) => (
                  <span className="pill" key={name}>
                    {name}
                  </span>
                ))
              : "자료에 설치된 것으로 표시된 시설이 없습니다."}
          </p>
          <p className="helper mt-2">
            설치 여부 기준 {station.as_of} · 현재 가동 여부는 별도 확인이
            필요합니다.
          </p>
        </>
      ) : (
        <p className="helper mt-2">
          이 노선 승강장의 편의시설 자료를 확보하지 못했습니다. 시설이 없다는
          뜻은 아닙니다.
        </p>
      )}
      {station.nursing_rooms.map((room, i) => (
        <p key={i} className="helper mt-2">
          {room.type}: {room.location} · {room.fare_area} 구역 (자료 기준{" "}
          {room.as_of})
        </p>
      ))}
    </section>
  );
}
export function JourneyDetails({ journey }: { journey: Journey }) {
  return (
    <details className="method" open>
      <summary>빠른 승하차 문 · 출발·도착역 편의시설</summary>
      {journey.timetable?.as_of && (
        <p className="helper mt-2">
          시간표 기준 {journey.timetable.as_of} · 급행·일반 열차의 출도착 시각과
          대기·환승 보행시간을 반영한 경로입니다. 현재 운행과 실시간 지연을
          확인한 자료는 아닙니다.
        </p>
      )}
      <p className="helper mt-2">
        칸별 추정에는 이 경로의 출입 접근 문과 환승 문 위치를 반영합니다. 특정
        출구별 최단 문 자료와 칸별 실측값은 아직 확보하지 못했습니다.
      </p>
      <AccessDoors
        title="출발역 승차 접근 위치"
        guidance={journey.departure_boarding_guidance}
      />
      <AccessDoors
        title="도착역 하차 접근 위치"
        guidance={journey.arrival_alighting_guidance}
      />
      {journey.endpoint_facilities && (
        <>
          <Facilities
            title="출발"
            station={journey.endpoint_facilities.departure}
          />
          <Facilities
            title="도착"
            station={journey.endpoint_facilities.arrival}
          />
        </>
      )}
    </details>
  );
}
