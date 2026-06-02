"use client";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";
import type { YearPoint } from "@/data/sample-data";

interface Props {
  data: YearPoint[];
  color?: string;
  unit?: string;
  height?: number;
  showZeroLine?: boolean;
}

const CustomTooltip = ({ active, payload, label, unit }: any) => {
  if (!active || !payload?.length) return null;
  const v = payload[0].value as number;
  return (
    <div className="bg-white border border-slate-200 rounded-lg shadow-lg px-3 py-2 text-sm">
      <p className="text-slate-500 text-xs mb-1">{label}</p>
      <p className="font-semibold text-slate-900">
        {v >= 0 ? "" : ""}{v.toFixed(1)}{unit}
      </p>
    </div>
  );
};

export default function TrendLineChart({ data, color = "#3b82f6", unit = "%", height = 180, showZeroLine = true }: Props) {
  const min = Math.min(...data.map(d => d.value));
  const max = Math.max(...data.map(d => d.value));
  const pad = Math.max(1, (max - min) * 0.2);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
        <XAxis dataKey="year" tick={{ fontSize: 11, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
        <YAxis
          domain={[Math.floor(min - pad), Math.ceil(max + pad)]}
          tick={{ fontSize: 11, fill: "#94a3b8" }}
          axisLine={false}
          tickLine={false}
          tickFormatter={v => `${v}${unit}`}
        />
        <Tooltip content={<CustomTooltip unit={unit} />} />
        {showZeroLine && <ReferenceLine y={0} stroke="#e2e8f0" strokeDasharray="4 4" />}
        <Line
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2.5}
          dot={{ r: 4, fill: color, strokeWidth: 0 }}
          activeDot={{ r: 6, fill: color }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
