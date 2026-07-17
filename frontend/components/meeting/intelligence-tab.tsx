"use client";

import {
  AlertTriangle,
  CheckSquare,
  HelpCircle,
  Lightbulb,
  ListChecks,
  Square,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { meetingsApi } from "@/lib/endpoints";
import type { ActionItem, Intelligence } from "@/lib/types";
import { cn, formatDateTime } from "@/lib/utils";

// Insight type -> icon + label. Groups the flat insight list into sections.
const INSIGHT_META: Record<string, { label: string; icon: React.ElementType }> = {
  decision: { label: "Decisions", icon: CheckSquare },
  discussion_point: { label: "Discussion points", icon: Lightbulb },
  risk: { label: "Risks", icon: AlertTriangle },
  open_question: { label: "Open questions", icon: HelpCircle },
  follow_up: { label: "Follow-ups", icon: ListChecks },
};

const PRIORITY_VARIANT = {
  high: "destructive",
  medium: "warning",
  low: "secondary",
} as const;

export function IntelligenceTab({ meetingId }: { meetingId: string }) {
  const [intel, setIntel] = useState<Intelligence | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    meetingsApi
      .intelligence(meetingId)
      .then(setIntel)
      .finally(() => setLoading(false));
  }, [meetingId]);

  async function toggleItem(item: ActionItem) {
    const next = item.status === "done" ? "open" : "done";
    // Optimistic update; revert on failure.
    setIntel((prev) =>
      prev
        ? { ...prev, action_items: prev.action_items.map((a) => (a.id === item.id ? { ...a, status: next } : a)) }
        : prev
    );
    try {
      await meetingsApi.updateActionItem(meetingId, item.id, { status: next });
    } catch {
      toast.error("Could not update task");
      setIntel((prev) =>
        prev
          ? { ...prev, action_items: prev.action_items.map((a) => (a.id === item.id ? item : a)) }
          : prev
      );
    }
  }

  if (loading) return <Skeleton className="h-64 w-full" />;
  if (!intel || (intel.summaries.length === 0 && intel.action_items.length === 0)) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No intelligence yet. It appears once analysis completes.
      </p>
    );
  }

  const executive = intel.summaries.find((s) => s.summary_type === "executive");
  const full = intel.summaries.find((s) => s.summary_type === "full");
  const grouped = Object.keys(INSIGHT_META).map((type) => ({
    type,
    ...INSIGHT_META[type],
    items: intel.insights.filter((i) => i.insight_type === type),
  }));

  return (
    <div className="space-y-6">
      {/* Summaries */}
      {executive && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Executive summary</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-foreground/90">{executive.content}</CardContent>
        </Card>
      )}
      {full && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Full summary</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-foreground/90">{full.content}</CardContent>
        </Card>
      )}

      {/* Action items */}
      {intel.action_items.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Action items</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {intel.action_items.map((item) => (
              <button
                key={item.id}
                onClick={() => toggleItem(item)}
                className="flex w-full items-start gap-3 rounded-md p-2 text-left transition-colors hover:bg-accent"
              >
                {item.status === "done" ? (
                  <CheckSquare className="mt-0.5 h-4 w-4 shrink-0 text-[var(--success)]" />
                ) : (
                  <Square className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                )}
                <div className="min-w-0 flex-1">
                  <p className={cn("text-sm", item.status === "done" && "line-through text-muted-foreground")}>
                    {item.description}
                  </p>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    {item.assignee_name && <span>👤 {item.assignee_name}</span>}
                    {item.due_date && <span>📅 {formatDateTime(item.due_date)}</span>}
                    <Badge variant={PRIORITY_VARIANT[item.priority]}>{item.priority}</Badge>
                  </div>
                </div>
              </button>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Insights grouped by type */}
      <div className="grid gap-4 md:grid-cols-2">
        {grouped
          .filter((g) => g.items.length > 0)
          .map((g) => (
            <Card key={g.type}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <g.icon className="h-4 w-4 text-primary" /> {g.label}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 text-sm text-foreground/90">
                  {g.items.map((i) => (
                    <li key={i.id} className="flex gap-2">
                      <span className="text-muted-foreground">•</span>
                      {i.content}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ))}
      </div>
    </div>
  );
}
