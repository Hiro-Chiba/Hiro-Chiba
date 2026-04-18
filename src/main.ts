import { parseArgs } from "jsr:@std/cli/parse-args";
import { LANGUAGE_COLORS, DEFAULT_COLOR } from "./language-colors.ts";

// --- CLI ---

const args = parseArgs(Deno.args, {
  string: ["token", "excluded-languages", "output-dir", "min-percentage"],
  default: { "output-dir": "output", "min-percentage": "0.1" },
});

const token = args.token ?? Deno.env.get("REPOSCOPE_TOKEN");
if (!token) {
  console.error("Error: --token or REPOSCOPE_TOKEN env var required");
  Deno.exit(1);
}

const excludedLanguages = new Set(
  (args["excluded-languages"] ?? Deno.env.get("EXCLUDED_LANGUAGES") ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean),
);

const outputDir = args["output-dir"];
const minPercentage = parseFloat(args["min-percentage"]);

// --- GitHub API ---

const API_BASE = "https://api.github.com";
const headers = {
  Authorization: `Bearer ${token}`,
  Accept: "application/vnd.github+json",
  "X-GitHub-Api-Version": "2022-11-28",
};

interface Repo {
  full_name: string;
  fork: boolean;
}

async function fetchAllRepos(): Promise<Repo[]> {
  const repos: Repo[] = [];
  let url: string | null =
    `${API_BASE}/user/repos?visibility=all&affiliation=owner&per_page=100`;

  while (url) {
    const res = await fetch(url, { headers });
    if (!res.ok) {
      throw new Error(`GitHub API error: ${res.status} ${await res.text()}`);
    }
    const data: Repo[] = await res.json();
    repos.push(...data.filter((r) => !r.fork));

    const link = res.headers.get("Link");
    const next = link?.match(/<([^>]+)>;\s*rel="next"/);
    url = next ? next[1] : null;
  }
  return repos;
}

async function fetchRepoLanguages(
  fullName: string,
): Promise<Record<string, number>> {
  const res = await fetch(`${API_BASE}/repos/${fullName}/languages`, {
    headers,
  });
  if (!res.ok) return {};
  return res.json();
}

interface LanguageStat {
  name: string;
  bytes: number;
  percentage: number;
  color: string;
}

async function aggregateLanguages(): Promise<LanguageStat[]> {
  console.log("Fetching repositories...");
  const repos = await fetchAllRepos();
  console.log(`Found ${repos.length} repositories (excluding forks)`);

  const totals: Record<string, number> = {};

  // Batch fetch language data (10 concurrent)
  for (let i = 0; i < repos.length; i += 10) {
    const batch = repos.slice(i, i + 10);
    const results = await Promise.all(
      batch.map((r) => fetchRepoLanguages(r.full_name)),
    );
    for (const langs of results) {
      for (const [lang, bytes] of Object.entries(langs)) {
        if (!excludedLanguages.has(lang)) {
          totals[lang] = (totals[lang] ?? 0) + bytes;
        }
      }
    }
  }

  const totalBytes = Object.values(totals).reduce((a, b) => a + b, 0);
  if (totalBytes === 0) return [];

  const all = Object.entries(totals)
    .map(([name, bytes]) => ({
      name,
      bytes,
      percentage: (bytes / totalBytes) * 100,
      color: LANGUAGE_COLORS[name] ?? DEFAULT_COLOR,
    }))
    .sort((a, b) => b.bytes - a.bytes);

  // Split into visible languages and "Other" (below threshold)
  const visible = all.filter((l) => l.percentage >= minPercentage);
  const otherPct = all
    .filter((l) => l.percentage < minPercentage)
    .reduce((s, l) => s + l.percentage, 0);

  visible.push({
    name: "Other",
    bytes: 0,
    percentage: otherPct,
    color: DEFAULT_COLOR,
  });

  return visible;
}

// --- SVG: Shared styles ---

