"use client";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell, ReferenceLine,
} from "recharts";
import type { CompareRow } from "@/data/sample-data";

const RISK_COLOR: Record<string, string> = {
  low:      "#10b981",
  medium:   "#f59e0b",
  high:     "#f97316",
  critical: "#ef4444",
};

interface Props {
  data: CompareRow[];
  unit?: string;
  height?: number;
  colorByRisk?: boolean;
}

const CustomTooltip = ({ active, payload, unit }: any) => {
  if (!active || !payload?.length) return null;
  const entry = payload[0].payload as CompareRow;
  return (
    <div className="bg-white border border-slate-200 rounded-lg shadow-lg px-3 py-2 text-sm">
      <p className="font-medium text-slate-900">{entry.flagEmoji} {entry.countryName}</p>
      <p className="text-slate-700 mt-0.5">{entry.value.toFixed(1)} {unit}</p>
    </div>
  );
};

export default function CompareBarChart({ data, unit = "%", height = 280, colorByRisk = true }: Props) {
  const hasNegative = data.some(d => d.value < 0);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
        <XAxis
          dataKey="countryName"
          tick={{ fontSize: 11, fill: "#94a3b8" }}
          axisLine={false}
          tickLine={false}
          interval={0}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "#94a3b8" }}
          axisLine={false}
          tickLine={false}
          tickFormatter={v => `${v}${unit === "%" ? "%" : ""}`}
        />
        <Tooltip content={<CustomTooltip unit={unit} />} />
        {hasNegative && <ReferenceLine y={0} stroke="#cbd5e1" />}
        <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={42}>
          {data.map((entry, i) => (
            <Cell
              key={i}
              fill={colorByRisk ? RISK_COLOR[entry.riskLevel] : "#3b82f6"}
              opacity={0.85}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
