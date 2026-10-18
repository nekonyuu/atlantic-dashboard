// Icônes au trait (24×24, currentColor), dessinées pour ce dashboard.
import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 18, children, ...rest }: P) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      {...rest}
    >
      {children}
    </svg>
  );
}

export const IconHome = (p: P) => (
  <Svg {...p}>
    <path d="M3 10.5 12 3l9 7.5" />
    <path d="M5 9.5V20h14V9.5" />
    <path d="M10 20v-5h4v5" />
  </Svg>
);
export const IconDrop = (p: P) => (
  <Svg {...p}>
    <path d="M12 3s6 6.4 6 11a6 6 0 0 1-12 0c0-4.6 6-11 6-11Z" />
  </Svg>
);
export const IconFlame = (p: P) => (
  <Svg {...p}>
    <path d="M12 21a6.5 6.5 0 0 0 6.5-6.5c0-4.5-4-6.5-4.5-10.5-2 1.5-3 3.5-3 5.5-1-.5-2-1.8-2-3.2C7.2 8.3 5.5 11 5.5 14.5A6.5 6.5 0 0 0 12 21Z" />
  </Svg>
);
export const IconChart = (p: P) => (
  <Svg {...p}>
    <path d="M4 20V4" />
    <path d="M4 20h16" />
    <path d="m7 15 4-4 3 3 5-6" />
  </Svg>
);
export const IconBolt = (p: P) => (
  <Svg {...p}>
    <path d="M13 3 5 13.5h6L10 21l8-10.5h-6L13 3Z" />
  </Svg>
);
export const IconThermo = (p: P) => (
  <Svg {...p}>
    <path d="M14 14.8V5a2 2 0 1 0-4 0v9.8a4 4 0 1 0 4 0Z" />
    <path d="M12 9v7" />
  </Svg>
);
export const IconOutdoor = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="3.5" />
    <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4" />
  </Svg>
);
export const IconGauge = (p: P) => (
  <Svg {...p}>
    <path d="M4.5 17a8.5 8.5 0 1 1 15 0" />
    <path d="m12 13 3.5-4" />
    <circle cx="12" cy="13" r="1.2" />
  </Svg>
);
export const IconPump = (p: P) => (
  <Svg {...p}>
    <rect x="3" y="5" width="18" height="14" rx="3" />
    <circle cx="9" cy="12" r="3.2" />
    <path d="M9 8.8v6.4M5.8 12h6.4M15 9h3M15 12h3M15 15h3" />
  </Svg>
);
export const IconWave = (p: P) => (
  <Svg {...p}>
    <path d="M3 9c2.5-2 4.5-2 7 0s4.5 2 7 0 3.5-1.5 4-1" />
    <path d="M3 15c2.5-2 4.5-2 7 0s4.5 2 7 0 3.5-1.5 4-1" />
  </Svg>
);
export const IconAlert = (p: P) => (
  <Svg {...p}>
    <path d="M12 4 2.8 19.5h18.4L12 4Z" />
    <path d="M12 10v4.5M12 17.2v.1" />
  </Svg>
);
export const IconCheck = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="m8.3 12.3 2.4 2.4 5-5.2" />
  </Svg>
);
export const IconOff = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="m9 9 6 6M15 9l-6 6" />
  </Svg>
);
export const IconClock = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 2" />
  </Svg>
);
export const IconTable = (p: P) => (
  <Svg {...p}>
    <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
    <path d="M3.5 9.5h17M3.5 14.5h17M9.5 9.5v10" />
  </Svg>
);
export const IconSun = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4" />
  </Svg>
);
export const IconMoon = (p: P) => (
  <Svg {...p}>
    <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z" />
  </Svg>
);
export const IconAuto = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 3.5v17a8.5 8.5 0 0 0 0-17Z" fill="currentColor" stroke="none" />
  </Svg>
);