function sharedStyles(): string {
  return `
    @media (prefers-color-scheme: light) {
      .bg { fill: #ffffff; }
      .text-primary { fill: #1f2328; }
      .text-secondary { fill: #656d76; }
      .bar-bg { fill: #d1d9e0; }
      .border { stroke: #d1d9e0; }
    }
    @media (prefers-color-scheme: dark) {
      .bg { fill: #0d1117; }
      .text-primary { fill: #ffffff; }
      .text-secondary { fill: #9198a1; }
      .bar-bg { fill: #30363d; }
      .border { stroke: #30363d; }
    }
    text {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif;
    }
    @keyframes fadeIn {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    @keyframes slideIn {
      from { transform: scaleX(0); }
      to { transform: scaleX(1); }
    }
  `;
}

// --- Design A: GitHub Native ---

function generateDesignA(languages: LanguageStat[]): string {
  const top = languages.slice(0, 8);
  const width = 480;
  const barY = 52;
  const barHeight = 8;
  const legendStartY = 80;
  const rowHeight = 22;
  const cols = 3;
  const rows = Math.ceil(top.length / cols);
  const height = legendStartY + rows * rowHeight + 20;
  const barWidth = width - 48;

  let barX = 24;
  const barSegments = top
    .map((lang) => {
      const segWidth = Math.max((lang.percentage / 100) * barWidth, 1);
      const segment =
        `<rect x="${barX.toFixed(1)}" y="${barY}" width="${segWidth.toFixed(1)}" height="${barHeight}" fill="${lang.color}"><title>${lang.name} ${lang.percentage.toFixed(2)}%</title></rect>`;
      barX += segWidth;
      return segment;
    })
    .join("\n      ");

  const legendEntries = top
    .map((lang, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      const x = 24 + col * 152;
      const y = legendStartY + row * rowHeight;
      return `<g style="animation: fadeIn 0.4s ease ${0.3 + i * 0.04}s both">
        <circle cx="${x}" cy="${y}" r="4" fill="${lang.color}" />
        <text x="${x + 10}" y="${y + 4}" font-size="11.5" class="text-primary">
          <tspan font-weight="500">${lang.name}</tspan>
          <tspan class="text-secondary"> ${lang.percentage.toFixed(1)}%</tspan>
        </text>
      </g>`;
    })
    .join("\n      ");

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg">
  <style>${sharedStyles()}</style>
  <rect class="bg border" width="${width}" height="${height}" rx="10" stroke-width="1" />
  <text class="text-primary" x="24" y="32" font-size="14" font-weight="600"
        style="animation: fadeIn 0.3s ease both">Most Used Languages</text>
  <defs>
    <clipPath id="barClipA">
      <rect x="24" y="${barY}" width="${barWidth}" height="${barHeight}" rx="4" />
    </clipPath>
  </defs>
  <rect class="bar-bg" x="24" y="${barY}" width="${barWidth}" height="${barHeight}" rx="4" />
  <g clip-path="url(#barClipA)" style="animation: slideIn 0.6s ease 0.15s both; transform-origin: 24px ${barY}px">
      ${barSegments}
  </g>
      ${legendEntries}
</svg>`;
}

// --- Design B: Compact Donut (horizontal layout) ---

function formatPct(pct: number): string {
  if (pct >= 0.1) return `${pct.toFixed(1)}%`;
  return "&lt;0.1%";
}

function generateDesignB(languages: LanguageStat[]): string {
  // languages already includes "Other" from aggregation if applicable
  const allSegments = languages;
  const totalLanguages = allSegments.filter((l) => l.name !== "Other").length;
  const width = 520;
  const r = 65;
  const strokeWidth = 22;
  const circumference = 2 * Math.PI * r;
  const donutCx = 110;
  const donutCy = 110;
  const listStartY = 30;
  const listRowHeight = 26;
  const listBottom = listStartY + allSegments.length * listRowHeight;
  const donutBottom = donutCy + r + strokeWidth / 2;
  const height = Math.max(donutBottom, listBottom) + 20;

  // Background ring for donut guide
  const bgRing = `<circle cx="${donutCx}" cy="${donutCy}" r="${r}"
    fill="none" class="bar-bg" stroke-width="${strokeWidth}" />`;

  let offset = 0;
  const segments = allSegments
    .map((lang, i) => {
      const dashLen = Math.max((lang.percentage / 100) * circumference, 0.5);
      const rotation = -90 + (offset / circumference) * 360;
      offset += (lang.percentage / 100) * circumference;
      return `<circle cx="${donutCx}" cy="${donutCy}" r="${r}"
        fill="none" stroke="${lang.color}" stroke-width="${strokeWidth}"
        stroke-dasharray="${dashLen.toFixed(1)} ${(circumference - dashLen).toFixed(1)}"
        transform="rotate(${rotation.toFixed(2)} ${donutCx} ${donutCy})"
        style="animation: fadeIn 0.4s ease ${(0.10 + i * 0.06).toFixed(2)}s both">
        <title>${lang.name} ${lang.percentage.toFixed(2)}%</title>
      </circle>`;
    })
    .join("\n    ");

  // Right-side legend with horizontal bars (log scale for visibility)
  const listX = 230;
  const barMaxW = 120;
  const maxLogPct = Math.log10(Math.max(...allSegments.map((l) => l.percentage)) + 1);

  const listEntries = allSegments
    .map((lang, i) => {
      const y = listStartY + i * listRowHeight;
      const logBarW = Math.max((Math.log10(lang.percentage + 1) / maxLogPct) * barMaxW, 4);
      return `<g style="animation: fadeIn 0.4s ease ${(0.30 + i * 0.05).toFixed(2)}s both">
        <circle cx="${listX}" cy="${y + 7}" r="4" fill="${lang.color}" />
        <text x="${listX + 12}" y="${y + 11}" font-size="12" font-weight="500" class="text-primary">${lang.name}</text>
        <rect x="${listX + 100}" y="${y + 1}" width="${logBarW.toFixed(1)}" height="12" rx="3" fill="${lang.color}" />
        <text x="${listX + 100 + logBarW + 8}" y="${y + 11}" font-size="11" class="text-secondary">${formatPct(lang.percentage)}</text>
      </g>`;
    })
    .join("\n    ");

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg">
  <style>${sharedStyles()}</style>
  <rect class="bg border" width="${width}" height="${height}" rx="12" stroke-width="1" />
    ${bgRing}
    ${segments}
  <text x="${donutCx}" y="${donutCy - 4}" text-anchor="middle" class="text-primary" font-size="24" font-weight="700"
        style="animation: fadeIn 0.4s ease 0.20s both">${totalLanguages}</text>
  <text x="${donutCx}" y="${donutCy + 14}" text-anchor="middle" class="text-secondary" font-size="11"
        style="animation: fadeIn 0.4s ease 0.30s both">Languages</text>
    ${listEntries}
</svg>`;
}

