import { useCallback, useEffect, useState } from 'react';
import { getMedia, triggerScan } from './api/client';
import Header from './components/Header';
import FolderTree from './components/FolderTree';
import MediaGrid from './components/MediaGrid';
import MediaViewer from './components/MediaViewer';
import Pagination from './components/Pagination';
import type { MediaFile, MediaQuery, PaginationMeta } from './types/media';

export default function App() {
  const [items, setItems] = useState<MediaFile[]>([]);
  const [pagination, setPagination] = useState<PaginationMeta>({
    page: 1,
    per_page: 50,
    total: 0,
    total_pages: 0,
  });
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedMedia, setSelectedMedia] = useState<MediaFile | null>(null);
  const [page, setPage] = useState(1);

  const fetchMedia = useCallback(async () => {
    setLoading(true);
    try {
      const query: MediaQuery = {
        page,
        per_page: 50,
        sort_by: 'file_created_at',
        sort_order: 'desc',
      };
      if (selectedFolder) query.folder = selectedFolder;
      if (searchQuery) query.search = searchQuery;

      const data = await getMedia(query);
      setItems(data.items);
      setPagination(data.pagination);
    } catch (err) {
      console.error('Failed to fetch media:', err);
    } finally {
      setLoading(false);
    }
  }, [page, selectedFolder, searchQuery]);

  useEffect(() => {
    fetchMedia();
  }, [fetchMedia]);

  const handleScan = async () => {
    setScanning(true);
    try {
      await triggerScan();
      await fetchMedia();
    } catch (err) {
      console.error('Scan failed:', err);
    } finally {
      setScanning(false);
    }
  };

  const handleSearch = (query: string) => {
    setSearchQuery(query);
    setPage(1);
  };

  const handleSelectFolder = (folder: string | null) => {
    setSelectedFolder(folder);
    setPage(1);
  };

  const handleSelectMedia = (media: MediaFile) => {
    setSelectedMedia(media);
  };

  const handleCloseViewer = () => {
    setSelectedMedia(null);
  };

  const currentIndex = selectedMedia
    ? items.findIndex((m) => m.id === selectedMedia.id)
    : -1;

  const handlePrev = () => {
    if (currentIndex > 0) {
      setSelectedMedia(items[currentIndex - 1]);
    }
  };

  const handleNext = () => {
    if (currentIndex < items.length - 1) {
      setSelectedMedia(items[currentIndex + 1]);
    }
  };

  return (
    <div className="flex h-screen flex-col">
      <Header onSearch={handleSearch} onScan={handleScan} scanning={scanning} />

      <div className="flex flex-1 overflow-hidden">
        <FolderTree
          selectedFolder={selectedFolder}
          onSelectFolder={handleSelectFolder}
        />

        <main className="flex flex-1 flex-col overflow-y-auto">
          <MediaGrid
            items={items}
            loading={loading}
            onSelect={handleSelectMedia}
          />
          <Pagination pagination={pagination} onPageChange={setPage} />
        </main>
      </div>

      {selectedMedia && (
        <MediaViewer
          media={selectedMedia}
          onClose={handleCloseViewer}
          onPrev={handlePrev}
          onNext={handleNext}
        />
      )}
    </div>
  );
}
