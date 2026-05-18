import { useEffect, useState } from 'react';
import { getFolderTree } from '../api/client';
import type { FolderNode } from '../types/media';

interface FolderTreeProps {
  selectedFolder: string | null;
  onSelectFolder: (folder: string | null) => void;
}

function FolderItem({
  node,
  depth,
  selectedFolder,
  onSelectFolder,
}: {
  node: FolderNode;
  depth: number;
  selectedFolder: string | null;
  onSelectFolder: (folder: string | null) => void;
}) {
  const [expanded, setExpanded] = useState(depth < 2);
  const isSelected = selectedFolder === node.path;
  const hasChildren = node.children.length > 0;

  return (
    <div>
      <button
        onClick={() => onSelectFolder(isSelected ? null : node.path)}
        className={`flex w-full items-center gap-1 rounded px-2 py-1 text-left text-sm transition-colors ${
          isSelected
            ? 'bg-[var(--color-accent)]/20 text-[var(--color-accent)]'
            : 'text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)]'
        }`}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
      >
        {hasChildren && (
          <span
            onClick={(e) => {
              e.stopPropagation();
              setExpanded(!expanded);
            }}
            className="cursor-pointer select-none"
          >
            {expanded ? '▾' : '▸'}
          </span>
        )}
        {!hasChildren && <span className="w-3" />}
        <span className="truncate">{node.name}</span>
        <span className="ml-auto text-xs text-[var(--color-text-muted)]">{node.file_count}</span>
      </button>
      {expanded &&
        hasChildren &&
        node.children.map((child) => (
          <FolderItem
            key={child.path}
            node={child}
            depth={depth + 1}
            selectedFolder={selectedFolder}
            onSelectFolder={onSelectFolder}
          />
        ))}
    </div>
  );
}

export default function FolderTree({ selectedFolder, onSelectFolder }: FolderTreeProps) {
  const [tree, setTree] = useState<FolderNode[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getFolderTree()
      .then(setTree)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <aside className="w-56 shrink-0 overflow-y-auto border-r border-[var(--color-border)] bg-[var(--color-bg)] p-2">
      <div className="mb-2 px-2 text-xs font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
        Folders
      </div>
      <button
        onClick={() => onSelectFolder(null)}
        className={`mb-1 flex w-full items-center rounded px-2 py-1 text-left text-sm transition-colors ${
          selectedFolder === null
            ? 'bg-[var(--color-accent)]/20 text-[var(--color-accent)]'
            : 'text-[var(--color-text-muted)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)]'
        }`}
      >
        All Files
      </button>
      {loading ? (
        <div className="px-2 text-sm text-[var(--color-text-muted)]">Loading...</div>
      ) : (
        tree.map((node) => (
          <FolderItem
            key={node.path}
            node={node}
            depth={0}
            selectedFolder={selectedFolder}
            onSelectFolder={onSelectFolder}
          />
        ))
      )}
    </aside>
  );
}
