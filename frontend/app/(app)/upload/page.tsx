"use client";

import { FileAudio, UploadCloud, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { ACCEPTED_EXTENSIONS, isAcceptedFile, uploadMeeting } from "@/lib/upload";
import { cn } from "@/lib/utils";

export default function UploadPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);

  function pick(f: File | null | undefined) {
    if (!f) return;
    if (!isAcceptedFile(f.name)) {
      toast.error(`Unsupported file. Allowed: ${ACCEPTED_EXTENSIONS.join(", ")}`);
      return;
    }
    setFile(f);
    if (!title) setTitle(f.name.replace(/\.[^.]+$/, ""));
  }

  async function onUpload() {
    if (!file) return;
    setProgress(0);
    try {
      const meeting = await uploadMeeting(file, title || undefined, setProgress);
      toast.success("Uploaded! Processing has started.");
      // Straight to the detail page, where live status polling takes over.
      router.push(`/meetings/${meeting.id}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Upload failed");
      setProgress(null);
    }
  }

  const uploading = progress !== null;

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Upload a meeting</h1>
        <p className="text-sm text-muted-foreground">
          MP3, WAV or MP4. We&apos;ll transcribe, identify speakers, and summarize it.
        </p>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          pick(e.dataTransfer.files?.[0]);
        }}
        onClick={() => !uploading && inputRef.current?.click()}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-10 text-center transition-colors",
          dragging ? "border-primary bg-primary/5" : "border-border hover:border-primary/50",
          uploading && "pointer-events-none opacity-60"
        )}
      >
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
          <UploadCloud className="h-6 w-6" />
        </div>
        <div>
          <p className="font-medium">Drag &amp; drop, or click to browse</p>
          <p className="text-xs text-muted-foreground">Max 500 MB</p>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_EXTENSIONS.join(",")}
          className="hidden"
          onChange={(e) => pick(e.target.files?.[0])}
        />
      </div>

      {/* Selected file + title + action */}
      {file && (
        <Card>
          <CardContent className="space-y-4 p-5">
            <div className="flex items-center gap-3">
              <FileAudio className="h-5 w-5 text-primary" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{file.name}</p>
                <p className="text-xs text-muted-foreground">
                  {(file.size / 1024 / 1024).toFixed(1)} MB
                </p>
              </div>
              {!uploading && (
                <Button variant="ghost" size="icon" onClick={() => setFile(null)}>
                  <X className="h-4 w-4" />
                </Button>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="title">Title</Label>
              <Input
                id="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                disabled={uploading}
                placeholder="Meeting title"
              />
            </div>

            {uploading ? (
              <div className="space-y-2">
                <Progress value={progress!} />
                <p className="text-center text-xs text-muted-foreground">
                  {progress! < 100 ? `Uploading… ${progress}%` : "Finishing up…"}
                </p>
              </div>
            ) : (
              <Button className="w-full" onClick={onUpload}>
                Upload &amp; process
              </Button>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
