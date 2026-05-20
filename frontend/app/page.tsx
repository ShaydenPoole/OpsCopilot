import { ChatSurface } from '@/components/ChatSurface';
import { EvalBadge } from '@/components/EvalBadge';
import { SITE } from '@/lib/site';

export default function Home() {
  return (
    <div className="flex h-screen flex-col">
      <header className="shrink-0 border-b border-slate-800 bg-slate-950/90 backdrop-blur">
        <div className="mx-auto flex max-w-3xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div>
            <h1 className="text-base font-semibold text-slate-100">{SITE.name}</h1>
            <p className="text-xs text-slate-500">{SITE.tagline}</p>
          </div>
          <nav className="flex items-center gap-3 text-sm">
            <EvalBadge />
            <a
              href={SITE.repoUrl}
              target="_blank"
              rel="noreferrer"
              className="text-slate-400 transition-colors hover:text-slate-100"
            >
              GitHub
            </a>
            {SITE.langfuseUrl && (
              <a
                href={SITE.langfuseUrl}
                target="_blank"
                rel="noreferrer"
                className="text-slate-400 transition-colors hover:text-slate-100"
              >
                Traces
              </a>
            )}
          </nav>
        </div>
      </header>

      <main className="min-h-0 flex-1">
        <ChatSurface />
      </main>
    </div>
  );
}
