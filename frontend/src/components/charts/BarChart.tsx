"use client";

import {
  Bar,
  BarChart as RechartsBarChart,
  CartesianGrid,
  XAxis,
  YAxis,
} from "recharts";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { cn } from "@/lib/utils";

// Single-series bar chart (visit-frequency-by-month, provider-entry-counts)
// via shadcn's `chart` wrapper around recharts. Colour comes only from the
// chart token (`--color-value` → `--chart-1`), never a hex literal (ESLint:
// no hex under src/components/). The outer div carries `role="img"` +
// `aria-label` so the chart reads as one accessible summary; recharts' own
// SVG stays out of the accessibility tree (see ChartContainer).

export interface BarDatum {
  label: string;
  value: number;
}

interface BarChartProps {
  data: BarDatum[];
  /** Accessible label for the whole chart (e.g. "Visits per month"). */
  ariaLabel: string;
  formatValue?: (value: number) => string;
  className?: string;
}

const chartConfig = {
  value: { label: "Value", color: "var(--chart-1)" },
} satisfies ChartConfig;

export function BarChart({ data, ariaLabel, formatValue, className }: BarChartProps) {
  const fmt = formatValue ?? ((v: number) => String(v));

  return (
    <div role="img" aria-label={ariaLabel} className={cn("w-full", className)}>
      <ChartContainer config={chartConfig} className="aspect-auto h-40 w-full">
        <RechartsBarChart data={data} margin={{ left: 0, right: 0, top: 8 }}>
          <CartesianGrid vertical={false} />
          <XAxis
            dataKey="label"
            tickLine={false}
            axisLine={false}
            tickMargin={8}
            fontSize={10}
          />
          <YAxis hide />
          <ChartTooltip
            cursor={false}
            content={
              <ChartTooltipContent
                hideLabel
                formatter={(value, _name, item) => (
                  <div className="flex flex-1 items-center justify-between gap-2">
                    <div
                      className="h-2.5 w-2.5 shrink-0 rounded-[2px]"
                      style={{ backgroundColor: "var(--color-value)" }}
                    />
                    <span className="flex-1 text-muted-foreground">
                      {String(item.payload?.label ?? "")}
                    </span>
                    <span className="font-mono font-medium text-foreground tabular-nums">
                      {fmt(Number(value))}
                    </span>
                  </div>
                )}
              />
            }
          />
          <Bar dataKey="value" fill="var(--color-value)" radius={4} />
        </RechartsBarChart>
      </ChartContainer>
    </div>
  );
}
