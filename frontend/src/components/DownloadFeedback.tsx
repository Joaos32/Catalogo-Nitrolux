import type { DownloadFeedbackState } from "../lib/use-download-action";

export default function DownloadFeedback({
  feedback,
}: {
  feedback: DownloadFeedbackState | null;
}): JSX.Element {
  return (
    <div role="status" aria-live="polite" aria-atomic="true">
      {feedback && <p className={`download-feedback is-${feedback.tone}`}>{feedback.text}</p>}
    </div>
  );
}
