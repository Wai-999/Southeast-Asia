/**
 * frontend/data/countries.ts
 * ───────────────────────────
 * Complete country registry for the SEA Change Intelligence Dashboard.
 *
 * Covers:
 *   11 Southeast Asian countries  (SEA_COUNTRIES)
 *    7 partner/external entities  (PARTNER_COUNTRIES)
 *   18 total                      (ALL_COUNTRIES)
 *
 * This file is the single source of truth for country metadata in the
 * frontend. It is separate from sample-data.ts (which holds indicator
 * values for the 5 active countries) so that country lists and filters
 * can reference all 18 entities without breaking indicator logic.
 *
 * SOURCE: pipeline/output/json/countries.json (v2.0)
 * Refresh: update that JSON, then mirror changes here.
 */

import type { RiskLevel } from "@/lib/utils";

// ─────────────────────────────────────────────────────────────────────────────
// TYPES
// ─────────────────────────────────────────────────────────────────────────────

export type RegionGroup =
  | "Southeast Asia"
  | "East Asia"
  | "South Asia"
  | "Oceania"
  | "Americas"
  | "Europe";

export type SubRegion =
  | "Mainland SEA"
  | "Maritime SEA"
  | "East Asia"
  | "South Asia"
  | "Oceania"
  | "North America"
  | "Europe";

export type AseanStatus = "full" | "candidate" | "observer" | "none";

export type DataQuality = "excellent" | "good" | "fair" | "poor";

export interface DashboardCountry {
  /** ISO 3166-1 alpha-3 — dashboard primary key */
  iso3: string;
  /** ISO 3166-1 alpha-2 */
  iso2: string;
  /** World Bank API code (use in /v2/country/{wbCode}/indicator/...) */
  wbCode: string;
  /** Official English name */
  name: string;
  /** Shorter display name for chips/tables */
  shortName: string;
  /** Unicode flag emoji */
  flagEmoji: string;
  /** Capital city */
  capital: string;
  /** ISO 4217 currency code */
  currencyCode: string;
  /** Common currency name */
  currencyName: string;
  /** Top-level filter group */
  regionGroup: RegionGroup;
  /** Finer geographic sub-group */
  subRegion: SubRegion;
  /** True for Southeast Asian countries */
  isSea: boolean;
  /** True for external partner/observer entities */
  isPartner: boolean;
  /** True if this is a multi-country bloc (EU only) */
  isBloc: boolean;
  /** Full ASEAN membership */
  aseanMember: boolean;
  /** ASEAN membership status */
  aseanStatus: AseanStatus;
  /** Sort order (1 = highest priority, shown first) */
  defaultPriority: number;
  /** Appears in main indicator charts by default */
  dashboardActive: boolean;
  /** Full 8-indicator sample data exists in sample-data.ts */
  indicatorDataAvailable: boolean;
  /** Data reliability — used by AI confidence levels */
  dataQuality: DataQuality;
  /** Latest population estimate (millions) */
  populationMillions: number;
  /** Latest GDP in current USD (billions) */
  gdpNominalUsdB: number;
  /** Top-3 export product groups */
  mainExports: string[];
  /** Top-3 import partner countries */
  mainImportPartners: string[];
  /** Brief analyst notes */
  notes: string;
  /** Risk level — computed for active countries, estimated for others */
  riskLevel?: RiskLevel;
}


// ─────────────────────────────────────────────────────────────────────────────
// COUNTRY DATA  (18 entries — 11 SEA + 7 partners)
// ─────────────────────────────────────────────────────────────────────────────

