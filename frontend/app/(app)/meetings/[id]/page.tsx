"use client";

import { ArrowLeft, Loader2, RefreshCw, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { IntelligenceTab } from "@/components/meeting/intelligence-tab";
import { SpeakersTab } from "@/components/meeting/speakers-tab";
import { TranscriptTab } from "@/components/meeting/transcript-tab";
import { StatusBadge, isProcessing } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { meetingsApi } from "@/lib/endpoints";
import type { MeetingDetail, MeetingStatus } from "@/lib/types";
import { formatDateTime, formatDuration } from "@/lib/utils";

// Ordered pipeline stages -> a progress percentage while processing.
const STAGES: MeetingStatus[] = [
  "uploaded",
  "extracting",
  "transcribing",
  "diarizing",
  "analyzing",
  "embedding",
  "completed",
];

export default function MeetingDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [meeting, setMeeting] = useState<MeetingDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    const data = await meetingsApi.get(id);
    setMeeting(data);
    return data;
  }, [id]);

  useEffect(() => {
    load().finally(() => setLoading(false));
  }, [load]);

  // Live polling: while the pipeline runs, re-fetch every 3s until it settles.
  useEffect(() => {
    if (!meeting) return;
    const running = isProcessing(meeting.status);
    if (running && !pollRef.current) {
      pollRef.current = setInterval(() => load(), 3000);
    }
    if (!running && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [meeting, load]);

  async function onReprocess() {
    try {
      await meetingsApi.reprocess(id);
      toast.success("Reprocessing started");
      await load();
    } catch {
      toast.error("Could not reprocess");
    }
  }

  async function onDelete() {
    if (!confirm("Delete this meeting? This can't be undone from the UI.")) return;
    try {
      await meetingsApi.remove(id);
      toast.success("Meeting deleted");
      router.push("/meetings");
    } catch {
      toast.error("Could not delete");
    }
  }

  if (loading) return <Skeleton className="h-64 w-full" />;
  if (!meeting) return <p className="text-sm text-muted-foreground">Meeting not found.</p>;

  const stageIndex = STAGES.indexOf(meeting.status);
  const progressPct = stageIndex >= 0 ? ((stageIndex + 1) / STAGES.length) * 100 : 0;
  const done = meeting.status === "completed";

  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" asChild>
        <Link href="/meetings">
          <ArrowLeft className="h-4 w-4" /> Back to meetings
        </Link>
      </Button>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{meeting.title}</h1>
          <p className="text-sm text-muted-foreground">
            {formatDateTime(meeting.created_at)} · {formatDuration(meeting.duration_seconds)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={meeting.status} />
          {(done || meeting.status === "failed") && (
            <Button variant="outline" size="sm" onClick={onReprocess}>
              <RefreshCw className="h-4 w-4" /> Reprocess
            </Button>
          )}
          <Button variant="ghost" size="icon" onClick={onDelete} aria-label="Delete">
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {meeting.error_message && (
        <Card className="border-destructive/40">
          <CardContent className="p-4 text-sm text-destructive">
            {meeting.error_message}
          </CardContent>
        </Card>
      )}

      {/* Live processing indicator */}
      {isProcessing(meeting.status) && (
        <Card>
          <CardContent className="space-y-3 p-5">
            <div className="flex items-center gap-2 text-sm">
              <Loader2 className="h-4 w-4 animate-spin text-primary" />
              <span className="font-medium">Processing…</span>
              <span className="text-muted-foreground">
                (updates automatically — this can take a few minutes)
              </span>
            </div>
            <Progress value={progressPct} />
          </CardContent>
        </Card>
      )}

      {/* Tabs (only meaningful once there's data, but they degrade gracefully) */}
      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="transcript">Transcript</TabsTrigger>
          <TabsTrigger value="speakers">Speakers</TabsTrigger>
          <TabsTrigger value="intelligence">Intelligence</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <Card>
            <CardContent className="space-y-3 p-5">
              <h3 className="text-sm font-semibold">Files</h3>
              {meeting.files.map((f) => (
                <div key={f.id} className="flex justify-between text-sm">
                  <span>{f.original_filename}</span>
                  <span className="text-muted-foreground">
                    {(f.size_bytes / 1024 / 1024).toFixed(1)} MB · {f.file_type}
                  </span>
                </div>
              ))}
              {meeting.tags.length > 0 && (
                <p className="pt-2 text-xs text-muted-foreground">
                  Tags: {meeting.tags.join(", ")}
                </p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="transcript">
          {done ? (
            <TranscriptTab meetingId={id} />
          ) : (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Transcript will appear when processing completes.
            </p>
          )}
        </TabsContent>

        <TabsContent value="speakers">
          {done ? (
            <SpeakersTab meetingId={id} />
          ) : (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Speakers will appear when processing completes.
            </p>
          )}
        </TabsContent>

        <TabsContent value="intelligence">
          {done ? (
            <IntelligenceTab meetingId={id} />
          ) : (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Summary &amp; action items will appear when processing completes.
            </p>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
