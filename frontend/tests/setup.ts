import '@testing-library/jest-dom/vitest';

// jsdom does not implement scrollIntoView; ChatSurface calls it on every
// new message. Stub it so component tests don't error on the auto-scroll.
Element.prototype.scrollIntoView = () => {};
