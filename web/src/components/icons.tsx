// Minimal inline icon set (lucide-style, 1.6 stroke, currentColor).
import type { ReactNode, SVGProps } from 'react';

type P = SVGProps<SVGSVGElement> & { size?: number };
function svg(path: ReactNode, viewBox = '0 0 24 24') {
  return function Icon({ size = 16, ...rest }: P) {
    return (
      <svg
        width={size}
        height={size}
        viewBox={viewBox}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.6}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        {...rest}
      >
        {path}
      </svg>
    );
  };
}

export const SearchIcon = svg(
  <>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.2-3.2" />
  </>,
);
export const GridIcon = svg(
  <>
    <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
    <rect x="13.5" y="3.5" width="7" height="7" rx="1.5" />
    <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
    <rect x="13.5" y="13.5" width="7" height="7" rx="1.5" />
  </>,
);
export const LayersIcon = svg(
  <>
    <path d="M12 3 3 8l9 5 9-5-9-5Z" />
    <path d="m3 13 9 5 9-5" />
  </>,
);
export const PlusIcon = svg(<path d="M12 5v14M5 12h14" />);
export const ChevronRightIcon = svg(<path d="m9 6 6 6-6 6" />);
export const ChevronUpIcon = svg(<path d="m6 15 6-6 6 6" />);
export const ChevronDownIcon = svg(<path d="m6 9 6 6 6-6" />);
export const CheckIcon = svg(<path d="M5 12.5 10 17l9-10" />);
export const XIcon = svg(<path d="M6 6l12 12M18 6 6 18" />);
export const ArrowRightIcon = svg(<path d="M5 12h14m-6-6 6 6-6 6" />);
export const TargetIcon = svg(
  <>
    <circle cx="12" cy="12" r="8.5" />
    <circle cx="12" cy="12" r="3.2" />
  </>,
);
export const DiamondIcon = svg(<path d="M12 3 21 12l-9 9-9-9 9-9Z" />);
export const CodeIcon = svg(<path d="m8 7-5 5 5 5M16 7l5 5-5 5" />);
export const FlaskIcon = svg(
  <>
    <path d="M9 3h6M10 3v6.5L5 18a1.5 1.5 0 0 0 1.3 2.3h11.4A1.5 1.5 0 0 0 19 18l-5-8.5V3" />
    <path d="M7.5 14h9" />
  </>,
);
export const TakeoverIcon = svg(
  <>
    <path d="M8 5v14M16 5v14" />
  </>,
);
export const EditIcon = svg(
  <>
    <path d="M4 20h4L19 9l-4-4L4 16v4Z" />
    <path d="m13.5 6.5 4 4" />
  </>,
);
export const ClockIcon = svg(
  <>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 2" />
  </>,
);
export const PlayIcon = svg(<path d="M8 5.5v13l10-6.5-10-6.5Z" />);
export const AlertIcon = svg(
  <>
    <path d="M12 3.5 21 19H3L12 3.5Z" />
    <path d="M12 10v4" />
    <path d="M12 17h.01" />
  </>,
);
export const NoEntryIcon = svg(
  <>
    <circle cx="12" cy="12" r="8.5" />
    <path d="m6.4 6.4 11.2 11.2" />
  </>,
);
