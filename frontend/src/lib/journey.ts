import type { Prediction } from "./metro";
export type RideStep = {
  kind: "ride";
  line: number;
  service: string;
  from_station: string;
  to_station: string;
  start_at: string;
  forecast_at: string;
  end_at: string;
  estimated_minutes: number;
  ride_minutes: number;
  train_change_wait_minutes: number;
  status: string;
  unavailable_reason: string | null;
  forecast: Prediction | null;
  timing_basis?: string;
  waiting_minutes?: number;
  dwell_minutes?: number;
  schedule?: { train_no: string; destination: string } | null;
};
export type TransferStep = {
  door_guidance?: DoorGuidance;
  kind: "transfer";
  purpose?: "interchange" | "destination_access";
  counts_as_transfer?: boolean;
  from_station: string;
  to_station: string;
  from_line: number;
  to_line: number;
  start_at: string;
  end_at: string;
  estimated_minutes: number;
};
export type Journey = {
  to_line?: number;
  arrival_station_id?: string;
  destination_access_minutes?: number;
  timetable?: {
    status: string;
    as_of?: string;
    matched_ride_segments: number;
    fallback_ride_segments: number;
    current_service_verified?: boolean;
  };
  endpoint_facilities?: {
    departure: StationFacilities;
    arrival: StationFacilities;
  };
  departure_boarding_guidance?: DoorGuidance;
  arrival_alighting_guidance?: DoorGuidance;
  from_station: string;
  to_station: string;
  departure_at: string;
  estimated_arrival_at: string;
  estimated_minutes: number;
  route_strategy: string;
  transfer_count: number;
  ride_segments: number;
  predicted_segments: number;
  status: "complete" | "partial" | "unavailable";
  available_segment_weighted_mean_pct: number | null;
  steps: (RideStep | TransferStep)[];
  legs: {
    line: number;
    service: string;
    from_station: string;
    to_station: string;
    car_count: number;
    step_indices: number[];
    coverage: number;
    predicted_segments: number;
    total_segments: number;
    cars: {
      car: number;
      estimated_mean_congestion_pct: number;
      estimated_peak_congestion_pct: number;
    }[];
  }[];
  warnings: string[];
};

export type DoorGuidance = {
  status: string;
  note: string;
  as_of?: string;
  points?: {
    car: number;
    door: number;
    facility: string;
    toward_station: string;
  }[];
  routes?: {
    source_route_id: string;
    alight: { label: string };
    board: { label: string };
    from_direction: string;
    to_direction: string;
  }[];
};
export type StationFacilities = {
  station_id: string;
  station_name: string;
  line: number;
  status: string;
  as_of: string;
  features: Record<string, boolean | null>;
  nursing_rooms: {
    location: string;
    fare_area: string;
    type: string;
    as_of: string;
  }[];
};
