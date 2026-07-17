import { cn } from "@/lib/utils";

/** Loading placeholder — pulse animation over the muted color. */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} {...props} />;
}
