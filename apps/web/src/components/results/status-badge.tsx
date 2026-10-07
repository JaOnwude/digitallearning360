import type { SheetStatus } from "@dl360/api-client";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const LABEL: Record<SheetStatus, string> = {
  draft: "In progress",
  submitted: "Waiting for approval",
  approved: "Approved",
  published: "Published",
};

const TONE: Record<SheetStatus, string> = {
  draft: "bg-muted text-muted-foreground",
  submitted: "bg-warning/20 text-warning-foreground",
  approved: "bg-brand/20 text-brand-ink",
  published: "bg-success/15 text-success",
};

export function StatusBadge({ status, className }: { status: SheetStatus; className?: string }) {
  return <Badge className={cn("border-transparent", TONE[status], className)}>{LABEL[status]}</Badge>;
}
