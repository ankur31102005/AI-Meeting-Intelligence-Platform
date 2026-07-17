import { Badge } from "@/components/ui/badge";
import type { MeetingStatus } from "@/lib/types";

/** Maps a pipeline status to a colored badge with a human label. */
const STATUS_META: Record<
  MeetingStatus,
  { label: string; variant: "default" | "success" | "warning" | "destructive" | "secondary" }
> = {
  uploaded: { label: "Uploaded", variant: "secondary" },
  extracting: { label: "Extracting audio", variant: "warning" },
  transcribing: { label: "Transcribing", variant: "warning" },
  diarizing: { label: "Identifying speakers", variant: "warning" },
  analyzing: { label: "Analyzing", variant: "warning" },
  embedding: { label: "Indexing", variant: "warning" },
  completed: { label: "Completed", variant: "success" },
  failed: { label: "Failed", variant: "destructive" },
};

export function StatusBadge({ status }: { status: MeetingStatus }) {
  const meta = STATUS_META[status] ?? { label: status, variant: "secondary" as const };
  return <Badge variant={meta.variant}>{meta.label}</Badge>;
}

/** True while the pipeline is still working — used to poll for updates. */
export function isProcessing(status: MeetingStatus): boolean {
  return !["completed", "failed"].includes(status);
}
