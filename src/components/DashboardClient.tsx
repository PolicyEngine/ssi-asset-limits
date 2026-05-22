"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  ChartContainer,
  DataTable,
  MetricCard,
  PEBarChart,
} from "@policyengine/ui-kit";
import { CsvRow, loadCsv } from "@/src/lib/csv";
import {
  formatCurrency,
  formatPeople,
  formatRate,
  numeric,
} from "@/src/lib/format";

const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

function formatMetric(row: CsvRow): string {
  const value = numeric(row.value);
  if (row.unit === "currency") {
    return formatCurrency(value);
  }
  if (row.unit === "people") {
    return formatPeople(value);
  }
  if (row.unit === "rate") {
    return formatRate(value);
  }
  return value.toLocaleString("en-US");
}

function metric(summary: CsvRow[], key: string): CsvRow | undefined {
  return summary.find((row) => row.metric === key);
}

export default function DashboardClient() {
  const [summary, setSummary] = useState<CsvRow[]>([]);
  const [resourceBins, setResourceBins] = useState<CsvRow[]>([]);

  useEffect(() => {
    void Promise.all([
      loadCsv(`${BASE_PATH}/data/national_summary.csv`),
      loadCsv(`${BASE_PATH}/data/resource_bins.csv`),
    ]).then(([nationalSummary, bins]) => {
      setSummary(nationalSummary);
      setResourceBins(bins);
    });
  }, []);

  const headlineMetrics = useMemo(
    () =>
      [
        "annual_ssi_cost",
        "new_recipients",
        "average_gain",
        "people_lifted_from_poverty",
      ]
        .map((key) => metric(summary, key))
        .filter((row): row is CsvRow => row !== undefined),
    [summary],
  );

  const chartData = useMemo(
    () =>
      resourceBins.map((row) => ({
        resource_bin: row.resource_bin,
        ssi_increase: numeric(row.ssi_increase),
      })),
    [resourceBins],
  );

  return (
    <main className="min-h-screen bg-background">
      <section className="border-b border-border bg-muted/35">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-6 py-8">
          <p className="text-sm font-semibold uppercase tracking-[0.08em] text-muted-foreground">
            Supplemental Security Income
          </p>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
            <div className="flex flex-col gap-3">
              <h1 className="text-3xl font-semibold tracking-normal text-foreground md:text-4xl">
                SSI asset limits
              </h1>
              <p className="max-w-3xl text-base leading-7 text-muted-foreground">
                Estimated impact of removing the SSI resource test using
                PolicyEngine US and the Enhanced CPS.
              </p>
            </div>
            <Card className="self-start">
              <CardHeader>
                <CardTitle>Current law limits</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-2 text-sm text-muted-foreground">
                <div className="flex justify-between gap-4">
                  <span>Individual</span>
                  <strong className="text-foreground">$2,000</strong>
                </div>
                <div className="flex justify-between gap-4">
                  <span>Couple</span>
                  <strong className="text-foreground">$3,000</strong>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      <section className="mx-auto grid max-w-6xl gap-6 px-6 py-8">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {headlineMetrics.length === 0
            ? ["Annual SSI cost", "New SSI recipients", "Average gain", "Poverty impact"].map(
                (label) => (
                  <MetricCard
                    key={label}
                    label={label}
                    value="Run data pipeline"
                    format="string"
                  />
                ),
              )
            : headlineMetrics.map((row) => (
                <MetricCard
                  key={row.metric}
                  label={row.label}
                  value={formatMetric(row)}
                  format="string"
                />
              ))}
        </div>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_24rem]">
          <ChartContainer
            title="SSI increase by countable resources"
            subtitle="Annual benefit increase by baseline SSI countable-resource bin"
          >
            <PEBarChart
              data={chartData}
              xKey="resource_bin"
              yKey="ssi_increase"
              height={360}
              fillColor="var(--chart-1)"
              formatTooltip={formatCurrency}
              margin={{ left: 24, right: 16, bottom: 88 }}
            />
          </ChartContainer>

          <Card>
            <CardHeader>
              <CardTitle>Methodology</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 text-sm leading-6 text-muted-foreground">
              <p>
                The reform sets the SSI individual and couple resource limits
                to a binding-free level from 2026 onward.
              </p>
              <p>
                Data are generated by the Python package in this repo. The app
                reads CSV outputs from <code>public/data</code>.
              </p>
              <p>
                Provenance: PolicyEngine US microsimulation, Enhanced CPS, and
                package versions from the generation environment.
              </p>
            </CardContent>
          </Card>
        </div>

        <DataTable
          columns={[
            { key: "resource_bin", header: "Resource bin" },
            {
              key: "people",
              header: "People",
              align: "right",
              format: (value) => formatPeople(numeric(String(value))),
            },
            {
              key: "ssi_increase",
              header: "SSI increase",
              align: "right",
              format: (value) => formatCurrency(numeric(String(value))),
            },
            {
              key: "average_gain",
              header: "Average gain",
              align: "right",
              format: (value) => formatCurrency(numeric(String(value))),
            },
          ]}
          data={resourceBins}
        />
      </section>
    </main>
  );
}