export const ALL_COUNTRIES: DashboardCountry[] = [

  // ── Southeast Asia — Mainland ───────────────────────────────────────────────

  {
    iso3: "THA", iso2: "TH", wbCode: "TH",
    name: "Thailand", shortName: "Thailand", flagEmoji: "🇹🇭",
    capital: "Bangkok", currencyCode: "THB", currencyName: "Thai Baht",
    regionGroup: "Southeast Asia", subRegion: "Mainland SEA",
    isSea: true, isPartner: false, isBloc: false,
    aseanMember: true, aseanStatus: "full",
    defaultPriority: 1, dashboardActive: true, indicatorDataAvailable: true,
    dataQuality: "good", populationMillions: 70.8, gdpNominalUsdB: 514.9,
    riskLevel: "medium",
    mainExports: ["Vehicles & parts", "Electronics", "Rubber products"],
    mainImportPartners: ["China", "Japan", "United States"],
    notes: "Upper-middle income. Key auto hub. EEC FDI zone. Political risk from recurring military interventions. Tourism-reliant services sector.",
  },

  {
    iso3: "VNM", iso2: "VN", wbCode: "VN",
    name: "Vietnam", shortName: "Vietnam", flagEmoji: "🇻🇳",
    capital: "Hanoi", currencyCode: "VND", currencyName: "Vietnamese Đồng",
    regionGroup: "Southeast Asia", subRegion: "Mainland SEA",
    isSea: true, isPartner: false, isBloc: false,
    aseanMember: true, aseanStatus: "full",
    defaultPriority: 2, dashboardActive: true, indicatorDataAvailable: true,
    dataQuality: "good", populationMillions: 97.3, gdpNominalUsdB: 433.2,
    riskLevel: "low",
    mainExports: ["Electronics & components", "Textiles & footwear", "Machinery"],
    mainImportPartners: ["China", "South Korea", "Japan"],
    notes: "Fast-growing FDI magnet for electronics supply chains. Large US trade surplus creates tariff risk. EVFTA with EU in force.",
  },

  {
    iso3: "MMR", iso2: "MM", wbCode: "MM",
    name: "Myanmar", shortName: "Myanmar", flagEmoji: "🇲🇲",
    capital: "Naypyidaw", currencyCode: "MMK", currencyName: "Burmese Kyat",
    regionGroup: "Southeast Asia", subRegion: "Mainland SEA",
    isSea: true, isPartner: false, isBloc: false,
    aseanMember: true, aseanStatus: "full",
    defaultPriority: 7, dashboardActive: true, indicatorDataAvailable: true,
    dataQuality: "poor", populationMillions: 54.4, gdpNominalUsdB: 65.0,
    riskLevel: "critical",
    mainExports: ["Natural gas", "Jade & gems", "Rice"],
    mainImportPartners: ["China", "Thailand", "Singapore"],
    notes: "POST-COUP CRISIS (Feb 2021). GDP contracted. Hyperinflation, currency collapse, FDI exit. Post-2021 statistics from IMF estimates only.",
  },

  {
    iso3: "KHM", iso2: "KH", wbCode: "KH",
    name: "Cambodia", shortName: "Cambodia", flagEmoji: "🇰🇭",
    capital: "Phnom Penh", currencyCode: "KHR", currencyName: "Cambodian Riel",
    regionGroup: "Southeast Asia", subRegion: "Mainland SEA",
    isSea: true, isPartner: false, isBloc: false,
    aseanMember: true, aseanStatus: "full",
    defaultPriority: 8, dashboardActive: true, indicatorDataAvailable: true,
    dataQuality: "fair", populationMillions: 16.7, gdpNominalUsdB: 30.1,
    riskLevel: "high",
    mainExports: ["Garments & textiles", "Footwear", "Rice"],
    mainImportPartners: ["China", "Vietnam", "Thailand"],
    notes: "Garment-dependent economy. EU GSP preference pressure. High current-account deficit. Highly dollarised — limited independent monetary policy.",
  },

  {
    iso3: "LAO", iso2: "LA", wbCode: "LA",
    name: "Laos", shortName: "Laos", flagEmoji: "🇱🇦",
    capital: "Vientiane", currencyCode: "LAK", currencyName: "Lao Kip",
    regionGroup: "Southeast Asia", subRegion: "Mainland SEA",
    isSea: true, isPartner: false, isBloc: false,
    aseanMember: true, aseanStatus: "full",
    defaultPriority: 9, dashboardActive: false, indicatorDataAvailable: false,
    dataQuality: "fair", populationMillions: 7.4, gdpNominalUsdB: 14.0,
    riskLevel: "critical",
    mainExports: ["Hydropower electricity", "Copper", "Gold"],
    mainImportPartners: ["Thailand", "China", "Vietnam"],
    notes: "DEBT DISTRESS: Government debt >100% GDP. Kip lost >50% vs USD since 2021. IMF-flagged for restructuring. China-Laos Railway opened 2021.",
  },

  // ── Southeast Asia — Maritime ────────────────────────────────────────────────

  {
    iso3: "SGP", iso2: "SG", wbCode: "SG",
    name: "Singapore", shortName: "Singapore", flagEmoji: "🇸🇬",
    capital: "Singapore", currencyCode: "SGD", currencyName: "Singapore Dollar",
    regionGroup: "Southeast Asia", subRegion: "Maritime SEA",
    isSea: true, isPartner: false, isBloc: false,
    aseanMember: true, aseanStatus: "full",
    defaultPriority: 3, dashboardActive: true, indicatorDataAvailable: true,
    dataQuality: "excellent", populationMillions: 5.9, gdpNominalUsdB: 501.4,
    riskLevel: "low",
    mainExports: ["Electronics", "Financial services", "Petroleum products"],
    mainImportPartners: ["China", "Malaysia", "United States"],
    notes: "City-state hub. World's largest FDI per capita. Re-export centre distorts trade statistics. MAS uses exchange rate band as primary monetary tool.",
  },

  {
    iso3: "IDN", iso2: "ID", wbCode: "ID",
    name: "Indonesia", shortName: "Indonesia", flagEmoji: "🇮🇩",
    capital: "Jakarta", currencyCode: "IDR", currencyName: "Indonesian Rupiah",
    regionGroup: "Southeast Asia", subRegion: "Maritime SEA",
    isSea: true, isPartner: false, isBloc: false,
    aseanMember: true, aseanStatus: "full",
    defaultPriority: 4, dashboardActive: false, indicatorDataAvailable: false,
    dataQuality: "good", populationMillions: 275.5, gdpNominalUsdB: 1371.2,
    riskLevel: "medium",
    mainExports: ["Coal", "Palm oil", "Nickel ore"],
    mainImportPartners: ["China", "Singapore", "Japan"],
    notes: "Largest ASEAN economy. Commodity-export dependent. Capital relocation to Nusantara ongoing. Key nickel and palm oil producer.",
  },

  {
    iso3: "MYS", iso2: "MY", wbCode: "MY",
    name: "Malaysia", shortName: "Malaysia", flagEmoji: "🇲🇾",
    capital: "Kuala Lumpur", currencyCode: "MYR", currencyName: "Malaysian Ringgit",
    regionGroup: "Southeast Asia", subRegion: "Maritime SEA",
    isSea: true, isPartner: false, isBloc: false,
    aseanMember: true, aseanStatus: "full",
    defaultPriority: 5, dashboardActive: false, indicatorDataAvailable: false,
    dataQuality: "good", populationMillions: 33.0, gdpNominalUsdB: 416.6,
    riskLevel: "low",
    mainExports: ["Electronics & semiconductors", "Palm oil", "LNG"],
    mainImportPartners: ["China", "Singapore", "United States"],
    notes: "Semiconductor cluster in Penang attracting major US chip investment. Ringgit volatility tied to commodity prices. ASEAN Chair 2025.",
  },

  {
    iso3: "PHL", iso2: "PH", wbCode: "PH",
    name: "Philippines", shortName: "Philippines", flagEmoji: "🇵🇭",
    capital: "Manila", currencyCode: "PHP", currencyName: "Philippine Peso",
    regionGroup: "Southeast Asia", subRegion: "Maritime SEA",
    isSea: true, isPartner: false, isBloc: false,
    aseanMember: true, aseanStatus: "full",
    defaultPriority: 6, dashboardActive: false, indicatorDataAvailable: false,
    dataQuality: "good", populationMillions: 114.2, gdpNominalUsdB: 435.0,
    riskLevel: "medium",
    mainExports: ["Electronics", "Remittances (services)", "Coconut products"],
    mainImportPartners: ["China", "Japan", "United States"],
    notes: "Large diaspora remittance inflows support consumption. Growing BPO sector. Typhoon risk creates periodic GDP shocks. South China Sea tensions.",
  },

  {
    iso3: "BRN", iso2: "BN", wbCode: "BN",
    name: "Brunei Darussalam", shortName: "Brunei", flagEmoji: "🇧🇳",
    capital: "Bandar Seri Begawan", currencyCode: "BND", currencyName: "Brunei Dollar",
    regionGroup: "Southeast Asia", subRegion: "Maritime SEA",
    isSea: true, isPartner: false, isBloc: false,
    aseanMember: true, aseanStatus: "full",
    defaultPriority: 10, dashboardActive: false, indicatorDataAvailable: false,
    dataQuality: "fair", populationMillions: 0.45, gdpNominalUsdB: 14.1,
    riskLevel: "low",
    mainExports: ["Crude oil", "Natural gas", "Methanol"],
    mainImportPartners: ["Malaysia", "Singapore", "China"],
    notes: "Micro oil-state. High GDP per capita. Economy entirely dependent on hydrocarbons. BND pegged 1:1 to SGD. Very limited World Bank data.",
  },

  {
    iso3: "TLS", iso2: "TL", wbCode: "TP",
    name: "Timor-Leste", shortName: "Timor-Leste", flagEmoji: "🇹🇱",
    capital: "Dili", currencyCode: "USD", currencyName: "US Dollar (official)",
    regionGroup: "Southeast Asia", subRegion: "Maritime SEA",
    isSea: true, isPartner: false, isBloc: false,
    aseanMember: false, aseanStatus: "candidate",
    defaultPriority: 11, dashboardActive: false, indicatorDataAvailable: false,
    dataQuality: "poor", populationMillions: 1.3, gdpNominalUsdB: 2.0,
    riskLevel: "high",
    mainExports: ["Petroleum (offshore)", "Coffee"],
    mainImportPartners: ["Indonesia", "Australia", "Singapore"],
    notes: "ASEAN candidate. Uses USD — no independent monetary policy. Petroleum Fund is primary fiscal resource. WB code TP (legacy East Timor identifier).",
  },

  // ── Partner countries ───────────────────────────────────────────────────────

  {
    iso3: "CHN", iso2: "CN", wbCode: "CN",
    name: "China", shortName: "China", flagEmoji: "🇨🇳",
    capital: "Beijing", currencyCode: "CNY", currencyName: "Chinese Yuan Renminbi",
    regionGroup: "East Asia", subRegion: "East Asia",
    isSea: false, isPartner: true, isBloc: false,
    aseanMember: false, aseanStatus: "none",
    defaultPriority: 12, dashboardActive: false, indicatorDataAvailable: false,
    dataQuality: "fair", populationMillions: 1411.0, gdpNominalUsdB: 17963.2,
    mainExports: ["Electronics", "Machinery", "Textiles"],
    mainImportPartners: ["United States", "Japan", "South Korea"],
    notes: "Largest trade partner for all SEA countries. BRI funder. Property crisis ongoing. US-China tech decoupling driving supply chain shifts to SEA.",
  },

  {
    iso3: "USA", iso2: "US", wbCode: "US",
    name: "United States", shortName: "United States", flagEmoji: "🇺🇸",
    capital: "Washington D.C.", currencyCode: "USD", currencyName: "US Dollar",
    regionGroup: "Americas", subRegion: "North America",
    isSea: false, isPartner: true, isBloc: false,
    aseanMember: false, aseanStatus: "none",
    defaultPriority: 13, dashboardActive: false, indicatorDataAvailable: false,
    dataQuality: "excellent", populationMillions: 331.0, gdpNominalUsdB: 25462.4,
    mainExports: ["Services", "Aircraft", "Petroleum"],
    mainImportPartners: ["China", "Mexico", "Canada"],
    notes: "Key export destination for VNM, THA, MYS. Primary source of tariff risk. Fed rate decisions affect SEA currency pressure.",
  },

  {
    iso3: "JPN", iso2: "JP", wbCode: "JP",
    name: "Japan", shortName: "Japan", flagEmoji: "🇯🇵",
    capital: "Tokyo", currencyCode: "JPY", currencyName: "Japanese Yen",
    regionGroup: "East Asia", subRegion: "East Asia",
    isSea: false, isPartner: true, isBloc: false,
    aseanMember: false, aseanStatus: "none",
    defaultPriority: 14, dashboardActive: false, indicatorDataAvailable: false,
    dataQuality: "excellent", populationMillions: 125.7, gdpNominalUsdB: 4409.7,
    mainExports: ["Vehicles", "Machinery", "Electronics"],
    mainImportPartners: ["China", "United States", "Australia"],
    notes: "Major FDI source for THA (auto), VNM (electronics). Yen weakness reduces FDI purchasing power. CPTPP founding member.",
  },

  {
    iso3: "IND", iso2: "IN", wbCode: "IN",
    name: "India", shortName: "India", flagEmoji: "🇮🇳",
    capital: "New Delhi", currencyCode: "INR", currencyName: "Indian Rupee",
    regionGroup: "South Asia", subRegion: "South Asia",
    isSea: false, isPartner: true, isBloc: false,
    aseanMember: false, aseanStatus: "none",
    defaultPriority: 15, dashboardActive: false, indicatorDataAvailable: false,
    dataQuality: "good", populationMillions: 1407.6, gdpNominalUsdB: 3386.4,
    mainExports: ["Petroleum products", "Pharmaceuticals", "Vehicles"],
    mainImportPartners: ["China", "United States", "UAE"],
    notes: "Rising regional power. Act East policy deepens ASEAN ties. Competing manufacturing FDI destination vs SEA.",
  },

  {
    iso3: "KOR", iso2: "KR", wbCode: "KR",
    name: "Republic of Korea", shortName: "South Korea", flagEmoji: "🇰🇷",
    capital: "Seoul", currencyCode: "KRW", currencyName: "South Korean Won",
    regionGroup: "East Asia", subRegion: "East Asia",
    isSea: false, isPartner: true, isBloc: false,
    aseanMember: false, aseanStatus: "none",
    defaultPriority: 16, dashboardActive: false, indicatorDataAvailable: false,
    dataQuality: "excellent", populationMillions: 51.7, gdpNominalUsdB: 1665.2,
    mainExports: ["Semiconductors", "Vehicles", "Ships"],
    mainImportPartners: ["China", "United States", "Australia"],
    notes: "Major FDI source for VNM (Samsung ~20% of Vietnam exports), IDN, THA. Korea-ASEAN FTA active.",
  },

  {
    iso3: "AUS", iso2: "AU", wbCode: "AU",
    name: "Australia", shortName: "Australia", flagEmoji: "🇦🇺",
    capital: "Canberra", currencyCode: "AUD", currencyName: "Australian Dollar",
    regionGroup: "Oceania", subRegion: "Oceania",
    isSea: false, isPartner: true, isBloc: false,
    aseanMember: false, aseanStatus: "none",
    defaultPriority: 17, dashboardActive: false, indicatorDataAvailable: false,
    dataQuality: "excellent", populationMillions: 25.9, gdpNominalUsdB: 1702.7,
    mainExports: ["Iron ore", "Coal", "Natural gas"],
    mainImportPartners: ["China", "United States", "South Korea"],
    notes: "Key ASEAN dialogue partner. CPTPP and RCEP member. Commodity exports relevant to SEA industrialisation. Australia-ASEAN Comprehensive Strategic Partnership.",
  },

  {
    iso3: "EUU", iso2: "EU", wbCode: "EU",
    name: "European Union", shortName: "EU", flagEmoji: "🇪🇺",
    capital: "Brussels", currencyCode: "EUR", currencyName: "Euro (bloc aggregate)",
    regionGroup: "Europe", subRegion: "Europe",
    isSea: false, isPartner: true, isBloc: true,
    aseanMember: false, aseanStatus: "none",
    defaultPriority: 18, dashboardActive: false, indicatorDataAvailable: false,
    dataQuality: "good", populationMillions: 447.0, gdpNominalUsdB: 16642.3,
    mainExports: ["Machinery", "Vehicles", "Pharmaceuticals"],
    mainImportPartners: ["China", "United States", "United Kingdom"],
    notes: "BLOC (27 member states). GSP/EBA preferences critical for KHM, MMR, LAO garment exports. EVFTA with VNM active. CBAM affects IDN, MYS commodity exporters.",
  },
];


