// テーマ、フォントサイズ、検索履歴、キーボードショートカット管理

// テーマ切替（後方互換性）
function toggleTheme() {
  const html = document.documentElement;
  const current = html.getAttribute('data-theme') || 'light';
  const next = current === 'light' ? 'dark' : 'light';
  html.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  updateThemeButton();
  setTimeout(() => updateThemeButton(), 50);
}

function updateThemeButton() {
  const btn = document.getElementById('themeToggle');
  if (!btn) return;
  const current = document.documentElement.getAttribute('data-theme') || 'light';
  btn.textContent = current === 'dark' ? '☀️' : '🌙';
}

// 初期化時にボタンを更新（モーダルベースの新UIではボタンが存在しないため、チェック）
if (document.getElementById('themeToggle')) {
  updateThemeButton();
}

function extractFilenameFromDisposition(contentDisposition) {
  let filename = 'download';
  if (!contentDisposition) {
    return filename;
  }

  const match5987 = contentDisposition.match(/filename\*=UTF-8''([^;\s]+)/);
  if (match5987) {
    try {
      return decodeURIComponent(match5987[1]);
    } catch (_err) {
      return match5987[1];
    }
  }

  const match = contentDisposition.match(/filename="?([^";\s]+)"?/);
  if (match) {
    return match[1];
  }

  return filename;
}

async function startDL(btn) {
  if (btn.disabled) return;
  btn.disabled = true;
  btn.textContent = '…';

  try {
    const resp = await fetch('/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        program: JSON.parse(btn.dataset.program),
        episode: JSON.parse(btn.dataset.episode),
      }),
    });
    const html = await resp.text();
    if (!resp.ok) {
      btn.textContent = '✗';
      btn.disabled = false;
      return;
    }

    const tmp = document.createElement('span');
    tmp.innerHTML = html;
    const node = tmp.firstElementChild || tmp;
    btn.replaceWith(node);
    htmx.process(node);
  } catch (err) {
    btn.textContent = '✗';
    btn.disabled = false;
  }
}

function triggerPendingAutoDownloads(root = document) {
  const searchRoot = root && typeof root.querySelectorAll === 'function' ? root : document;
  searchRoot.querySelectorAll('[data-auto-download-job-id]:not([data-auto-download-armed])').forEach((node) => {
    node.dataset.autoDownloadArmed = '1';
    const jobId = node.dataset.autoDownloadJobId;
    setTimeout(() => downloadFile(jobId), 100);
  });
}

async function downloadFile(jobId) {
  try {
    const resp = await fetch(`/api/download/${jobId}/file`);
    if (!resp.ok) {
      alert('ファイルダウンロードに失敗しました');
      return;
    }

    const blob = await resp.blob();
    const filename = extractFilenameFromDisposition(resp.headers.get('content-disposition'));
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  } catch (err) {
    console.error('ダウンロードエラー:', err);
    alert('ファイルダウンロードに失敗しました');
  }
}

async function downloadSavedEpisode(siteId, cornerId, episodeId, episodeDate, episodeTitle) {
  try {
    const resp = await fetch(`/api/episodes/${siteId}/${cornerId}/${episodeId}/file`);
    if (!resp.ok) {
      alert('ファイルダウンロードに失敗しました');
      return;
    }

    const blob = await resp.blob();
    const filename = extractFilenameFromDisposition(resp.headers.get('content-disposition'));
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  } catch (err) {
    console.error('ダウンロードエラー:', err);
    alert('ファイルダウンロードに失敗しました');
  }
}

let settingsBackup = { theme: 'auto', fontSize: 100, storageLimit: 10 };

async function openSettingsModal() {
  const modal = document.getElementById('settingsModal');
  if (!modal) return;

  const theme = localStorage.getItem('theme') || 'auto';
  const fontSize = localStorage.getItem('fontSize') || '100';
  let storageLimit = 10;

  try {
    const resp = await fetch('/api/settings');
    if (resp.ok) {
      const data = await resp.json();
      storageLimit = data.storage_limit_gb;
    }
  } catch (err) {
    console.error('設定の読み込みに失敗:', err);
  }

  settingsBackup = { theme, fontSize: parseInt(fontSize, 10), storageLimit };
  updateModalUI(theme, fontSize, storageLimit);
  modal.classList.add('show');
}

