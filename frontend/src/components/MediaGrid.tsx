import type { MediaFile } from '../types/media';
import { getThumbnailUrl } from '../api/client';

interface MediaGridProps {
  items: MediaFile[];
  loading: boolean;
  onSelect: (media: MediaFile) => void;
}

function MediaCard({ media, onClick }: { media: MediaFile; onClick: () => void }) {
  const aspectRatio =
    media.width && media.height ? media.width / media.height : 1;

  return (
    <button
      onClick={onClick}
      className="group relative overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] transition-all hover:border-[var(--color-accent)]/50 hover:shadow-lg hover:shadow-[var(--color-accent)]/5 text-left"
    >
      <div
        className="relative w-full bg-[var(--color-bg)]"
        style={{ paddingBottom: `${Math.min(100 / aspectRatio, 150)}%` }}
      >
        {media.thumbnail_url ? (
          <img
            src={getThumbnailUrl(media.thumbnail_url)}
            alt={media.file_name}
            loading="lazy"
            className="absolute inset-0 h-full w-full object-cover"
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-[var(--color-text-muted)]">
            {media.media_type === 'video' ? '▶' : '🖼'}
          </div>
        )}

        {media.media_type === 'video' && (
          <div className="absolute bottom-2 right-2 rounded bg-black/70 px-1.5 py-0.5 text-xs text-white">
            VIDEO
          </div>
        )}
      </div>

      <div className="p-2">
        <p className="truncate text-xs text-[var(--color-text)]">{media.file_name}</p>
        {media.checkpoint_name && (
          <p className="mt-0.5 truncate text-xs text-[var(--color-text-muted)]">
            {media.checkpoint_name}
          </p>
        )}
        {media.positive_prompt && (
          <p className="mt-0.5 line-clamp-2 text-xs text-[var(--color-text-muted)]">
            {media.positive_prompt}
          </p>
        )}
      </div>
    </button>
  );
}

export default function MediaGrid({ items, loading, onSelect }: MediaGridProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
        {Array.from({ length: 18 }).map((_, i) => (
          <div
            key={i}
            className="animate-pulse rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]"
          >
            <div className="aspect-square bg-[var(--color-bg)]" />
            <div className="space-y-1 p-2">
              <div className="h-3 w-3/4 rounded bg-[var(--color-bg)]" />
              <div className="h-3 w-1/2 rounded bg-[var(--color-bg)]" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-[var(--color-text-muted)]">
        <span className="text-4xl">📂</span>
        <p className="text-lg">No media found</p>
        <p className="text-sm">Try adjusting your search or scan for new files.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
      {items.map((media) => (
        <MediaCard key={media.id} media={media} onClick={() => onSelect(media)} />
      ))}
    </div>
  );
}
