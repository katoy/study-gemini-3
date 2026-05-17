// テーマ、フォントサイズ、検索履歴、キーボードショートカット管理

// テーマ切替
function toggleTheme() {
  const html = document.documentElement;
  const current = html.getAttribute('data-theme') || 'light';
  const next = current === 'light' ? 'dark' : 'light';
  html.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  updateThemeButton();
}

function updateThemeButton() {
  const btn = document.getElementById('themeToggle');
  if (!btn) return;
  const current = document.documentElement.getAttribute('data-theme') || 'light';
  btn.textContent = current === 'dark' ? '☀️' : '🌙';
}

// 初期化時にボタンを更新
updateThemeButton();

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

// 検索履歴管理
function addToSearchHistory(query) {
  if (!query.trim()) return;
  let history = JSON.parse(localStorage.getItem('searchHistory') || '[]');
  history = history.filter(h => h !== query); // 重複削除
  history.unshift(query);
  if (history.length > 10) history = history.slice(0, 10); // 最大 10 件
  localStorage.setItem('searchHistory', JSON.stringify(history));
}

function getSearchHistory() {
  return JSON.parse(localStorage.getItem('searchHistory') || '[]');
}

// キーボードショートカット
document.addEventListener('keydown', function(e) {
  // / キーで検索ボックスにフォーカス
  if (e.key === '/') {
    e.preventDefault();
    const searchBox = document.querySelector('input[type="text"][placeholder*="検索"]');
    if (searchBox) searchBox.focus();
  }
  // ? or F1 キーでヘルプを表示
  if (e.key === '?' || e.key === 'F1') {
    e.preventDefault();
    // ヘルプページへナビゲート
    window.location.href = '/help';
  }
  // Esc キーでモーダルを閉じる
  if (e.key === 'Escape') {
    const modal = document.querySelector('.modal.show');
    if (modal) {
      modal.classList.remove('show');
    }
  }
  // g キーでジャンルセレクタにフォーカス
  if (e.key === 'g') {
    e.preventDefault();
    const genreSelect = document.querySelector('select');
    if (genreSelect) genreSelect.focus();
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

// === エピソードフィルタ・選択管理 ===
function filterEpisodes(searchText = null) {
  const filterInput = document.getElementById('ep-filter-input');
  const showSavedOnly = document.getElementById('show-saved-only')?.checked || false;
  const query = searchText !== null ? searchText : (filterInput?.value || '').toLowerCase();

  const tbody = document.getElementById('ep-tbody');
  if (!tbody) return;

  let visibleCount = 0;
  tbody.querySelectorAll('.ep-row').forEach(row => {
    const title = row.dataset.title?.toLowerCase() || '';
    const saved = parseInt(row.dataset.saved) || 0;

    const matchesQuery = !query || title.includes(query);
    const matchesSavedFilter = !showSavedOnly || saved === 1;
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