function closeSettingsModal() {
  const modal = document.getElementById('settingsModal');
  if (modal) {
    modal.classList.remove('show');
  }
}

function updateModalUI(theme, fontSize, storageLimit) {
  document.querySelectorAll('.radio-option[data-theme]').forEach((opt) => {
    const isSelected = opt.dataset.theme === theme;
    opt.classList.toggle('selected', isSelected);
    opt.querySelector('input').checked = isSelected;
  });

  const sliderValue = parseInt(fontSize, 10) || 100;
  const fontSizeSlider = document.getElementById('fontSizeSlider');
  if (fontSizeSlider) {
    fontSizeSlider.value = sliderValue;
  }
  updateFontSizeDisplay(sliderValue);

  const storageSlider = document.getElementById('storageLimitSlider');
  if (storageSlider) {
    const limitValue = Math.round(storageLimit || 10);
    storageSlider.value = limitValue;
    updateStorageLimitDisplay(limitValue);
  }
}

function updateFontSizeDisplay(sliderValue) {
  const display = document.getElementById('fontSizeDisplay');
  if (display) {
    display.textContent = `${sliderValue}%`;
  }
}

function updateStorageLimitDisplay(sliderValue) {
  const display = document.getElementById('storageLimitDisplay');
  if (display) {
    display.textContent = `${sliderValue} GB`;
  }
}

function handleStorageLimitChange(sliderValue) {
  const limitValue = parseInt(sliderValue, 10);
  updateStorageLimitDisplay(limitValue);
  settingsBackup.storageLimit = limitValue;
}

function handleFontSizeChange(sliderValue) {
  const percentage = parseInt(sliderValue, 10);
  const baseFontSize = 16;
  const newFontSize = (baseFontSize * percentage) / 100;
  localStorage.setItem('fontSize', percentage.toString());
  updateFontSizeDisplay(percentage);
  document.documentElement.style.fontSize = `${newFontSize}px`;
  settingsBackup.fontSize = percentage;
}

function applyTheme(theme) {
  localStorage.setItem('theme', theme);
  const html = document.documentElement;
  if (theme === 'auto') {
    const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    html.setAttribute('data-theme', dark ? 'dark' : 'light');
  } else {
    html.setAttribute('data-theme', theme);
  }
  settingsBackup.theme = theme;
}

function cancelSettings() {
  const { theme, fontSize, storageLimit } = settingsBackup;
  updateModalUI(theme, fontSize, storageLimit);
  applyTheme(theme);
  document.documentElement.style.fontSize = `${(16 * fontSize) / 100}px`;
  closeSettingsModal();
}

async function confirmSettings() {
  const slider = document.getElementById('storageLimitSlider');
  const storageLimit = parseInt(slider?.value || '10', 10);

  try {
    const resp = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ storage_limit_gb: storageLimit }),
    });
    if (!resp.ok) {
      alert('設定の保存に失敗しました');
      return;
    }
  } catch (err) {
    console.error('設定保存エラー:', err);
    alert('設定の保存に失敗しました');
    return;
  }

  closeSettingsModal();
}

// フォントサイズ変更
function setFontSize(size) {
  const html = document.documentElement;
  if (size === 'medium') {
    html.removeAttribute('data-font-size');
  } else {
    html.setAttribute('data-font-size', size);
  }
  localStorage.setItem('fontSize', size);
}

// 検索ヒストリードロップダウンの外部クリック閉じる
document.addEventListener('click', (e) => {
  const wrapper = document.getElementById('program-search')?.closest('.db-search-wrapper');
  if (!wrapper || !wrapper.contains(e.target)) {
    hideSearchHistory();
  }
});

