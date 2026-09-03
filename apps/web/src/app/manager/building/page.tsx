"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { apiRequest, managerHeaders } from "@/lib/api";

type FacilityCategory =
  | "HVAC"
  | "LIFT"
  | "ELECTRICAL"
  | "PLUMBING"
  | "ACCESS"
  | "GENERAL";

type FacilityDraft = { key: string; name: string };
type FloorDraft = { key: string; name: string; facilities: FacilityDraft[] };

type ApiFacility = { id: string; name: string; category: FacilityCategory };
type ApiFloor = { id: string; name: string; facilities: ApiFacility[] };
type ApiLayout = { floors: ApiFloor[] };

const PRESETS: { label: string; namePrefix: string; numbered: boolean }[] = [
  { label: "+ Toilet", namePrefix: "Toilet", numbered: true },
  { label: "+ Office area", namePrefix: "Office", numbered: true },
  { label: "+ Lift lobby", namePrefix: "Lift Lobby", numbered: false },
  { label: "+ Electrical room", namePrefix: "Electrical Room", numbered: false },
  { label: "+ HVAC plant room", namePrefix: "HVAC Plant Room", numbered: false },
  { label: "+ Pantry", namePrefix: "Pantry", numbered: false },
  { label: "+ Main entrance", namePrefix: "Main Entrance", numbered: false },
];

// The category is inferred from the facility name so managers never have to
// pick a type manually — it just drives the color-coding on the report page.
function inferCategory(name: string): FacilityCategory {
  const n = name.toLowerCase();
  if (/toilet|restroom|washroom|bathroom|plumbing|pipe|sink|leak/.test(n)) return "PLUMBING";
  if (/lift|elevator/.test(n)) return "LIFT";
  if (/electrical|breaker|wiring|switch room|power/.test(n)) return "ELECTRICAL";
  if (/hvac|aircon|air-con|air con|a\/c|chiller|plant room/.test(n)) return "HVAC";
  if (/entrance|door|access|security|gate|lobby/.test(n)) return "ACCESS";
  return "GENERAL";
}

function makeKey(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2);
}

