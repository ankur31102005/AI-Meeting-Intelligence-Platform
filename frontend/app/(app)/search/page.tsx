"use client";

import { Search as SearchIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { chatApi } from "@/lib/endpoints";
import type { SearchResult } from "@/lib/types";
import { formatTimestamp } from "@/lib/utils";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [loading, setLoading] = useState(false);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    try {
      const resp = await chatApi.search(query.trim());
      setResults(resp.results);
    } catch {
      toast.error("Search failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Search</h1>
        <p className="text-sm text-muted-foreground">
          Semantic search across all your meetings — find by meaning, not just keywords.
        </p>
      </div>

      <form onSubmit={run} className="flex gap-2">
        <div className="relative flex-1">
          <SearchIcon className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder="e.g. what did we decide about the release?"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <Button type="submit" disabled={loading}>
          {loading ? "Searching…" : "Search"}
        </Button>
      </form>

      {results !== null && (
        <div className="space-y-3">
          {results.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No matches found. Meetings must finish processing to be searchable.
            </p>
          ) : (
            results.map((r, i) => (
              <Card key={i}>
                <CardContent className="space-y-2 p-4">
                  <p className="text-sm text-foreground/90">{r.text}</p>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    {r.meeting_id && (
                      <Link
                        href={`/meetings/${r.meeting_id}`}
                        className="text-primary hover:underline"
                      >
                        Open meeting
                      </Link>
                    )}
                    {r.start_time != null && <span>· at {formatTimestamp(r.start_time)}</span>}
                    <Badge variant="secondary">match {(r.score * 100).toFixed(0)}%</Badge>
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      )}
    </div>
  );
}
