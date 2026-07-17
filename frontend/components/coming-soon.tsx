import { Construction } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

/** Placeholder for pages built in later modules. */
export function ComingSoon({ title, note }: { title: string; note: string }) {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Construction className="h-6 w-6" />
          </div>
          <p className="text-sm text-muted-foreground">{note}</p>
        </CardContent>
      </Card>
    </div>
  );
}
