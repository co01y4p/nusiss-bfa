"use client";

import { useEffect, useState } from "react";

import { apiRequest } from "@/lib/api";

export type FacilityCategory =
  | "HVAC"
  | "LIFT"
  | "ELECTRICAL"
  | "PLUMBING"
  | "ACCESS"
  | "GENERAL";

export type Facility = { id: string; name: string; category: FacilityCategory };
export type Floor = { id: string; name: string; facilities: Facility[] };
type BuildingLayoutResponse = { floors: Floor[] };

export type SelectedFacility = {
  facilityId: string;
  locationLabel: string;
  example: string;
};

const CATEGORY_META: Record<
  FacilityCategory,
  { color: string; label: string; example: string }
> = {
  HVAC: {
    color: "#1457d9",
    label: "HVAC",
    example:
      "The HVAC/AC unit here is blowing warm air and making an unusual noise.",
  },
  LIFT: {
    color: "#6d3fa0",
    label: "Lift",
    example: "The lift here is stuck or not responding to calls.",
  },
  ELECTRICAL: {
    color: "#a15c00",
    label: "Electrical",
    example: "There is a power or wiring issue in this area.",
  },
  PLUMBING: {
    color: "#0f7a8c",
    label: "Plumbing",
    example: "There is a leak, blockage, or plumbing issue in this area.",
  },
  ACCESS: {
    color: "#167447",
    label: "Access",
    example: "The door or access control here is not working.",
  },
  GENERAL: {
    color: "#47536b",
    label: "General",
    example: "There is a facility issue in this area that needs attention.",
  },
};

export default function BuildingMap({
  selectedId,
  onSelect,
}: {
  selectedId: string | null;
  onSelect: (facility: SelectedFacility) => void;
}) {
  const [floors, setFloors] = useState<Floor[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiRequest<BuildingLayoutResponse>("/facilities/layout")
      .then((data) => setFloors(data.floors))
      .catch(() => setError("Unable to load the building layout."));
  }, []);

  function pick(floor: Floor, facility: Facility) {
    const meta = CATEGORY_META[facility.category];
    onSelect({
      facilityId: facility.id,
      locationLabel: `${floor.name} — ${facility.name}`,
      example: meta.example,
    });
  }

  if (error) {
    return <div className="notice error">{error}</div>;
  }

  if (floors === null) {
    return <div className="notice">Loading building layout...</div>;
  }

  if (floors.length === 0) {
    return (
      <div className="notice warning">
        No building layout has been configured yet. Enter the location
        manually below, or ask a manager to set one up under Manager →
        Building setup.
      </div>
    );
  }

  return (
    <div className="building-map">
      <div className="building-figure">
        <div className="building-roof" />
        {floors.map((floor) => (
          <div className="building-floor-row" key={floor.id}>
            <div className="floor-label">{floor.name}</div>
            <div className="floor-rooms">
              {floor.facilities.length === 0 && (
                <span className="muted-note">No facilities configured</span>
              )}
              {floor.facilities.map((facility) => {
                const meta = CATEGORY_META[facility.category];
                return (
                  <button
                    type="button"
                    key={facility.id}
                    className="room-block"
                    data-selected={selectedId === facility.id}
                    style={{ "--room-color": meta.color } as React.CSSProperties}
                    onClick={() => pick(floor, facility)}
                  >
                    {facility.name}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
        <div className="building-ground" />
      </div>

      <div className="building-legend">
        {Object.entries(CATEGORY_META).map(([key, meta]) => (
          <span className="legend-item" key={key}>
            <span className="legend-dot" style={{ background: meta.color }} />
            {meta.label}
          </span>
        ))}
      </div>
    </div>
  );
}