export default function BuildingSettingsPage() {
  const router = useRouter();
  const [floors, setFloors] = useState<FloorDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!localStorage.getItem("bfa_manager_token")) {
      router.replace("/manager");
      return;
    }
    apiRequest<ApiLayout>("/facilities/layout")
      .then((data) => {
        setFloors(
          data.floors.map((floor) => ({
            key: makeKey(),
            name: floor.name,
            facilities: floor.facilities.map((facility) => ({
              key: makeKey(),
              name: facility.name,
            })),
          })),
        );
      })
      .catch((caught: unknown) => {
        setError(
          caught instanceof Error ? caught.message : "Unable to load the building layout",
        );
      })
      .finally(() => setLoading(false));
  }, [router]);

  function addFloor() {
    setSaved(false);
    setFloors((prev) => [
      ...prev,
      { key: makeKey(), name: `Floor ${prev.length + 1}`, facilities: [] },
    ]);
  }

  function removeFloor(floorKey: string) {
    setSaved(false);
    setFloors((prev) => prev.filter((floor) => floor.key !== floorKey));
  }

  function renameFloor(floorKey: string, name: string) {
    setSaved(false);
    setFloors((prev) =>
      prev.map((floor) => (floor.key === floorKey ? { ...floor, name } : floor)),
    );
  }

  function addFacility(floorKey: string, name: string) {
    setSaved(false);
    setFloors((prev) =>
      prev.map((floor) =>
        floor.key === floorKey
          ? { ...floor, facilities: [...floor.facilities, { key: makeKey(), name }] }
          : floor,
      ),
    );
  }

  function addPreset(floorKey: string, preset: (typeof PRESETS)[number]) {
    const floor = floors.find((f) => f.key === floorKey);
    if (!floor) return;
    let name = preset.namePrefix;
    if (preset.numbered) {
      const pattern = new RegExp(`^${preset.namePrefix} \\d+$`, "i");
      const count = floor.facilities.filter((f) => pattern.test(f.name.trim())).length;
      name = `${preset.namePrefix} ${count + 1}`;
    }
    addFacility(floorKey, name);
  }

  function removeFacility(floorKey: string, facilityKey: string) {
    setSaved(false);
    setFloors((prev) =>
      prev.map((floor) =>
        floor.key === floorKey
          ? { ...floor, facilities: floor.facilities.filter((f) => f.key !== facilityKey) }
          : floor,
      ),
    );
  }

  function renameFacility(floorKey: string, facilityKey: string, name: string) {
    setSaved(false);
    setFloors((prev) =>
      prev.map((floor) =>
        floor.key === floorKey
          ? {
              ...floor,
              facilities: floor.facilities.map((f) =>
                f.key === facilityKey ? { ...f, name } : f,
              ),
            }
          : floor,
      ),
    );
  }

  async function save() {
    setBusy(true);
    setError("");
    setSaved(false);
    const payload = {
      floors: floors
        .map((floor) => ({
          name: floor.name.trim(),
          facilities: floor.facilities
            .filter((facility) => facility.name.trim())
            .map((facility) => ({
              name: facility.name.trim(),
              category: inferCategory(facility.name),
            })),
        }))
        .filter((floor) => floor.name),
    };
    try {
      const data = await apiRequest<ApiLayout>("/facilities/layout", {
        method: "PUT",
        headers: { ...managerHeaders(), "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setFloors(
        data.floors.map((floor) => ({
          key: makeKey(),
          name: floor.name,
          facilities: floor.facilities.map((facility) => ({
            key: makeKey(),
            name: facility.name,
          })),
        })),
      );
      setSaved(true);
    } catch (caught) {
      const message =
        caught instanceof Error ? caught.message : "Unable to save the building layout";
      setError(message);
      if (message.includes("token")) router.replace("/manager");
    } finally {
      setBusy(false);
    }
  }

  function signOut() {
    localStorage.removeItem("bfa_manager_token");
    router.push("/manager");
  }

  return (
    <section className="card">
      <div className="actions">
        <h1>Building setup</h1>
        <Link className="button-link button-secondary" href="/manager/dashboard">
          Incident queue
        </Link>
        <button onClick={signOut}>Sign out</button>
      </div>
      <p className="lede">
        Define the floors in your building and the facilities on each one
        (toilets, offices, lift lobbies, plant rooms, and so on). Just name
        each facility — its type is detected automatically from the name.
        The floor list below matches the building map top to bottom, so add
        your topmost floor first and the ground floor last.
      </p>

      {error && <div className="notice error">{error}</div>}
      {saved && <div className="notice success">Building layout saved.</div>}

      {loading ? (
        <p>Loading...</p>
      ) : (
        <>
          {floors.length === 0 && (
            <p className="lede">
              No floors yet. Click &ldquo;Add floor&rdquo; to get started.
            </p>
          )}

          {floors.map((floor) => (
            <div className="floor-editor" key={floor.key}>
              <div className="floor-editor-header">
                <input
                  aria-label="Floor name"
                  value={floor.name}
                  maxLength={120}
                  onChange={(event) => renameFloor(floor.key, event.target.value)}
                />
                <button
                  type="button"
                  className="button-danger"
                  onClick={() => removeFloor(floor.key)}
                >
                  Remove floor
                </button>
              </div>

              {floor.facilities.map((facility) => (
                <div className="facility-row" key={facility.key}>
                  <input
                    aria-label="Facility name"
                    value={facility.name}
                    maxLength={120}
                    onChange={(event) =>
                      renameFacility(floor.key, facility.key, event.target.value)
                    }
                  />
                  <button
                    type="button"
                    className="button-danger"
                    onClick={() => removeFacility(floor.key, facility.key)}
                  >
                    Remove
                  </button>
                </div>
              ))}

              <div className="quick-add">
                {PRESETS.map((preset) => (
                  <button
                    type="button"
                    key={preset.label}
                    onClick={() => addPreset(floor.key, preset)}
                  >
                    {preset.label}
                  </button>
                ))}
                <button type="button" onClick={() => addFacility(floor.key, "")}>
                  + Custom facility
                </button>
              </div>
            </div>
          ))}

          <div className="actions">
            <button type="button" className="button-secondary" onClick={addFloor}>
              Add floor
            </button>
            <button type="button" disabled={busy} onClick={() => void save()}>
              {busy ? "Saving..." : "Save layout"}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