// キーボードショートカット
document.addEventListener('keydown', function(e) {
  const isTextInput = e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA';
  const contentDiv = document.querySelector('.db-content');

  // / キーで検索ボックスにフォーカス（入力フィールド外のみ）
  if (e.key === '/' && !isTextInput) {
    e.preventDefault();
    const searchBox = document.getElementById('program-search');
    if (searchBox) searchBox.focus();
  }
  // ? or F1 キーでヘルプを表示（入力フィールド外のみ）
  if ((e.key === '?' || e.key === 'F1') && !isTextInput) {
    e.preventDefault();
    // ヘルプページへナビゲート
    window.location.href = '/help';
  }
  // Esc キーでモーダルを閉じる（全体で有効）
  if (e.key === 'Escape') {
    const modal = document.querySelector('.modal.show');
    if (modal) {
      modal.classList.remove('show');
    }
  }
  // g キーでジャンルセレクタにフォーカス（入力フィールド外のみ）
  if (e.key === 'g' && !isTextInput) {
    e.preventDefault();
    const genreSelect = document.querySelector('select');
    if (genreSelect) genreSelect.focus();
  }

  // === スクロール操作（入力フィールド外のみ） ===
  if (!isTextInput && contentDiv) {
    // 矢印キー（↑↓）でスクロール（1 行分）
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      contentDiv.scrollBy(0, -40);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      contentDiv.scrollBy(0, 40);
    }
    // SPACE でページダウン、Shift+SPACE でページアップ
    else if (e.code === 'Space') {
      e.preventDefault();
      const direction = e.shiftKey ? -1 : 1;
      contentDiv.scrollBy(0, direction * contentDiv.clientHeight * 0.8);
    }
  }
});

// キャッシュクリア
async function clearCache(scope = 'all') {
  if (!confirm(`キャッシュ（${scope}）をクリアします。よろしいですか？`)) {
    return;
  }
  try {
    const resp = await fetch(`/api/cache/clear?scope=${scope}`, {
      method: 'POST'
    });
    if (resp.ok || resp.status === 204) {
      alert('キャッシュをクリアしました。ページをリロードします。');
      location.reload();
    } else {
      alert('キャッシュクリアに失敗しました。');
    }
  } catch (err) {
    alert(`エラー: ${err.message}`);
  }
}

// === コンテキストメニュー処理 ===
let contextMenuTarget = null;

document.addEventListener('contextmenu', (e) => {
  const epRow = e.target.closest('.ep-row');
  if (!epRow) return;
  e.preventDefault();
  contextMenuTarget = epRow;
  showContextMenu(e.clientX, e.clientY);
});

document.addEventListener('click', (e) => {
  const menu = document.getElementById('context-menu');
  if (!menu) return;
  // メニュー外をクリックで閉じる
  if (!e.target.closest('.context-menu')) {
    menu.style.display = 'none';
  }
});

function showContextMenu(x, y) {
  const menu = document.getElementById('context-menu');
  if (!menu) return;
  menu.style.left = x + 'px';
  menu.style.top = y + 'px';
  menu.style.display = 'block';
}

