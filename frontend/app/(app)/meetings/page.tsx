"use client";

import { Search as SearchIcon } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { meetingsApi } from "@/lib/endpoints";
import type { Meeting, PaginationMeta } from "@/lib/types";
import { formatDateTime, formatDuration } from "@/lib/utils";

const PAGE_SIZE = 10;

export default function MeetingsPage() {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [meta, setMeta] = useState<PaginationMeta | null>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [loading, setLoading] = useState(true);

  // Debounce the search box so we don't hit the API on every keystroke.
  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search);
      setPage(1);
    }, 350);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    setLoading(true);
    meetingsApi
      .list({ page, page_size: PAGE_SIZE, search: debounced || undefined })
      .then((resp) => {
        setMeetings(resp.data ?? []);
        setMeta(resp.meta);
      })
      .finally(() => setLoading(false));
  }, [page, debounced]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Meetings</h1>
          <p className="text-sm text-muted-foreground">All your recorded meetings.</p>
        </div>
        <Button asChild>
          <Link href="/upload">Upload meeting</Link>
        </Button>
      </div>

      <div className="relative max-w-sm">
        <SearchIcon className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search by title…"
          className="pl-9"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <Card>
        <CardContent className="p-2">
          {loading ? (
            <div className="space-y-2 p-2">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : meetings.length === 0 ? (
            <p className="py-12 text-center text-sm text-muted-foreground">
              No meetings found.
            </p>
          ) : (
            <div className="divide-y">
              {meetings.map((m) => (
                <Link
                  key={m.id}
                  href={`/meetings/${m.id}`}
                  className="flex items-center justify-between px-4 py-4 transition-colors hover:bg-accent"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium">{m.title}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatDateTime(m.created_at)} · {formatDuration(m.duration_seconds)}
                      {m.tags.length > 0 && ` · ${m.tags.join(", ")}`}
                    </p>
                  </div>
                  <StatusBadge status={m.status} />
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {meta && meta.total_pages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Page {meta.page} of {meta.total_pages} · {meta.total_items} total
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= meta.total_pages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
