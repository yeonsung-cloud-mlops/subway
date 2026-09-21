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
};
export type TransferStep = {
  kind: "transfer";
  from_station: string;
  to_station: string;
  from_line: number;
  to_line: number;
  start_at: string;
  end_at: string;
  estimated_minutes: number;
};
export type Journey = {
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