document.getElementById('context-menu')?.addEventListener('click', (e) => {
  const action = e.target.closest('li')?.dataset.action;
  if (!action || !contextMenuTarget) return;

  const epData = contextMenuTarget.dataset.episode;
  const episode = epData ? JSON.parse(epData) : {};

  switch(action) {
    case 'open-nhk':
      if (episode.url) window.open(episode.url, '_blank');
      break;
    case 'copy-title':
      navigator.clipboard.writeText(episode.title || '');
      break;
    case 'copy-filename':
      const filename = (episode.title || 'episode').replace(/[\\/:*?"<>|]/g, '_') + '.m4a';
      navigator.clipboard.writeText(filename);
      break;
    case 'redownload':
      const progData = contextMenuTarget.dataset.program;
      const program = progData ? JSON.parse(progData) : {};
      if (!confirm(`「${episode.title}」を再ダウンロードしますか？`)) return;
      // DL ボタンをクリック
      const dlBtn = contextMenuTarget.querySelector('.ep-dl-btn');
      if (dlBtn && !dlBtn.disabled) startDL(dlBtn);
      break;
    case 'delete-file':
      if (!confirm(`「${episode.title}」を削除しますか？`)) return;
      deleteFile(episode);
      break;
  }

  document.getElementById('context-menu').style.display = 'none';
});

// === 番組名絞り込み ===
let _programSearchTimer = null;

function addToSearchHistory(query) {
  if (!query.trim()) return;
  let history = JSON.parse(localStorage.getItem('programSearchHistory') || '[]');
  history = history.filter(h => h !== query);
  history.unshift(query);
  if (history.length > 10) history = history.slice(0, 10);
  localStorage.setItem('programSearchHistory', JSON.stringify(history));
}

function getSearchHistory() {
  return JSON.parse(localStorage.getItem('programSearchHistory') || '[]');
}

function updateSearchClearButton() {
  const input = document.getElementById('program-search');
  const clearBtn = document.getElementById('program-search-clear');
  if (clearBtn) {
    clearBtn.style.display = input && input.value ? 'flex' : 'none';
  }
}

function clearSearchInput() {
  const input = document.getElementById('program-search');
  if (input) {
    input.value = '';
    input.focus();
    debounceSearchPrograms('');
    updateSearchClearButton();
    showSearchHistory();
  }
}

function showSearchHistory() {
  const input = document.getElementById('program-search');
  const historyDiv = document.getElementById('program-search-history');
  if (!historyDiv) return;

  const query = input?.value.trim() || '';
  const allHistory = getSearchHistory();
  const filtered = query
    ? allHistory.filter(h => h.toLowerCase().includes(query.toLowerCase()))
    : allHistory;

  if (filtered.length === 0) {
    historyDiv.style.display = 'none';
    return;
  }

  historyDiv.innerHTML = filtered.map(item =>
    `<div class="db-search-history-item" onclick="selectSearchHistoryItem('${item.replace(/'/g, "\\'")}')">
      <span class="db-search-history-icon">🕐</span>${item}
    </div>`
  ).join('');
  historyDiv.style.display = 'block';
}

function hideSearchHistory() {
  const historyDiv = document.getElementById('program-search-history');
  if (historyDiv) historyDiv.style.display = 'none';
}

function selectSearchHistoryItem(query) {
  const input = document.getElementById('program-search');
  if (input) {
    input.value = query;
    updateSearchClearButton();
    hideSearchHistory();
    debounceSearchPrograms(query);
    addToSearchHistory(query);
  }
}

function debounceSearchPrograms(value) {
  clearTimeout(_programSearchTimer);
  updateSearchClearButton();
  _programSearchTimer = setTimeout(() => {
    const genre = document.querySelector('.db-nav-item.active')?.dataset.genre || '';
    const q = value.trim();
    if (q) addToSearchHistory(q);
    const url = q
      ? `/programs?genre=${encodeURIComponent(genre)}&q=${encodeURIComponent(q)}`
      : `/programs?genre=${encodeURIComponent(genre)}`;
    htmx.ajax('GET', url, '#db-program-list');
  }, 300);
}

// === エピソードフィルタ・選択管理 ===
function setEpisodeFilter(type) {
  if (type === 'saved') {
    if (document.getElementById('filter-saved').checked) {
      document.getElementById('filter-unsaved').checked = false;
    }
  } else if (type === 'unsaved') {
    if (document.getElementById('filter-unsaved').checked) {
      document.getElementById('filter-saved').checked = false;
    }
  }
  filterEpisodes();
}

function filterEpisodes(searchText = null) {
  const filterInput = document.getElementById('ep-filter-input');
  const filterSaved = document.getElementById('filter-saved')?.checked || false;
  const filterUnsaved = document.getElementById('filter-unsaved')?.checked || false;
  const query = searchText !== null ? searchText : (filterInput?.value || '').toLowerCase();

  const tbody = document.getElementById('ep-tbody');
  if (!tbody) return;

  let visibleCount = 0;
  tbody.querySelectorAll('.ep-row').forEach(row => {
    const title = row.dataset.title?.toLowerCase() || '';
    const saved = parseInt(row.dataset.saved) || 0;

    const matchesQuery = !query || title.includes(query);
    // 保存済み チェック → 保存済みのみ表示
    // 未保存 チェック → 未保存のみ表示
    // 両方未チェック → 全表示
    let matchesSavedFilter = true;
    if (filterSaved) {
      matchesSavedFilter = saved === 1;
    } else if (filterUnsaved) {
      matchesSavedFilter = saved === 0;
    }
    const shouldShow = matchesQuery && matchesSavedFilter;

    row.style.display = shouldShow ? '' : 'none';
    if (shouldShow) visibleCount++;
  });

  // サマリー更新
  const summary = document.getElementById('ep-summary');
  if (summary) {
    const total = tbody.querySelectorAll('.ep-row').length;
    summary.textContent = `全 ${total} 件 / 表示 ${visibleCount} 件`;
  }

  updateSelectedCount();
}

function toggleSelectAll(checkbox) {
  const tbody = document.getElementById('ep-tbody');
  if (!tbody) return;
  tbody.querySelectorAll('.ep-checkbox').forEach(cb => {
    if (cb.closest('.ep-row').style.display !== 'none') {
      cb.checked = checkbox.checked;
    }
  });
  updateSelectedCount();
}

function updateSelectedCount() {
  const tbody = document.getElementById('ep-tbody');
  if (!tbody) return;
  const selected = tbody.querySelectorAll('.ep-checkbox:checked').length;
  const counter = document.getElementById('ep-selected-count');
  if (counter) {
    if (selected > 0) {
      counter.textContent = `${selected} 件選択`;
      counter.style.display = 'inline';
    } else {
      counter.style.display = 'none';
    }
  }
}

// === 一括ダウンロード ===
async function batchDownload() {
  const tbody = document.getElementById('ep-tbody');
  const epPanel = document.getElementById('episode-panel');
  if (!tbody || !epPanel) return;

  const selectedRows = tbody.querySelectorAll('.ep-row');
  const selectedCheckboxes = Array.from(tbody.querySelectorAll('.ep-checkbox:checked'));
  if (selectedCheckboxes.length === 0) {
    alert('エピソードを選択してください');
    return;
  }

  const episodes = selectedCheckboxes.map(cb => {
    const row = cb.closest('.ep-row');
    return JSON.parse(row.dataset.episode);
  });

  const programData = selectedRows[0]?.dataset.program;
  const program = programData ? JSON.parse(programData) : null;
  if (!program) {
    alert('プログラム情報が見つかりません');
    return;
  }

  try {
    const resp = await fetch('/download/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ program, episodes })
    });
    if (resp.ok) {
      // ジョブをクリア
      selectedCheckboxes.forEach(cb => cb.checked = false);
      updateSelectedCount();
      updateStatusMessage(`${episodes.length} 件のダウンロードを開始しました`);
    } else {
      alert('ダウンロード開始に失敗しました');
    }
  } catch (err) {
    alert(`エラー: ${err.message}`);
  }
}

// === ジョブ管理 ===
async function cancelJob(jobId) {
  if (!confirm('このジョブをキャンセルしますか？')) return;
  try {
    const resp = await fetch(`/api/download/${jobId}/cancel`, {
      method: 'POST'
    });
    if (resp.ok) {
      updateStatusMessage('ジョブをキャンセルしました');
    }
  } catch (err) {
    alert(`キャンセル失敗: ${err.message}`);
  }
}

async function deleteFile(episode) {
  try {
    const resp = await fetch('/api/file/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ episode })
    });
    if (resp.ok || resp.status === 204) {
      updateStatusMessage(`「${episode.title}」を削除しました`);
      setTimeout(() => location.reload(), 1000);
    } else {
      alert('削除に失敗しました');
    }
  } catch (err) {
    alert(`エラー: ${err.message}`);
  }
}

