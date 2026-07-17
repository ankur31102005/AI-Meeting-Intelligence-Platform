import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import type { Citation } from "@/lib/types";
import { formatTimestamp } from "@/lib/utils";

/** Renders the sources an assistant answer drew from — each links back to the
 * exact meeting + timestamp (the trust/verifiability layer of RAG). */
export function Citations({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null;
  return (
    <div className="mt-3 space-y-2 border-t pt-3">
      <p className="text-xs font-medium text-muted-foreground">Sources</p>
      {citations.map((c) => (
        <div key={c.excerpt} className="rounded-md bg-muted/50 p-2 text-xs">
          <p className="line-clamp-2 text-foreground/80">{c.text}</p>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-muted-foreground">
            {c.meeting_id && (
              <Link href={`/meetings/${c.meeting_id}`} className="text-primary hover:underline">
                Open meeting
              </Link>
            )}
            {c.start_time != null && <span>· {formatTimestamp(c.start_time)}</span>}
            <Badge variant="secondary">{(c.score * 100).toFixed(0)}%</Badge>
          </div>
        </div>
      ))}
    </div>
  );
}