// ─────────────────────────────────────────────────────────────────────────────
// DERIVED COLLECTIONS
// ─────────────────────────────────────────────────────────────────────────────

/** All 11 Southeast Asian countries, sorted by default_priority */
export const SEA_COUNTRIES: DashboardCountry[] = ALL_COUNTRIES
  .filter(c => c.isSea)
  .sort((a, b) => a.defaultPriority - b.defaultPriority);

/** All 7 partner / external entities, sorted by default_priority */
export const PARTNER_COUNTRIES: DashboardCountry[] = ALL_COUNTRIES
  .filter(c => c.isPartner)
  .sort((a, b) => a.defaultPriority - b.defaultPriority);

/** The 5 countries with full indicator data in sample-data.ts */
export const ACTIVE_COUNTRIES: DashboardCountry[] = ALL_COUNTRIES
  .filter(c => c.indicatorDataAvailable)
  .sort((a, b) => a.defaultPriority - b.defaultPriority);

/** Countries grouped by region_group */
export const COUNTRIES_BY_REGION: Record<string, DashboardCountry[]> = {};
for (const c of ALL_COUNTRIES) {
  if (!COUNTRIES_BY_REGION[c.regionGroup]) COUNTRIES_BY_REGION[c.regionGroup] = [];
  COUNTRIES_BY_REGION[c.regionGroup].push(c);
}