// --- Design C: Gradient Donut ---

function generateDesignC(languages: LanguageStat[]): string {
  const maxLangs = 6;
  const top = languages.slice(0, maxLangs);
  const otherPct = languages.slice(maxLangs).reduce((s, l) => s + l.percentage, 0);
  const allSegments = otherPct > 0.01
    ? [...top, { name: "Other", bytes: 0, percentage: otherPct, color: DEFAULT_COLOR }]
    : top;

  const totalLanguages = languages.length;
  const width = 420;
  const r = 80;
  const strokeWidth = 24;
  const circumference = 2 * Math.PI * r;
  const cx = width / 2;
  const cy = 140;
  const gap = 3;

  let offset = 0;
  const segments = allSegments
    .map((lang, i) => {
      const dashLen = Math.max((lang.percentage / 100) * circumference - gap, 0.5);
      const rotation = -90 + (offset / circumference) * 360;
      offset += (lang.percentage / 100) * circumference;
      return `<circle cx="${cx}" cy="${cy}" r="${r}"
        fill="none" stroke="${lang.color}" stroke-width="${strokeWidth}"
        stroke-dasharray="${dashLen.toFixed(1)} ${(circumference - dashLen).toFixed(1)}"
        stroke-linecap="round"
        transform="rotate(${rotation.toFixed(1)} ${cx} ${cy})"
        style="animation: fadeIn 0.5s ease ${0.15 + i * 0.08}s both"
        filter="url(#glow)">
        <title>${lang.name} ${lang.percentage.toFixed(2)}%</title>
      </circle>`;
    })
    .join("\n    ");

  // 3-column legend
  const cols = 3;
  const legendStartY = cy + r + strokeWidth / 2 + 28;
  const rowHeight = 28;
  const rows = Math.ceil(allSegments.length / cols);
  const height = legendStartY + rows * rowHeight + 20;
  const colWidth = (width - 40) / cols;

  const legendEntries = allSegments
    .map((lang, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      const x = 28 + col * colWidth;
      const y = legendStartY + row * rowHeight;
      return `<g style="animation: fadeIn 0.4s ease ${0.5 + i * 0.05}s both">
        <rect x="${x - 2}" y="${y - 10}" width="${colWidth - 8}" height="24" rx="6" class="legend-bg" />
        <circle cx="${x + 8}" cy="${y}" r="4.5" fill="${lang.color}" />
        <text x="${x + 18}" y="${y + 4}" font-size="11" class="text-primary">
          <tspan font-weight="600">${lang.name}</tspan>
          <tspan class="text-secondary" font-size="10"> ${lang.percentage.toFixed(1)}%</tspan>
        </text>
      </g>`;
    })
    .join("\n    ");

  return `<?xml version="1.0" encoding="UTF-8"?>
<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bgGrad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" class="grad-start" />
      <stop offset="100%" class="grad-end" />
    </linearGradient>
    <filter id="glow">
      <feGaussianBlur stdDeviation="2" result="blur" />
      <feMerge>
        <feMergeNode in="blur" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>
  </defs>
  <style>
    ${sharedStyles()}
    @media (prefers-color-scheme: dark) {
      .grad-start { stop-color: #0d1117; }
      .grad-end { stop-color: #161b22; }
      .legend-bg { fill: #161b22; stroke: #21262d; stroke-width: 1; }
    }
    @media (prefers-color-scheme: light) {
      .grad-start { stop-color: #ffffff; }
      .grad-end { stop-color: #f6f8fa; }
      .legend-bg { fill: #f6f8fa; stroke: #d1d9e0; stroke-width: 1; }
    }
  </style>
  <rect width="${width}" height="${height}" rx="14" fill="url(#bgGrad)" class="border" stroke-width="1" />
  <text class="text-primary" x="${cx}" y="30" font-size="15" font-weight="700" text-anchor="middle"
        letter-spacing="0.5" style="animation: fadeIn 0.3s ease both">Most Used Languages</text>
    ${segments}
  <text x="${cx}" y="${cy - 4}" text-anchor="middle" class="text-primary" font-size="26" font-weight="700"
        style="animation: fadeIn 0.4s ease 0.2s both">${totalLanguages}</text>
  <text x="${cx}" y="${cy + 14}" text-anchor="middle" class="text-secondary" font-size="11"
        style="animation: fadeIn 0.4s ease 0.3s both">Languages</text>
    ${legendEntries}
</svg>`;
}

// --- Main ---

async function main() {
  const languages = await aggregateLanguages();

  if (languages.length === 0) {
    console.error("No language data found.");
    Deno.exit(1);
  }

  console.log(`Aggregated ${languages.length} languages`);
  for (const lang of languages.slice(0, 10)) {
    console.log(`  ${lang.name}: ${lang.percentage.toFixed(2)}%`);
  }

  await Deno.mkdir(outputDir, { recursive: true });

  const svg = generateDesignB(languages);
  await Deno.writeTextFile(`${outputDir}/full_languages.svg`, svg);

  console.log(`SVG written to ${outputDir}/full_languages.svg`);
}

main();
