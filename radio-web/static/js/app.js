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
