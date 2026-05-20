/**
 * Static site links surfaced in the UI header/footer.
 *
 * The Langfuse public dashboard URL is only known after the U11 deploy, so it
 * is read from a public env var and the link is hidden when unset.
 */

export const SITE = {
  name: 'Aviation Ops Copilot',
  tagline: 'A tool-using LLM agent for aviation operations questions.',
  repoUrl: 'https://github.com/ShaydenPoole/OpsCopilot',
  evalUrl: 'https://github.com/ShaydenPoole/OpsCopilot/tree/main/evals',
  /** Set `NEXT_PUBLIC_LANGFUSE_URL` to the public Langfuse project view. */
  langfuseUrl: process.env.NEXT_PUBLIC_LANGFUSE_URL ?? '',
} as const;
