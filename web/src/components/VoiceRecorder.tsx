import { motion } from "framer-motion";
import { Mic, RotateCcw, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";

const MAX_SECONDS = 10 * 60;

type State = "idle" | "recording" | "done";

function pickMimeType(): string {
  if (typeof MediaRecorder === "undefined") return "";
  // Safari records MP4/AAC, Chrome records WebM/Opus; Gemini accepts both.
  return ["audio/mp4", "audio/webm;codecs=opus", "audio/webm"].find((type) => MediaRecorder.isTypeSupported(type)) ?? "";
}

function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/** Record a voice note in the browser. Hands back the recording as a file, or null when cleared. */
export function VoiceRecorder({ onRecorded, disabled }: { onRecorded: (file: File | null) => void; disabled?: boolean }) {
  const [state, setState] = useState<State>("idle");
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [playback, setPlayback] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const timer = useRef<number | null>(null);

  function release() {
    if (timer.current) window.clearInterval(timer.current);
    timer.current = null;
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
  }

  useEffect(
    () => () => {
      if (recorder.current?.state === "recording") recorder.current.stop();
      release();
    },
    [],
  );
  useEffect(() => () => void (playback && URL.revokeObjectURL(playback)), [playback]);

  async function start() {
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("Recording isn't available here. Choose a voice memo instead.");
      return;
    }
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      const blocked = (e as { name?: string }).name === "NotAllowedError";
      setError(
        blocked
          ? "Microphone access is blocked. Allow it for this app in your phone's settings, then try again."
          : "The microphone could not be started.",
      );
      return;
    }
    const mimeType = pickMimeType();
    const chunks: Blob[] = [];
    const rec = new MediaRecorder(stream.current, mimeType ? { mimeType } : undefined);
    rec.ondataavailable = (event) => event.data.size && chunks.push(event.data);
    rec.onstop = () => {
      release();
      const type = (rec.mimeType || mimeType || "audio/webm").split(";")[0];
      const blob = new Blob(chunks, { type });
      if (!blob.size) {
        setState("idle");
        setError("Nothing was recorded. Try again.");
        return;
      }
      const file = new File([blob], `voice-recipe.${type.includes("mp4") ? "m4a" : "webm"}`, { type });
      setPlayback(URL.createObjectURL(blob));
      setState("done");
      onRecorded(file);
    };
    recorder.current = rec;
    rec.start(1000);
    setSeconds(0);
    setState("recording");
    onRecorded(null);
    timer.current = window.setInterval(() => {
      setSeconds((s) => {
        if (s + 1 >= MAX_SECONDS && rec.state === "recording") rec.stop();
        return s + 1;
      });
    }, 1000);
  }

  function stop() {
    if (recorder.current?.state === "recording") recorder.current.stop();
  }

  function reset() {
    setPlayback(null);
    setState("idle");
    setSeconds(0);
    onRecorded(null);
  }

  return (
    <div className="flex flex-col items-center gap-4 rounded-3xl bg-card px-4 py-6 text-center ring-1 ring-line">
      {state === "done" && playback ? (
        <>
          <audio controls src={playback} className="w-full" aria-label="Your recording" />
          <button type="button" onClick={reset} disabled={disabled} className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-semibold text-ink-soft hover:bg-paper hover:text-ink">
            <RotateCcw size={16} /> Record again
          </button>
        </>
      ) : (
        <>
          <motion.button
            type="button"
            onClick={state === "recording" ? stop : start}
            disabled={disabled}
            aria-label={state === "recording" ? "Stop recording" : "Start recording"}
            whileTap={{ scale: 0.94 }}
            className={`relative grid h-20 w-20 place-items-center rounded-full text-card ${state === "recording" ? "bg-orange" : "bg-ink"}`}
          >
            {state === "recording" ? (
              <>
                <motion.span
                  className="absolute inset-0 rounded-full bg-orange"
                  animate={{ scale: [1, 1.35], opacity: [0.5, 0] }}
                  transition={{ duration: 1.2, repeat: Infinity, ease: "easeOut" }}
                  aria-hidden="true"
                />
                <Square size={26} fill="currentColor" />
              </>
            ) : (
              <Mic size={30} />
            )}
          </motion.button>
          <p className="text-sm font-semibold tabular-nums" aria-live="polite">
            {state === "recording" ? `Recording ${clock(seconds)} · tap to stop` : "Tap to start talking"}
          </p>
        </>
      )}
      {error ? (
        <p className="text-sm font-medium text-orange" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
