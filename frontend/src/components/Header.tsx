import { useState } from 'react';

interface HeaderProps {
  onSearch: (query: string) => void;
  onScan: () => void;
  scanning: boolean;
}

export default function Header({ onSearch, onScan, scanning }: HeaderProps) {
  const [searchInput, setSearchInput] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch(searchInput);
  };

  return (
    <header className="sticky top-0 z-50 border-b border-[var(--color-border)] bg-[var(--color-bg)]/95 backdrop-blur">
      <div className="mx-auto flex max-w-screen-2xl items-center gap-4 px-4 py-3">
        <h1 className="text-lg font-semibold tracking-tight whitespace-nowrap">
          ComfyUI Gallery
        </h1>

        <form onSubmit={handleSubmit} className="flex flex-1 max-w-xl">
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search workflows, models, loras..."
            className="flex-1 rounded-l-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text)] placeholder-[var(--color-text-muted)] outline-none focus:border-[var(--color-accent)]"
          />
          <button
            type="submit"
            className="rounded-r-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--color-accent-hover)] transition-colors"
          >
            Search
          </button>
        </form>

        <button
          onClick={onScan}
          disabled={scanning}
          className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)] transition-colors disabled:opacity-50"
        >
          {scanning ? 'Scanning...' : 'Rescan'}
        </button>
      </div>
    </header>
  );
}
