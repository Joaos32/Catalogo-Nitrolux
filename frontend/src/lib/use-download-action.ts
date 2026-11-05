import { useRef, useState } from "react";

export interface DownloadFeedbackState {
  tone: "info" | "warning";
  text: string;
}
export interface DownloadAction {
  pending: string | null;
  feedback: DownloadFeedbackState | null;
  run: (label: string, operation: () => Promise<void>) => Promise<void>;
}
export function useDownloadAction(): DownloadAction {
  const inFlight = useRef(false);
  const [pending, setPending] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<DownloadFeedbackState | null>(null);
  const run = async (label: string, operation: () => Promise<void>) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setPending(label);
    setFeedback({ tone: "info", text: `Preparando ${label}…` });
    try {
      await operation();
      setFeedback({ tone: "info", text: `Download de ${label} iniciado.` });
    } catch {
      setFeedback({ tone: "warning", text: `Não foi possível baixar ${label}. Tente novamente.` });
    } finally {
      inFlight.current = false;
      setPending(null);
    }
  };
  return { pending, feedback, run };
}