// === ステータスバー ===
function updateStatusMessage(msg) {
  const statusEl = document.getElementById('status-message');
  if (statusEl) {
    statusEl.textContent = msg;
    setTimeout(() => {
      statusEl.textContent = '準備完了';
    }, 3000);
  }
}

// === プレーヤーバー ===
function togglePlayback() {
  const btn = document.getElementById('player-play-btn');
  if (!btn) return;
  const isPlaying = btn.textContent === '⏸';
  btn.textContent = isPlaying ? '▶' : '⏸';
  // 実装は Phase D HLS streaming 統合時に実施
}

function closePlayer() {
  const playerBar = document.getElementById('player-bar');
  if (playerBar) {
    playerBar.style.display = 'none';
  }
}

async function loadProgramEpisodes(programId) {
  try {
    const response = await fetch(`/programs/${programId}/episodes`);
    if (!response.ok) return;

    const html = await response.text();
    const modal = document.createElement('div');
    modal.className = 'modal show';

    const content = document.createElement('div');
    content.className = 'modal-content modal-content-episode';
    content.style.cssText = 'position:relative;';
    content.innerHTML = html;

    const btn = document.createElement('button');
    btn.className = 'modal-close';
    btn.textContent = '✕';
    btn.onclick = () => modal.remove();

    content.appendChild(btn);
    modal.appendChild(content);
    modal.onclick = (e) => {
      if (e.target === modal) {
        modal.remove();
      }
    };
    document.body.appendChild(modal);
    htmx.process(content);
  } catch (err) {
    console.error('Failed to load episodes:', err);
  }
}

