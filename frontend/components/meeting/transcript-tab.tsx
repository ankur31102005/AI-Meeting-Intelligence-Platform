"use client";

import { useEffect, useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { meetingsApi } from "@/lib/endpoints";
import type { Transcript } from "@/lib/types";
import { cn, formatTimestamp } from "@/lib/utils";

// Stable color per speaker label so the eye can follow a speaker down the page.
const SPEAKER_COLORS = [
  "text-blue-500",
  "text-emerald-500",
  "text-amber-500",
  "text-pink-500",
  "text-violet-500",
];

export function TranscriptTab({ meetingId }: { meetingId: string }) {
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    meetingsApi
      .transcript(meetingId)
      .then(setTranscript)
      .finally(() => setLoading(false));
  }, [meetingId]);

  if (loading) {
    return (
      <div className="space-y-3">
        {[...Array(6)].map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (!transcript || transcript.segments.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">No transcript yet.</p>;
  }

  // Assign each distinct speaker a color.
  const labels = Array.from(
    new Set(transcript.segments.map((s) => s.speaker_label).filter(Boolean))
  ) as string[];
  const colorFor = (label: string | null) =>
    label ? SPEAKER_COLORS[labels.indexOf(label) % SPEAKER_COLORS.length] : "text-muted-foreground";

  return (
    <div className="space-y-4">
      {transcript.segments.map((seg) => (
        <div key={seg.id} className="flex gap-4">
          <span className="w-12 shrink-0 pt-0.5 text-xs tabular-nums text-muted-foreground">
            {formatTimestamp(seg.start_time)}
          </span>
          <div>
            <span className={cn("text-sm font-semibold", colorFor(seg.speaker_label))}>
              {seg.speaker_label ?? "Unknown"}
            </span>
            <p className="text-sm text-foreground/90">{seg.text}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