/** SEA mainland sub-group */
export const MAINLAND_SEA: DashboardCountry[] = SEA_COUNTRIES.filter(
  c => c.subRegion === "Mainland SEA"
);

/** SEA maritime sub-group */
export const MARITIME_SEA: DashboardCountry[] = SEA_COUNTRIES.filter(
  c => c.subRegion === "Maritime SEA"
);

/** ASEAN full members only */
export const ASEAN_MEMBERS: DashboardCountry[] = SEA_COUNTRIES.filter(
  c => c.aseanMember
);


// ─────────────────────────────────────────────────────────────────────────────
// HELPER FUNCTIONS
// ─────────────────────────────────────────────────────────────────────────────

/** Look up a country by ISO3 code. Returns undefined if not found. */
export function getCountry(iso3: string): DashboardCountry | undefined {
  return ALL_COUNTRIES.find(c => c.iso3 === iso3.toUpperCase());
}

/** Get flag emoji for a country (returns 🌏 if not found) */
export function getFlag(iso3: string): string {
  return getCountry(iso3)?.flagEmoji ?? "🌏";
}

/** Get short display name for a country */
export function getShortName(iso3: string): string {
  return getCountry(iso3)?.shortName ?? iso3;
}

/**
 * Filter countries by a filter mode.
 *
 * @param mode     - "sea" | "partners" | "all" | "active"
 * @param customIds - for mode "custom", the explicit ISO3 list
 */