// === ダッシュボード: ビュー切替 ===
function setView(view, persist = true) {
  window.currentView = view;
  if (persist) localStorage.setItem('dbView', view);
  document.getElementById('view-list-btn')?.classList.toggle('active', view === 'list');
  document.getElementById('view-grid-btn')?.classList.toggle('active', view === 'grid');
  applyCurrentView();
}

function applyCurrentView() {
  const v = window.currentView || 'list';
  const listEl = document.getElementById('db-view-list');
  const gridEl = document.getElementById('db-view-grid');
  if (listEl) listEl.style.display = v === 'grid' ? 'none' : 'block';
  if (gridEl) gridEl.style.display = v === 'grid' ? 'grid' : 'none';
}

// === ダッシュボード: ソート機能 ===
let _currentSortColumn = null;
let _currentSortAscending = true;

function saveSortState() {
  localStorage.setItem('dbSortColumn', _currentSortColumn || '');
  localStorage.setItem('dbSortAscending', _currentSortAscending ? '1' : '0');
}

function loadSortState() {
  _currentSortColumn = localStorage.getItem('dbSortColumn') || null;
  _currentSortAscending = localStorage.getItem('dbSortAscending') !== '0';
}

function sortProgramList(column) {
  const listView = document.getElementById('db-view-list');
  if (!listView) return;

  const rows = Array.from(listView.querySelectorAll('.db-list-row'));
  if (rows.length === 0) return;

  // 同じ列をクリックしたら昇順/降順を反転、異なる列なら昇順で開始
  const isAscending = _currentSortColumn === column ? !_currentSortAscending : true;
  _currentSortColumn = column;
  _currentSortAscending = isAscending;

  applySortToRows(rows, column, isAscending);
  updateSortIndicators(column);
  saveSortState();
}

function applySortToRows(rows, column, isAscending) {
  rows.sort((a, b) => {
    let aVal, bVal;

    switch (column) {
      case 'number':
        aVal = parseInt(a.querySelector('.db-row-number')?.textContent || 0);
        bVal = parseInt(b.querySelector('.db-row-number')?.textContent || 0);
        break;
      case 'title':
        aVal = a.dataset.title || '';
        bVal = b.dataset.title || '';
        aVal = aVal.toLowerCase();
        bVal = bVal.toLowerCase();
        break;
      case 'genre':
        aVal = a.dataset.genre || '';
        bVal = b.dataset.genre || '';
        break;
      case 'date':
        aVal = a.dataset.date || '';
        bVal = b.dataset.date || '';
        break;
      default:
        return 0;
    }

    if (typeof aVal === 'string' && typeof bVal === 'string') {
      return isAscending ? aVal.localeCompare(bVal, 'ja') : bVal.localeCompare(aVal, 'ja');
    } else {
      return isAscending ? aVal - bVal : bVal - aVal;
    }
  });

  const listView = document.getElementById('db-view-list');
  if (listView) {
    rows.forEach(row => listView.appendChild(row));
  }
}

