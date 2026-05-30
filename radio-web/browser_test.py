"""ブラウザ自動テスト - Playwright で実行"""

import asyncio
import time
from playwright.async_api import async_playwright


async def wait_for_server(url="http://localhost:8000", timeout=30):
    """サーバーが起動するまで待機"""
    import urllib.request
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:
            await asyncio.sleep(0.5)
    return False


async def test_ui_and_features():
    """ブラウザ機能テスト"""
    print("⏳ サーバーの起動を待機中...")
    if not await wait_for_server():
        print("❌ サーバーが起動しません")
        return

    print("✓ サーバーが起動しました\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        page.set_default_timeout(15000)

        try:
            # ページ読み込み
            print("🌐 http://localhost:8000 にアクセス中...")
            await page.goto("http://localhost:8000", wait_until="domcontentloaded")
            print("✅ ページロード完了\n")

            # テスト 1: ジャンルリスト表示
            print("✓ テスト 1: UI レイアウト確認")
            genre_section = await page.query_selector(".db-sidebar-section:nth-child(2)")
            if genre_section:
                print("  ✅ ジャンルセクションが表示されている")
                visible = await genre_section.is_visible()
                print(f"  ✅ ジャンルセクションは可視状態: {visible}")
            else:
                print("  ❌ ジャンルセクションが見つかりません")

            # テスト 2: ジャンルをクリック
            print("\n✓ テスト 2: ジャンル選択")
            genre_links = await page.query_selector_all("a[href*='genre=']")
            if len(genre_links) > 1:
                print(f"  ✅ {len(genre_links)} 個のジャンルが利用可能")
                await genre_links[1].click()
                await page.wait_for_timeout(2000)
                print("  ✅ ジャンルをクリック完了")

                # テスト 3: 番組一覧確認
                print("\n✓ テスト 3: 番組一覧表示")
                program_cards = await page.query_selector_all(".program-card")
                if program_cards:
                    print(f"  ✅ {len(program_cards)} 個の番組カードが表示")

                    # テスト 4: 番組をクリック
                    print("\n✓ テスト 4: エピソード一覧表示")
                    await program_cards[0].click()
                    await page.wait_for_timeout(2000)

                    episode_rows = await page.query_selector_all(".ep-row")
                    if episode_rows:
                        print(f"  ✅ {len(episode_rows)} 個のエピソードが表示")

                        # テスト 5: メニューボタン確認
                        print("\n✓ テスト 5: メニューボタン確認")
                        menu_buttons = await page.query_selector_all(".ep-menu-btn")
                        if menu_buttons:
                            print(f"  ✅ {len(menu_buttons)} 個の⋮ボタンが表示")

                            # テスト 6: メニューをクリック
                            print("\n✓ テスト 6: コンテキストメニュー表示")
                            await menu_buttons[0].click()
                            await page.wait_for_timeout(1000)

                            context_menu = await page.query_selector("#context-menu")
                            if context_menu:
                                is_visible = await context_menu.is_visible()
                                print(f"  ✅ コンテキストメニューが表示: {is_visible}")
                        else:
                            print("  ❌ メニューボタンが見つかりません")
                    else:
                        print("  ⚠️  エピソードが見つかりません")
                else:
                    print("  ⚠️  番組が見つかりません")
            else:
                print("  ⚠️  ジャンルが見つかりません")

            # スクリーンショット
            print("\n📸 スクリーンショット取得中...")
            await page.screenshot(path="/tmp/browser_test.png")
            print("  ✅ /tmp/browser_test.png に保存されました")

            print("\n✅ ブラウザテスト完了！")

        except Exception as e:
            print(f"\n❌ テスト実行中にエラーが発生: {e}")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(test_ui_and_features())
