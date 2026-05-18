import { useEffect } from 'react';
import type { MediaFile } from '../types/media';
import { getMediaFileUrl } from '../api/client';

interface MediaViewerProps {
  media: MediaFile;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function MetadataRow({ label, value }: { label: string; value: string | number | null | undefined }) {
  if (value == null || value === '') return null;
  return (
    <div className="flex justify-between gap-2 py-1">
      <span className="shrink-0 text-xs text-[var(--color-text-muted)]">{label}</span>
      <span
        className="cursor-pointer truncate text-right text-xs text-[var(--color-text)] hover:text-[var(--color-accent)]"
        title="Click to copy"
        onClick={() => navigator.clipboard.writeText(String(value))}
      >
        {value}
      </span>
    </div>
  );
}

export default function MediaViewer({ media, onClose, onPrev, onNext }: MediaViewerProps) {
  const fileUrl = getMediaFileUrl(media.file_path);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowLeft') onPrev();
      if (e.key === 'ArrowRight') onNext();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [onClose, onPrev, onNext]);

  return (
    <div
      className="fixed inset-0 z-[100] flex bg-black/90"
      onClick={onClose}
    >
      {/* Close button */}
      <button
        onClick={onClose}
        className="absolute right-4 top-4 z-10 rounded-full bg-black/50 p-2 text-white hover:bg-black/80 transition-colors"
      >
        ✕
      </button>

      {/* Prev/Next */}
      <button
        onClick={(e) => { e.stopPropagation(); onPrev(); }}
        className="absolute left-4 top-1/2 z-10 -translate-y-1/2 rounded-full bg-black/50 p-3 text-white hover:bg-black/80 transition-colors"
      >
        ←
      </button>
      <button
        onClick={(e) => { e.stopPropagation(); onNext(); }}
        className="absolute right-72 top-1/2 z-10 -translate-y-1/2 rounded-full bg-black/50 p-3 text-white hover:bg-black/80 transition-colors"
      >
        →
      </button>

      {/* Media display */}
      <div
        className="flex flex-1 items-center justify-center p-8"
        onClick={(e) => e.stopPropagation()}
      >
        {media.media_type === 'video' ? (
          <video
            src={fileUrl}
            controls
            autoPlay
            className="max-h-full max-w-full rounded-lg"
          />
        ) : (
          <img
            src={fileUrl}
            alt={media.file_name}
            className="max-h-full max-w-full rounded-lg object-contain"
          />
        )}
      </div>

      {/* Metadata sidebar */}
      <div
        className="w-72 shrink-0 overflow-y-auto border-l border-[var(--color-border)] bg-[var(--color-bg)] p-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="mb-3 text-sm font-semibold text-[var(--color-text)]">
          {media.file_name}
        </h3>

        <div className="space-y-3">
          <section>
            <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
              File Info
            </h4>
            <div className="divide-y divide-[var(--color-border)]">
              <MetadataRow label="Type" value={media.media_type} />
              <MetadataRow label="Size" value={formatFileSize(media.file_size)} />
              <MetadataRow
                label="Dimensions"
                value={media.width && media.height ? `${media.width} × ${media.height}` : null}
              />
              <MetadataRow label="Created" value={media.file_created_at ? new Date(media.file_created_at).toLocaleString() : null} />
            </div>
          </section>

          {media.checkpoint_name && (
            <section>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                Model
              </h4>
              <div className="divide-y divide-[var(--color-border)]">
                <MetadataRow label="Checkpoint" value={media.checkpoint_name} />
              </div>
            </section>
          )}

          {(media.sampler_name || media.scheduler || media.cfg_scale || media.steps || media.seed) && (
            <section>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                Sampler
              </h4>
              <div className="divide-y divide-[var(--color-border)]">
                <MetadataRow label="Sampler" value={media.sampler_name} />
                <MetadataRow label="Scheduler" value={media.scheduler} />
                <MetadataRow label="CFG" value={media.cfg_scale} />
                <MetadataRow label="Steps" value={media.steps} />
                <MetadataRow label="Seed" value={media.seed} />
              </div>
            </section>
          )}

          {media.lora_names && media.lora_names.length > 0 && (
            <section>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                LoRAs
              </h4>
              <div className="space-y-0.5">
                {media.lora_names.map((name) => (
                  <div key={name} className="rounded bg-[var(--color-surface)] px-2 py-1 text-xs text-[var(--color-text)]">
                    {name}
                  </div>
                ))}
              </div>
            </section>
          )}

          {media.positive_prompt && (
            <section>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                Positive Prompt
              </h4>
              <p
                className="cursor-pointer rounded bg-[var(--color-surface)] p-2 text-xs text-[var(--color-text)] hover:bg-[var(--color-surface-hover)]"
                onClick={() => navigator.clipboard.writeText(media.positive_prompt ?? '')}
                title="Click to copy"
              >
                {media.positive_prompt}
              </p>
            </section>
          )}

          {media.negative_prompt && (
            <section>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                Negative Prompt
              </h4>
              <p
                className="cursor-pointer rounded bg-[var(--color-surface)] p-2 text-xs text-[var(--color-text)] hover:bg-[var(--color-surface-hover)]"
                onClick={() => navigator.clipboard.writeText(media.negative_prompt ?? '')}
                title="Click to copy"
              >
                {media.negative_prompt}
              </p>
            </section>
          )}

          {media.metadata_prompt && (
            <section>
              <details>
                <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                  Raw Workflow JSON
                </summary>
                <pre className="mt-1 max-h-64 overflow-auto rounded bg-[var(--color-surface)] p-2 text-xs text-[var(--color-text)]">
                  {JSON.stringify(media.metadata_prompt, null, 2)}
                </pre>
              </details>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
