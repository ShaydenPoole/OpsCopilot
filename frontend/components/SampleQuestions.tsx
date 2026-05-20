/**
 * Chip-style starter questions shown on first load. Each covers a different
 * tool path so a first-time visitor sees the agent's range — flight history,
 * live weather, NOTAMs, the FAA document corpus, and a multi-tool synthesis.
 */

export const SAMPLE_QUESTIONS: readonly string[] = [
  'What was the average departure delay at ORD in summer 2024?',
  'What is the current weather at KJFK?',
  'Are there any active NOTAMs for KSFO?',
  'What does the FAA AIM say about VFR flight into Class B airspace?',
  'Compare on-time performance between ATL and DFW over the last year.',
  'Given current weather and NOTAMs for KORD, what arrival delays should I expect?',
];

interface SampleQuestionsProps {
  onSelect: (question: string) => void;
  disabled?: boolean;
}

export function SampleQuestions({ onSelect, disabled = false }: SampleQuestionsProps) {
  return (
    <div className="flex flex-wrap gap-2" aria-label="Sample questions">
      {SAMPLE_QUESTIONS.map((question) => (
        <button
          key={question}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(question)}
          className="rounded-full border border-slate-700 bg-slate-900 px-3.5 py-1.5 text-left text-sm text-slate-300 transition-colors hover:border-accent/50 hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {question}
        </button>
      ))}
    </div>
  );
}