export function getCountriesForMode(
  mode: "sea" | "partners" | "all" | "active" | "custom",
  customIds?: string[],
): DashboardCountry[] {
  switch (mode) {
    case "sea":     return SEA_COUNTRIES;
    case "partners":return PARTNER_COUNTRIES;
    case "all":     return ALL_COUNTRIES;
    case "active":  return ACTIVE_COUNTRIES;
    case "custom":  return (customIds ?? [])
      .map(id => getCountry(id))
      .filter((c): c is DashboardCountry => c !== undefined);
    default:        return SEA_COUNTRIES;
  }
}

/** ISO3 codes for a filter mode (convenient for filter comparisons) */
export function getIso3ForMode(
  mode: "sea" | "partners" | "all" | "active" | "custom",
  customIds?: string[],
): Set<string> {
  return new Set(getCountriesForMode(mode, customIds).map(c => c.iso3));
}

/** Data quality label for display */
export const DATA_QUALITY_LABEL: Record<DataQuality, string> = {
  excellent: "Excellent",
  good:      "Good",
  fair:      "Fair",
  poor:      "Poor — use with caution",
};

/** ASEAN status label for display */
export const ASEAN_STATUS_LABEL: Record<AseanStatus, string> = {
  full:      "ASEAN Member",
  candidate: "ASEAN Candidate",
  observer:  "ASEAN Observer",
  none:      "Non-ASEAN",
};
