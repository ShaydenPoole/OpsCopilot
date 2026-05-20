/**
 * Renders an answer body, with a blinking cursor while the run is still
 * streaming. Whitespace is preserved so the agent's paragraph breaks survive.
 */

interface StreamingTextProps {
  text: string;
  streaming: boolean;
}

export function StreamingText({ text, streaming }: StreamingTextProps) {
  return (
    <p className="whitespace-pre-wrap leading-relaxed text-slate-100">
      {text}
      {streaming && (
        <span className="cursor-blink ml-0.5 inline-block text-accent" aria-hidden>
          ▌
        </span>
      )}
    </p>
  );
}
