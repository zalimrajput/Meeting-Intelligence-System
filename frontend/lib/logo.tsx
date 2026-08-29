export function LogoMark({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden>
      <rect width="24" height="24" rx="6" fill="#6366f1" />
      <path d="M6 5h12M5 18h14" stroke="#c7d2fe" strokeWidth="1.6" fill="none" strokeLinecap="round" />
      <path d="M5 14a6 4 0 1" stroke="#a5b4fc" strokeWidth="1.6" fill="none" strokeLinecap="round" />
    </svg>
  );
}
