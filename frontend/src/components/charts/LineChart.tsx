"use client";

import {
  CartesianGrid,
  Line,
  LineChart as RechartsLineChart,
  XAxis,
  YAxis,
} from "recharts";
import type { DotItemDotProps } from "recharts";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { cn } from "@/lib/utils";

// Lab/vital trend line chart via shadcn's `chart` wrapper around recharts.
//
// Abnormal points are never marked by colour alone: each carries a distinct
// marker shape (an unfilled ring instead of a filled dot) in addition to the
// critical colour, and the caller renders the same points as text rows below
// the chart with an icon + label (.claude/rules/frontend.md,
// clinical-safety.md — colour never carries meaning alone).

export interface LinePoint {
  x: string;
  value: number;
  abnormal: boolean;
}

interface LineChartProps {
  data: LinePoint[];
  ariaLabel: string;
  className?: string;
}

const chartConfig = {
  value: { label: "Value", color: "var(--chart-1)" },
} satisfies ChartConfig;

function TrendDot(props: DotItemDotProps) {
  const { cx, cy, payload, index } = props;
  if (cx == null || cy == null) return null;
  const abnormal = Boolean((payload as LinePoint | undefined)?.abnormal);
  if (abnormal) {
    return (
      <circle
        key={index}
        cx={cx}
        cy={cy}
        r={6}
        fill="none"
        stroke="var(--critical)"
        strokeWidth={2}
      />
    );
  }
  return <circle key={index} cx={cx} cy={cy} r={3} fill="var(--color-value)" />;
}

export function LineChart({ data, ariaLabel, className }: LineChartProps) {
  if (data.length === 0) return null;

  return (
    <div role="img" aria-label={ariaLabel} className={cn("w-full", className)}>
      <ChartContainer config={chartConfig} className="aspect-auto h-40 w-full">
        <RechartsLineChart data={data} margin={{ left: 0, right: 12, top: 8 }}>
          <CartesianGrid vertical={false} />
          <XAxis
            dataKey="x"
            tickLine={false}
            axisLine={false}
            tickMargin={8}
            fontSize={10}
          />
          <YAxis hide domain={["auto", "auto"]} />
          <ChartTooltip
            cursor={false}
            content={
              <ChartTooltipContent
                hideLabel
                formatter={(value, _name, item) => (
                  <div className="flex flex-1 items-center justify-between gap-2">
                    <span className="flex-1 text-muted-foreground">
                      {String(item.payload?.x ?? "")}
                    </span>
                    <span className="font-mono font-medium text-foreground tabular-nums">
                      {String(value)}
                    </span>
                  </div>
                )}
              />
            }
          />
          <Line
            dataKey="value"
            type="monotone"
            stroke="var(--color-value)"
            strokeWidth={2}
            dot={TrendDot}
            isAnimationActive={false}
          />
        </RechartsLineChart>
      </ChartContainer>
    </div>
  );
}