function updateSortIndicators(column) {
  const headers = document.querySelectorAll('.db-list-header-cell');
  headers.forEach(header => {
    const icon = header.querySelector('.sort-icon');
    if (icon) {
      icon.textContent = '';
      icon.classList.remove('active');
      if (header.onclick && header.onclick.toString().includes(`'${column}'`)) {
        icon.textContent = _currentSortAscending ? '▲' : '▼';
        icon.classList.add('active');
      }
    }
  });
}

function restoreSortAfterListUpdate() {
  if (!_currentSortColumn) return;
  const listView = document.getElementById('db-view-list');
  if (!listView) return;

  const rows = Array.from(listView.querySelectorAll('.db-list-row'));
  if (rows.length === 0) return;

  console.log('[DEBUG] Restoring sort:', _currentSortColumn, _currentSortAscending);
  // 保存されたソート状態を適用
  applySortToRows(rows, _currentSortColumn, _currentSortAscending);
  updateSortIndicators(_currentSortColumn);
}

// === ダッシュボード: ジャンルフィルタ ===
function filterByGenre(genre, navItem) {
  document.querySelectorAll('.db-nav-item').forEach(el => el.classList.remove('active'));
  if (navItem) navItem.classList.add('active');
  activateFilterChip(document.querySelector(`.db-filter-chip[data-genre="${genre}"]`), genre, false);
  const q = document.getElementById('program-search')?.value.trim() || '';
  const url = q
    ? `/programs?genre=${encodeURIComponent(genre)}&q=${encodeURIComponent(q)}`
    : `/programs?genre=${encodeURIComponent(genre)}`;
  htmx.ajax('GET', url, '#db-program-list');
}

// 左メニュー件数を更新
function updateGenreCount(genre, count) {
  const item = document.getElementById(`nav-${genre || 'all'}`);
  if (item) {
    const countSpan = item.querySelector('.db-nav-count');
    if (countSpan) {
      countSpan.textContent = count;
    }
  }
}

// 全プログラムから各ジャンルの件数を動的に計算
function updateAllGenreCounts() {
  // 全プログラムリスト（初期ロード時）から件数を計算
  const genreCount = {};
  const rows = document.querySelectorAll('.db-list-row');

  rows.forEach(row => {
    const genresAttr = row.dataset.genre || '';
    const genres = genresAttr.split(' ').filter(Boolean);
    genres.forEach(g => {
      genreCount[g] = (genreCount[g] || 0) + 1;
    });
  });

  // 注意：「すべて」の件数は更新しない（常に全番組数を保つ）
  // updateGenreCount('all', totalCount) は削除

  // 各ジャンルの件数を更新
  Object.entries(genreCount).forEach(([genre, count]) => {
    if (genre) {
      updateGenreCount(genre, count);
    }
  });

  console.log('[DEBUG] Genre counts updated from current list:', genreCount);
}

function activateFilterChip(chip, genre, triggerFetch = true) {
  document.querySelectorAll('.db-filter-chip').forEach(el => el.classList.remove('active'));
  if (chip) chip.classList.add('active');
  document.querySelectorAll('.db-nav-item').forEach(el => el.classList.remove('active'));
  const navItem = document.getElementById(`nav-${genre || 'all'}`);
  if (navItem) navItem.classList.add('active');
  if (triggerFetch) htmx.ajax('GET', `/programs?genre=${encodeURIComponent(genre)}`, '#db-program-list');
}

// === ダッシュボード: ステータスフィルタ ===
function filterByStatus(status) {
  document.querySelectorAll('.db-list-row, .db-grid-card').forEach(el => {
    const s = el.dataset.dlStatus || 'undl';
    el.style.display = (!status || s === status) ? '' : 'none';
  });
  updateVisibleCount();
}

