"use client";

import { CheckCircle2, Clock, ListTodo, Video } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { meetingsApi } from "@/lib/endpoints";
import type { Meeting } from "@/lib/types";
import { formatDateTime, formatDuration } from "@/lib/utils";

interface Stats {
  total: number;
  completed: number;
  processing: number;
  totalSeconds: number;
}

export default function DashboardPage() {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        // One page is enough for recent view; stats use the total count + this page.
        const resp = await meetingsApi.list({ page: 1, page_size: 50 });
        const items = resp.data ?? [];
        setMeetings(items.slice(0, 6));
        setStats({
          total: resp.meta?.total_items ?? items.length,
          completed: items.filter((m) => m.status === "completed").length,
          processing: items.filter(
            (m) => !["completed", "failed"].includes(m.status)
          ).length,
          totalSeconds: items.reduce((s, m) => s + (m.duration_seconds ?? 0), 0),
        });
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground">Overview of your meetings.</p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard icon={Video} label="Total meetings" value={stats?.total} loading={loading} />
        <StatCard icon={CheckCircle2} label="Completed" value={stats?.completed} loading={loading} />
        <StatCard icon={Clock} label="Processing" value={stats?.processing} loading={loading} />
        <StatCard
          icon={ListTodo}
          label="Hours recorded"
          value={stats ? Math.round((stats.totalSeconds / 3600) * 10) / 10 : undefined}
          loading={loading}
        />
      </div>

      {/* Recent meetings */}
      <Card>
        <CardHeader>
          <CardTitle>Recent meetings</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1">
          {loading ? (
            [...Array(4)].map((_, i) => <Skeleton key={i} className="h-14 w-full" />)
          ) : meetings.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No meetings yet.{" "}
              <Link href="/upload" className="text-primary hover:underline">
                Upload one
              </Link>{" "}
              to get started.
            </p>
          ) : (
            meetings.map((m) => (
              <Link
                key={m.id}
                href={`/meetings/${m.id}`}
                className="flex items-center justify-between rounded-md px-3 py-3 transition-colors hover:bg-accent"
              >
                <div className="min-w-0">
                  <p className="truncate font-medium">{m.title}</p>
                  <p className="text-xs text-muted-foreground">
                    {formatDateTime(m.created_at)} · {formatDuration(m.duration_seconds)}
                  </p>
                </div>
                <StatusBadge status={m.status} />
              </Link>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  loading,
}: {
  icon: React.ElementType;
  label: string;
  value: number | undefined;
  loading: boolean;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-5">
        <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <p className="text-xs text-muted-foreground">{label}</p>
          {loading ? (
            <Skeleton className="mt-1 h-6 w-12" />
          ) : (
            <p className="text-2xl font-semibold">{value ?? 0}</p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
