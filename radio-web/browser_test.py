"""ブラウザ自動テスト - UI とファイルダウンロード機能を検証"""

import asyncio
from playwright.async_api import async_playwright


async def test_ui_and_features():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        print("🌐 http://localhost:8000 にアクセス中...")
        await page.goto("http://localhost:8000", wait_until="networkidle", timeout=60000)
        await page.wait_for_load_state("domcontentloaded")

        # テスト 1: ジャンルリストが表示されているか
        print("\n✓ テスト 1: ジャンルリスト表示確認")
        genre_section = await page.query_selector(".db-sidebar-section:nth-child(2)")
        if genre_section:
            print("  ✅ ジャンルセクションが表示されている")
        else:
            print("  ❌ ジャンルセクションが見つかりません")

        # テスト 2: ジャンルを選択して番組一覧を表示
        print("\n✓ テスト 2: ジャンル選択と番組一覧確認")
        genre_links = await page.query_selector_all("a[href*='genre=']")
        if genre_links:
            print(f"  📚 {len(genre_links)} 個のジャンルが利用可能")
            # 最初のジャンルをクリック（"すべて"以外）
            if len(genre_links) > 1:
                await genre_links[1].click()
                await page.wait_for_load_state("networkidle")

                # 番組一覧が表示されたか確認
                program_cards = await page.query_selector_all(".program-card")
                if program_cards:
                    print(f"  ✅ {len(program_cards)} 個の番組カードが表示されている")

                    # テスト 3: 番組をクリックしてエピソード一覧を表示
                    print("\n✓ テスト 3: エピソード一覧表示確認")
                    await program_cards[0].click()
                    await page.wait_for_load_state("networkidle")

                    # エピソード一覧が表示されたか確認
                    episode_rows = await page.query_selector_all(".ep-row")
                    if episode_rows:
                        print(f"  ✅ {len(episode_rows)} 個のエピソードが表示されている")

                        # テスト 4: メニューボタンが表示されているか
                        print("\n✓ テスト 4: メニューボタン確認")
                        menu_buttons = await page.query_selector_all(".ep-menu-btn")
                        if menu_buttons:
                            print(f"  ✅ {len(menu_buttons)} 個のメニューボタン（⋮）が表示されている")

                            # メニューボタンをクリック
                            await menu_buttons[0].click()
                            await page.wait_for_timeout(500)

                            # コンテキストメニューが表示されたか
                            context_menu = await page.query_selector("#context-menu")
                            if context_menu:
                                is_visible = await context_menu.is_visible()
                                if is_visible:
                                    print("  ✅ コンテキストメニューが表示されている")
                                    # メニュー項目を確認
                                    menu_items = await context_menu.query_selector_all("li")
                                    print(f"  ℹ️  メニュー項目数: {len(menu_items)}")
                                else:
                                    print("  ⚠️  コンテキストメニューが非表示です")
                        else:
                            print("  ❌ メニューボタンが見つかりません")
                    else:
                        print("  ⚠️  エピソードが見つかりません")
                else:
                    print("  ⚠️  番組カードが見つかりません")

        # テスト 5: ダウンロード済みエピソードの確認
        print("\n✓ テスト 5: ダウンロード機能確認")
        saved_buttons = await page.query_selector_all("button.done")
        if saved_buttons:
            print(f"  ✅ {len(saved_buttons)} 個の「済」ボタンが表示されている")
        else:
            print("  ℹ️  現在ダウンロード済みエピソードがありません")

        # テスト 6: UI レイアウト確認
        print("\n✓ テスト 6: UI レイアウト確認")
        viewport = page.viewport_size
        if viewport:
            print(f"  📐 ビューポート: {viewport['width']}x{viewport['height']}")

        # ページのスクリーンショット取得
        print("\n📸 スクリーンショット保存中...")
        await page.screenshot(path="browser_test_screenshot.png")
        print("  ✅ browser_test_screenshot.png に保存されました")

        print("\n✅ ブラウザテスト完了！")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(test_ui_and_features())
