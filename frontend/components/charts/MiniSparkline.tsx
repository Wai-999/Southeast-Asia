"use client";
import { LineChart, Line, ResponsiveContainer } from "recharts";
import type { YearPoint } from "@/data/sample-data";

interface Props { data: YearPoint[]; positive?: boolean; }

export default function MiniSparkline({ data, positive = true }: Props) {
  const color = positive ? "#10b981" : "#ef4444";
  return (
    <ResponsiveContainer width="100%" height={36}>
      <LineChart data={data}>
        <Line type="monotone" dataKey="value" stroke={color} strokeWidth={1.5} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
