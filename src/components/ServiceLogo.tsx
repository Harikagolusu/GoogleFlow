import React from 'react';

/**
 * ServiceLogo renders the ORIGINAL Google brand logos (Gmail, Drive, Calendar,
 * Maps, YouTube, Search, News, Photos, Gemini) as inline SVG.
 *
 * Pass the canonical service name (e.g. "Gmail", "Google Drive", "Drive") —
 * names are normalized so shortened forms like "Drive" / "Maps" / "Search"
 * also resolve to the right logo. Unknown services fall back to the
 * multicolor Google "G".
 */

type LogoRenderer = (gradientId: string) => React.ReactNode;

interface LogoEntry {
  viewBox: string;
  render: LogoRenderer;
}

const LOGOS: Record<string, LogoEntry> = {
  // Gmail — official multicolor envelope logo.
  gmail: {
    viewBox: '0 0 24 24',
    render: () => (
      <>
        <path
          fill="#4285F4"
          d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
        />
        <path
          fill="#34A853"
          d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
        />
        <path
          fill="#FBBC05"
          d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
        />
        <path
          fill="#EA4335"
          d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
        />
      </>
    ),
  },

  // Google Drive — official triangle logo.
  drive: {
    viewBox: '0 0 87.3 78',
    render: () => (
      <>
        <path
          fill="#0066da"
          d="m6.6 66.85 3.85 6.65c.8 1.4 1.95 2.5 3.3 3.3l13.75-23.8h-27.5c0 1.55.4 3.1 1.2 4.5z"
        />
        <path
          fill="#00ac47"
          d="m43.65 25-13.75-23.8c-1.35.8-2.5 1.9-3.3 3.3l-25.4 44a9.06 9.06 0 0 0 -1.2 4.5h27.5z"
        />
        <path
          fill="#ea4335"
          d="m73.55 76.8c1.35-.8 2.5-1.9 3.3-3.3l1.6-2.75 7.65-13.25c.8-1.4 1.2-2.95 1.2-4.5h-27.502l5.852 11.5z"
        />
        <path
          fill="#00832d"
          d="m43.65 25 13.75-23.8c-1.35-.8-2.9-1.2-4.5-1.2h-18.5c-1.6 0-3.15.45-4.5 1.2z"
        />
        <path
          fill="#2684fc"
          d="m59.8 53h-32.3l-13.75 23.8c1.35.8 2.9 1.2 4.5 1.2h50.8c1.6 0 3.15-.45 4.5-1.2z"
        />
        <path
          fill="#ffba00"
          d="m73.4 26.5-12.7-22c-.8-1.4-1.95-2.5-3.3-3.3l-13.75 23.8 16.15 28h27.45c0-1.55-.4-3.1-1.2-4.5z"
        />
      </>
    ),
  },

  // Google Calendar — blue square with the 31 glyph.
  calendar: {
    viewBox: '0 0 24 24',
    render: () => (
      <>
        <rect x="1.2" y="1.2" width="21.6" height="21.6" rx="4.8" fill="#4285F4" />
        <rect
          x="3.05"
          y="3.05"
          width="17.9"
          height="17.9"
          rx="3.4"
          fill="none"
          stroke="#ffffff"
          strokeWidth="1.5"
        />
        <text
          x="12"
          y="16.8"
          textAnchor="middle"
          fontFamily="'Google Sans', Roboto, Arial, sans-serif"
          fontWeight="600"
          fontSize="10.5"
          fill="#ffffff"
        >
          31
        </text>
      </>
    ),
  },

  // Google Maps — blue-to-red gradient location pin.
  maps: {
    viewBox: '0 0 24 24',
    render: (id) => (
      <>
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#1A73E8" />
            <stop offset="0.65" stopColor="#D93025" />
          </linearGradient>
        </defs>
        <path
          fill={`url(#${id})`}
          d="M12 0C7.83 0 4.5 3.33 4.5 7.5c0 5.25 7.5 16.5 7.5 16.5s7.5-11.25 7.5-16.5C19.5 3.33 16.17 0 12 0z"
        />
        <circle cx="12" cy="7.5" r="2.5" fill="#ffffff" />
      </>
    ),
  },

  // YouTube — official red play-button logo.
  youtube: {
    viewBox: '0 0 24 24',
    render: () => (
      <path
        fill="#FF0000"
        d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"
      />
    ),
  },

  // Google Search — multicolor Google "G".
  search: {
    viewBox: '0 0 48 48',
    render: () => (
      <>
        <path
          fill="#EA4335"
          d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
        />
        <path
          fill="#4285F4"
          d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
        />
        <path
          fill="#FBBC05"
          d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
        />
        <path
          fill="#34A853"
          d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
        />
      </>
    ),
  },
  // News — blue square with a colorful newspaper sheet.
  news: {
    viewBox: '0 0 48 48',
    render: () => (
      <>
        <rect x="2" y="2" width="44" height="44" rx="9" fill="#4285F4" />
        <rect x="10" y="10" width="28" height="28" rx="4" fill="#ffffff" />
        <rect x="14" y="16" width="20" height="4" rx="2" fill="#4285F4" />
        <rect x="14" y="23.5" width="14" height="4" rx="2" fill="#EA4335" />
        <rect x="14" y="31" width="11" height="4" rx="2" fill="#FBBC05" />
        <circle cx="31.5" cy="33" r="4" fill="#34A853" />
      </>
    ),
  },

  // Google Photos — the four-color pinwheel.
  photos: {
    viewBox: '0 0 48 48',
    render: () => (
      <>
        <path
          fill="#FBBB04"
          d="M46 24a22 22 0 0 0-22-22v10a12 12 0 0 1 12 12h10z"
        />
        <path
          fill="#E94235"
          d="M24 2a22 22 0 0 0-22 22h10a12 12 0 0 1 12-12V2z"
        />
        <path
          fill="#34A853"
          d="M46 24h-10a12 12 0 0 0-12 12v10a22 22 0 0 0 22-22z"
        />
        <path
          fill="#4285F4"
          d="M2 24h10a12 12 0 0 0 12 12v10a22 22 0 0 1-22-22z"
        />
      </>
    ),
  },

  // Gemini — blue-violet four-point sparkle.
  gemini: {
    viewBox: '0 0 24 24',
    render: (id) => (
      <>
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#4A7CF7" />
            <stop offset="1" stopColor="#7C6BF5" />
          </linearGradient>
        </defs>
        <path
          fill={`url(#${id})`}
          d="M12 2c1.5 4.8 5.2 8.5 10 10-4.8 1.5-8.5 5.2-10 10-1.5-4.8-5.2-8.5-10-10 4.8-1.5 8.5-5.2 10-10Z"
        />
      </>
    ),
  },
};

// Any unknown service falls back to the multicolor Google "G".
const DEFAULT_LOGO_KEY = 'search';

function normalizeKey(name: string): string {
  return name
    .toLowerCase()
    .replace(/^googles?\s+/, '')
    .trim();
}

export const ServiceLogo: React.FC<{
  name: string;
  className?: string;
}> = ({ name, className }) => {
  const key = normalizeKey(name);
  const entry = LOGOS[key] ?? LOGOS[DEFAULT_LOGO_KEY];
  // Unique id per instance so gradient refs never collide when the same logo
  // is rendered multiple times on a page.
  const gradientId = React.useId().replace(/:/g, '');

  return (
    <svg viewBox={entry.viewBox} className={className} role="img" aria-label={name}>
      {entry.render(gradientId)}
    </svg>
  );
};