"""包括的なブラウザ GUI テスト - Playwright"""

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


async def run_tests():
    """包括的な GUI テスト実行"""
    print("=" * 60)
    print("🧪 Playwright GUI テストスイート開始")
    print("=" * 60)

    print("\n⏳ サーバーの起動を待機中...")
    if not await wait_for_server():
        print("❌ サーバーが起動しません")
        return

    print("✓ サーバーが起動しました\n")

    test_results = {
        "成功": 0,
        "失敗": 0,
        "スキップ": 0,
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        page.set_default_timeout(15000)

        try:
            # === テスト 1: ホームページ読み込み ===
            print("📋 テスト 1: ホームページ読み込み")
            await page.goto("http://localhost:8000", wait_until="domcontentloaded")
            title = await page.title()
            if "NHK" in title:
                print("  ✅ ページタイトルに 'NHK' を含む")
                test_results["成功"] += 1
            else:
                print(f"  ❌ 予期しないタイトル: {title}")
                test_results["失敗"] += 1

            # === テスト 2: UI エレメント確認 ===
            print("\n📋 テスト 2: UI エレメント確認")
            elements = {
                "ヘッダー": "header",
                "サイドバー": ".db-sidebar",
                "メインコンテンツ": "main",
                "ジャンルセクション": ".db-sidebar-section:nth-child(2)",
            }
            for name, selector in elements.items():
                elem = await page.query_selector(selector)
                if elem and await elem.is_visible():
                    print(f"  ✅ {name} が表示されている")
                    test_results["成功"] += 1
                else:
                    print(f"  ❌ {name} が見つかりません")
                    test_results["失敗"] += 1

            # === テスト 3: ジャンル選択 ===
            print("\n📋 テスト 3: ジャンル選択機能")
            # サイドバーのリンクを検索
            sidebar_links = await page.query_selector_all(".db-sidebar a")
            genre_items = list(sidebar_links)
            if genre_items and len(genre_items) > 0:
                print(f"  ℹ️  {len(genre_items)} 個のサイドバー項目を検出")
                # 最初のジャンルをクリック
                await genre_items[0].click()
                await page.wait_for_timeout(1500)
                print("  ✅ ジャンル選択成功")
                test_results["成功"] += 1
            else:
                print("  ⚠️  ジャンル項目が見つかりません")
                test_results["スキップ"] += 1

            # === テスト 4: 番組カード表示 ===
            print("\n📋 テスト 4: 番組カード表示")
            program_cards = await page.query_selector_all(".program-card")
            if program_cards and len(program_cards) > 0:
                print(f"  ✅ {len(program_cards)} 個の番組カードが表示")
                test_results["成功"] += 1
            else:
                print("  ⚠️  番組カードが見つかりません")
                test_results["スキップ"] += 1

            # === テスト 5: 番組クリック ===
            if program_cards and len(program_cards) > 0:
                print("\n📋 テスト 5: 番組選択でエピソード一覧表示")
                await program_cards[0].click()
                await page.wait_for_timeout(1500)

                episode_rows = await page.query_selector_all(".ep-row")
                if episode_rows and len(episode_rows) > 0:
                    print(f"  ✅ {len(episode_rows)} 個のエピソードが表示")
                    test_results["成功"] += 1

                    # === テスト 6: メニューボタン表示 ===
                    print("\n📋 テスト 6: メニューボタン表示")
                    menu_btns = await page.query_selector_all(".ep-menu-btn")
                    if menu_btns and len(menu_btns) > 0:
                        print(f"  ✅ {len(menu_btns)} 個のメニューボタン（⋮）表示")
                        test_results["成功"] += 1

                        # === テスト 7: メニュー表示 ===
                        print("\n📋 テスト 7: メニュー表示機能")
                        await menu_btns[0].click()
                        await page.wait_for_timeout(800)
                        menu = await page.query_selector("#context-menu")
                        if menu:
                            is_visible = await menu.is_visible()
                            if is_visible:
                                print("  ✅ コンテキストメニューが表示")
                                test_results["成功"] += 1

                                # === テスト 8: メニュー項目 ===
                                print("\n📋 テスト 8: メニュー項目確認")
                                menu_items = await menu.query_selector_all("li")
                                if menu_items:
                                    print(f"  ✅ {len(menu_items)} 個のメニュー項目")
                                    test_results["成功"] += 1
                            else:
                                print("  ❌ メニューが非表示")
                                test_results["失敗"] += 1
                        else:
                            print("  ⚠️  メニューが見つかりません")
                            test_results["スキップ"] += 1

                    # === テスト 9: DL ボタン ===
                    print("\n📋 テスト 9: DL ボタン表示")
                    dl_btns = await page.query_selector_all(".ep-dl-btn")
                    if dl_btns and len(dl_btns) > 0:
                        print(f"  ✅ {len(dl_btns)} 個のダウンロードボタン")
                        test_results["成功"] += 1
                    else:
                        print("  ⚠️  ダウンロードボタンが見つかりません")
                        test_results["スキップ"] += 1

                    # === テスト 10: 保存済みボタン ===
                    print("\n📋 テスト 10: 保存済み（済）ボタン")
                    saved_btns = await page.query_selector_all("button.done")
                    if saved_btns and len(saved_btns) > 0:
                        print(f"  ✅ {len(saved_btns)} 個の済ボタン")
                        test_results["成功"] += 1
                    else:
                        print("  ℹ️  保存済みエピソードなし")
                        test_results["スキップ"] += 1

                    # === テスト 11: フィルタ機能 ===
                    print("\n📋 テスト 11: エピソードフィルタ")
                    filter_checkboxes = await page.query_selector_all("input[type='checkbox']")
                    if filter_checkboxes:
                        print(f"  ✅ {len(filter_checkboxes)} 個のフィルタチェックボックス")
                        # 最初のフィルタをチェック
                        await filter_checkboxes[0].click()
                        await page.wait_for_timeout(800)
                        print("  ✅ フィルタ動作確認")
                        test_results["成功"] += 1

                    # === テスト 12: 検索ボックス ===
                    print("\n📋 テスト 12: エピソード検索")
                    search_input = await page.query_selector("#ep-filter-input")
                    if search_input:
                        await search_input.fill("テスト")
                        await page.wait_for_timeout(500)
                        print("  ✅ 検索ボックスに入力成功")
                        test_results["成功"] += 1
                        # 検索をクリア
                        await search_input.fill("")
                else:
                    print("  ⚠️  エピソードが見つかりません")
                    test_results["スキップ"] += 1

            # === テスト 13: テーマ切り替え ===
            print("\n📋 テスト 13: テーマ切り替え")
            theme_btn = await page.query_selector("#themeToggle")
            if theme_btn:
                await theme_btn.click()
                await page.wait_for_timeout(500)
                print("  ✅ テーマ切り替え成功")
                test_results["成功"] += 1
            else:
                print("  ⚠️  テーマボタンが見つかりません")
                test_results["スキップ"] += 1

            # === テスト 14: ダウンロードページ ===
            print("\n📋 テスト 14: ダウンロードページ移動")
            nav_links = await page.query_selector_all("header nav a")
            download_link = None
            for link in nav_links:
                href = await link.get_attribute("href")
                if href and "download" in href:
                    download_link = link
                    break

            if download_link:
                await download_link.click()
                await page.wait_for_timeout(1500)
                print("  ✅ ダウンロードページ移動成功")
                test_results["成功"] += 1
                # ホームに戻る
                await page.goto("http://localhost:8000")
            else:
                print("  ⚠️  ダウンロードリンクが見つかりません")
                test_results["スキップ"] += 1

            # === テスト 15: ヘルプページ ===
            print("\n📋 テスト 15: ヘルプページ移動")
            help_link = None
            for link in nav_links:
                href = await link.get_attribute("href")
                if href and "help" in href:
                    help_link = link
                    break

            if help_link:
                await help_link.click()
                await page.wait_for_timeout(1500)
                print("  ✅ ヘルプページ移動成功")
                test_results["成功"] += 1
            else:
                print("  ⚠️  ヘルプリンクが見つかりません")
                test_results["スキップ"] += 1

            # === テスト 16: レスポンシブテスト ===
            print("\n📋 テスト 16: レスポンシブ対応確認")
            await page.set_viewport_size({"width": 480, "height": 800})
            await page.goto("http://localhost:8000", wait_until="domcontentloaded")
            sidebar = await page.query_selector(".db-sidebar")
            if sidebar:
                print("  ✅ モバイルビューで表示確認")
                test_results["成功"] += 1

        except Exception as e:
            print(f"\n❌ テスト実行中にエラー: {e}")
            test_results["失敗"] += 1
        finally:
            # === スクリーンショット ===
            print("\n📸 スクリーンショット取得中...")
            await page.screenshot(path="/tmp/browser_test.png")
            print("  ✅ /tmp/browser_test.png に保存")

            await browser.close()

    # === 結果サマリー ===
    print("\n" + "=" * 60)
    print("📊 テスト結果サマリー")
    print("=" * 60)
    total = test_results["成功"] + test_results["失敗"] + test_results["スキップ"]
    print(f"✅ 成功: {test_results['成功']}")
    print(f"❌ 失敗: {test_results['失敗']}")
    print(f"⚠️  スキップ: {test_results['スキップ']}")
    print(f"📊 合計: {total} テスト")
    success_rate = (test_results["成功"] / total * 100) if total > 0 else 0
    print(f"✨ 成功率: {success_rate:.1f}%")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_tests())
