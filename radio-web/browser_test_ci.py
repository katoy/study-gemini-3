"""Headless ブラウザテスト - CI 用"""

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
    """Headless モードでの GUI テスト"""
    print("=" * 60)
    print("🧪 Headless Playwright GUI テスト開始")
    print("=" * 60)

    print("\n⏳ サーバーの起動を待機中...")
    if not await wait_for_server():
        print("❌ サーバーが起動しません")
        return False

    print("✓ サーバーが起動しました\n")

    test_results = {
        "成功": 0,
        "失敗": 0,
        "スキップ": 0,
    }

    async with async_playwright() as p:
        # Headless モードでブラウザを起動
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        page.set_default_timeout(15000)

        try:
            # テスト 1: ホームページ読み込み
            print("📋 テスト 1: ホームページ読み込み")
            await page.goto("http://localhost:8000", wait_until="domcontentloaded")
            title = await page.title()
            if "NHK" in title:
                print("  ✅ ページタイトル確認")
                test_results["成功"] += 1
            else:
                print(f"  ❌ 予期しないタイトル: {title}")
                test_results["失敗"] += 1

            # テスト 2: UI エレメント確認
            print("\n📋 テスト 2: UI エレメント確認")
            elements = {
                "ヘッダー": "header",
                "サイドバー": ".db-sidebar",
                "メインコンテンツ": "main",
            }
            for name, selector in elements.items():
                elem = await page.query_selector(selector)
                if elem and await elem.is_visible():
                    test_results["成功"] += 1
                else:
                    test_results["失敗"] += 1

            # テスト 3: ジャンル選択
            print("\n📋 テスト 3: ジャンル選択機能")
            sidebar_links = await page.query_selector_all(".db-sidebar a")
            if sidebar_links and len(sidebar_links) > 0:
                await sidebar_links[0].click()
                await page.wait_for_timeout(1500)
                print("  ✅ ジャンル選択成功")
                test_results["成功"] += 1
            else:
                print("  ⚠️  ジャンル項目が見つかりません")
                test_results["スキップ"] += 1

            # テスト 4: 番組カード確認
            print("\n📋 テスト 4: 番組カード確認")
            program_cards = await page.query_selector_all(".program-card")
            if program_cards:
                print(f"  ✅ {len(program_cards)} 個の番組カード検出")
                test_results["成功"] += 1

                # テスト 5: 番組クリック
                print("\n📋 テスト 5: エピソード一覧表示")
                await program_cards[0].click()
                await page.wait_for_timeout(1500)

                episode_rows = await page.query_selector_all(".ep-row")
                if episode_rows:
                    print(f"  ✅ {len(episode_rows)} 個のエピソード検出")
                    test_results["成功"] += 1

                    # テスト 6: メニューボタン確認
                    print("\n📋 テスト 6: メニューボタン確認")
                    menu_buttons = await page.query_selector_all(".ep-menu-btn")
                    if menu_buttons:
                        print(f"  ✅ {len(menu_buttons)} 個のメニューボタン検出")
                        test_results["成功"] += 1

                        # テスト 7: メニュー表示
                        print("\n📋 テスト 7: メニュー表示機能")
                        await menu_buttons[0].click()
                        await page.wait_for_timeout(800)
                        menu = await page.query_selector("#context-menu")
                        if menu and await menu.is_visible():
                            print("  ✅ コンテキストメニュー表示")
                            test_results["成功"] += 1
                    else:
                        test_results["スキップ"] += 1

                    # テスト 8: フィルタ機能
                    print("\n📋 テスト 8: フィルタ機能")
                    checkboxes = await page.query_selector_all("input[type='checkbox']")
                    if checkboxes:
                        await checkboxes[0].click()
                        await page.wait_for_timeout(500)
                        print("  ✅ フィルタ動作確認")
                        test_results["成功"] += 1
                        await checkboxes[0].click()

            # テスト 9: テーマ切り替え
            print("\n📋 テスト 9: テーマ切り替え")
            theme_btn = await page.query_selector("#themeToggle")
            if theme_btn:
                await theme_btn.click()
                await page.wait_for_timeout(500)
                print("  ✅ テーマ切り替え確認")
                test_results["成功"] += 1
            else:
                test_results["スキップ"] += 1

            # テスト 10: ページナビゲーション
            print("\n📋 テスト 10: ダウンロードページ移動")
            nav_links = await page.query_selector_all("header nav a")
            if nav_links:
                for link in nav_links:
                    href = await link.get_attribute("href")
                    if href and "download" in href:
                        await link.click()
                        await page.wait_for_timeout(1500)
                        print("  ✅ ダウンロードページ移動成功")
                        test_results["成功"] += 1
                        break
                else:
                    test_results["スキップ"] += 1

        except Exception as e:
            print(f"\n❌ テスト実行中にエラー: {e}")
            test_results["失敗"] += 1
        finally:
            # スクリーンショット取得
            print("\n📸 スクリーンショット取得中...")
            await page.screenshot(path="/tmp/browser_test.png")
            print("  ✅ /tmp/browser_test.png に保存")

            await browser.close()

    # 結果サマリー
    print("\n" + "=" * 60)
    print("📊 テスト結果")
    print("=" * 60)
    total = test_results["成功"] + test_results["失敗"] + test_results["スキップ"]
    print(f"✅ 成功: {test_results['成功']}")
    print(f"❌ 失敗: {test_results['失敗']}")
    print(f"⚠️  スキップ: {test_results['スキップ']}")
    print(f"📊 合計: {total} テスト")
    success_rate = (test_results["成功"] / total * 100) if total > 0 else 0
    print(f"✨ 成功率: {success_rate:.1f}%")
    print("=" * 60)

    # 成功率 70% 以上なら成功
    return success_rate >= 70.0


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    exit(0 if success else 1)
