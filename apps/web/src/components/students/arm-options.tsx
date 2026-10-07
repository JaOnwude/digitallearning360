"use client";

import { useSetupSetupOverview } from "@dl360/api-client";

/** Arms of the active session as <option>s, grouped by section ("JSS1 A", ...). */
export function ArmOptions() {
  const overview = useSetupSetupOverview();
  return (
    <>
      {overview.data?.data.sections.map((section) => (
        <optgroup key={section.id} label={section.display_name}>
          {section.levels.flatMap((level) =>
            level.arms.map((arm) => (
              <option key={arm.id} value={arm.id}>
                {level.name} {arm.name}
              </option>
            )),
          )}
        </optgroup>
      ))}
    </>
  );
}

export function HouseOptions() {
  const overview = useSetupSetupOverview();
  return (
    <>
      {overview.data?.data.houses.map((h) => (
        <option key={h.id} value={h.id}>
          {h.name}
        </option>
      ))}
    </>
  );
}