// === ダッシュボード: 件数更新 ===
function updateVisibleCount(count = null) {
  const badge = document.getElementById('db-visible-count');
  if (!badge) return;
  if (count !== null) { badge.textContent = count; return; }
  const visible = Array.from(document.querySelectorAll('.db-list-row')).filter(r => r.style.display !== 'none').length;
  badge.textContent = visible;
}

// === ダッシュボード: 番組更新 ===
async function refreshPrograms() {
  const btn = document.querySelector('.db-refresh-btn');
  if (btn) { btn.textContent = '↻ 更新中…'; btn.disabled = true; }
  try { await fetch('/api/cache/clear?scope=programs', { method: 'POST' }); } catch(e) {}
  const genre = document.querySelector('.db-nav-item.active')?.dataset.genre || '';
  const q = document.getElementById('program-search')?.value.trim() || '';
  const url = q
    ? `/programs?genre=${encodeURIComponent(genre)}&q=${encodeURIComponent(q)}`
    : `/programs?genre=${encodeURIComponent(genre)}`;
  htmx.ajax('GET', url, '#db-program-list');
  setTimeout(() => { if (btn) { btn.textContent = '↻ 更新'; btn.disabled = false; } }, 1500);
}

// === ダッシュボード: サイドバードロワー ===
function toggleSidebar() {
  document.getElementById('db-sidebar')?.classList.toggle('drawer-open');
  document.getElementById('db-overlay')?.classList.toggle('show');
}

function closeSidebar() {
  document.getElementById('db-sidebar')?.classList.remove('drawer-open');
  document.getElementById('db-overlay')?.classList.remove('show');
}

// ページロード時に初期化
document.addEventListener('DOMContentLoaded', () => {
  triggerPendingAutoDownloads();
  document.querySelectorAll('.radio-option[data-theme]').forEach((opt) => {
    opt.addEventListener('click', function () {
      const input = this.querySelector('input');
      input.checked = true;
      applyTheme(input.value);
    });
  });

  if (document.getElementById('view-list-btn') || document.getElementById('view-grid-btn')) {
    setView(localStorage.getItem('dbView') || 'list', false);
  }

  loadSortState();
  console.log('[DEBUG] Loaded sort state:', _currentSortColumn, _currentSortAscending);
  updateAllGenreCounts();
  console.log('[DEBUG] Updated genre counts from current list');
});

document.addEventListener('htmx:afterSwap', (e) => {
  triggerPendingAutoDownloads(e.detail?.target || document);
});

// htmx がプログラムリストを更新した後、ソート状態を復元＋件数を更新
document.addEventListener('htmx:afterSettle', (e) => {
  const target = e.detail?.target;
  if (target && target.id === 'db-program-list') {
    console.log('[DEBUG] Program list updated via htmx');
    applyCurrentView();
    updateVisibleCount();
    restoreSortAfterListUpdate();
    updateAllGenreCounts();
  }
});

// === WebSocket ジョブリアルタイム更新 ===
(function() {
  const _jobsMap = {};

  function renderJobActivity() {
    const container = document.getElementById('db-activity-content');
    if (!container) return;
    const jobs = Object.values(_jobsMap).slice(-5).reverse();
    if (jobs.length === 0) {
      container.innerHTML = '<div class="activity-empty">実行中のジョブがありません</div>';
      return;
    }
    container.innerHTML = jobs.map(job => `
      <div class="job-row">
        <div class="job-title">${job.title}</div>
        <div class="job-status">${job.status === 'done' ? '✓ 完了' : job.status === 'downloading' ? '↓ DL中' : job.status === 'error' ? '✗ エラー' : '待機中'}</div>
      </div>
    `).join('');
  }

  function connectJobsWebSocket() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${location.host}/ws/jobs`);

    ws.onmessage = (e) => {
      const payload = JSON.parse(e.data);
      _jobsMap[payload.job_id] = payload;
      renderJobActivity();
    };

    ws.onclose = () => {
      setTimeout(connectJobsWebSocket, 3000);
    };

    ws.onerror = (err) => {
      console.error('WebSocket error:', err);
    };
  }

  document.addEventListener('DOMContentLoaded', connectJobsWebSocket);
})();
