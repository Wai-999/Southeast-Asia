import { create } from "zustand";
import type { Country, PatternAlert } from "@/data/sample-data";

interface DashboardState {
  selectedCountry: string | null;
  selectedYear: number;
  activeAlerts: PatternAlert[];
  countries: Country[];

  setSelectedCountry: (id: string | null) => void;
  setSelectedYear: (year: number) => void;
  setActiveAlerts: (alerts: PatternAlert[]) => void;
  setCountries: (countries: Country[]) => void;
}

export const useDashboardStore = create<DashboardState>((set) => ({
  selectedCountry: null,
  selectedYear: new Date().getFullYear() - 1,  // default: last full year
  activeAlerts: [],
  countries: [],

  setSelectedCountry: (id) => set({ selectedCountry: id }),
  setSelectedYear: (year) => set({ selectedYear: year }),
  setActiveAlerts: (alerts) => set({ activeAlerts: alerts }),
  setCountries: (countries) => set({ countries }),
}));
