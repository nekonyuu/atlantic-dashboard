import { describe, expect, it } from "vitest";

import { formatAge, formatAxisTime, formatDuration, formatTick, formatValue, translateEnum } from "./format";

describe("format", () => {
  it("formate les âges en français", () => {
    expect(formatAge(30)).toBe("à l'instant");
    expect(formatAge(180)).toBe("il y a 3 min");
    expect(formatAge(2 * 3600 + 300)).toBe("il y a 2 h 05");
    expect(formatAge(3 * 86400)).toBe("il y a 3 j");
  });

  it("formate les durées", () => {
    expect(formatDuration(7 * 3600)).toBe("7 h 00");
    expect(formatDuration(600)).toBe("10 min");
  });

  it("traduit les libellés d'enum et formate les valeurs", () => {
    expect(translateEnum("Heat")).toBe("Chauffage");
    expect(translateEnum("Inconnu")).toBe("Inconnu");
    expect(formatValue(1, null, "No")).toBe("Non");
    expect(formatValue(true, null, null)).toBe("Oui");
    expect(formatValue(null, "°C", null)).toBe("—");
    expect(formatValue(53.17, "°C", null).replace(/\s/g, " ")).toBe("53,2 °C");
  });

  it("adapte la précision des graduations au pas", () => {
    expect(formatTick(1.375, 0.025, "bar").replace(/\s/g, " ")).toBe("1,38 bar");
    expect(formatTick(20, 5, "°C").replace(/\s/g, " ")).toBe("20 °C");
  });

  it("graduations de temps : heure, puis date à minuit et au-delà d'un jour", () => {
    const midnightParis = Date.UTC(2026, 9, 17, 22) / 1000; // 18/10 00:00 à Paris
    expect(formatAxisTime(midnightParis, 3600)).toBe("18/10");
    expect(formatAxisTime(midnightParis + 6 * 3600, 3600)).toBe("06:00");
    expect(formatAxisTime(midnightParis + 6 * 3600, 86400)).toBe("18/10");
  });
});
