"use client";

import { Check, Pencil, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { meetingsApi } from "@/lib/endpoints";
import type { Speaker } from "@/lib/types";

export function SpeakersTab({ meetingId }: { meetingId: string }) {
  const [speakers, setSpeakers] = useState<Speaker[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    meetingsApi
      .speakers(meetingId)
      .then(setSpeakers)
      .finally(() => setLoading(false));
  }, [meetingId]);

  async function save(sid: string) {
    if (!draft.trim()) return;
    try {
      const updated = await meetingsApi.renameSpeaker(meetingId, sid, draft.trim());
      setSpeakers((prev) => prev.map((s) => (s.id === sid ? updated : s)));
      setEditing(null);
      toast.success("Speaker renamed");
    } catch {
      toast.error("Could not rename speaker");
    }
  }

  if (loading) return <Skeleton className="h-32 w-full" />;
  if (speakers.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No speakers identified (diarization is optional and may be disabled).
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {speakers.map((s) => (
        <div
          key={s.id}
          className="flex items-center justify-between rounded-md border px-4 py-3"
        >
          {editing === s.id ? (
            <div className="flex flex-1 items-center gap-2">
              <Input
                autoFocus
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && save(s.id)}
                className="h-8 max-w-xs"
              />
              <Button size="icon" variant="ghost" onClick={() => save(s.id)}>
                <Check className="h-4 w-4" />
              </Button>
              <Button size="icon" variant="ghost" onClick={() => setEditing(null)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          ) : (
            <>
              <div>
                <p className="font-medium">{s.label}</p>
                {s.display_name && (
                  <p className="text-xs text-muted-foreground">{s.diarization_label}</p>
                )}
              </div>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setEditing(s.id);
                  setDraft(s.display_name ?? "");
                }}
              >
                <Pencil className="h-4 w-4" /> Rename
              </Button>
            </>
          )}
        </div>
      ))}
    </div>
  );
}
