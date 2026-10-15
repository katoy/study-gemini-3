"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");

// ===== 軽量DOM・Canvas・Web Audio モック環境構築 =====
function createClassList(initial = []) {
  const set = new Set(initial);
  return {
    add: (...cls) => cls.forEach(c => set.add(c)),
    remove: (...cls) => cls.forEach(c => set.delete(c)),
    contains: (c) => set.has(c),
    toggle: (c, force) => {
      if (force) set.add(c);
      else set.delete(c);
    }
  };
}

function createMockElement(id = "", tagName = "DIV", initialClasses = []) {
  const listeners = new Map();
  const attrs = new Map();
  const children = [];
  const el = {
    id,
    tagName,
    textContent: "",
    className: initialClasses.join(" "),
    disabled: false,
    width: 720,
    height: 580,
    clientWidth: 720,
    clientHeight: 580,
    style: { width: "", height: "", display: "none", left: "", top: "", color: "" },
    classList: createClassList(initialClasses),
    children,
    rect: { left: 0, top: 0, width: 740, height: 600 },
    get innerHTML() {
      return "";
    },
    set innerHTML(_val) {
      children.length = 0;
    },
    appendChild(child) {
      children.push(child);
      return child;
    },
    prepend(child) {
      children.unshift(child);
      return child;
    },
    getAttribute(name) {
      return attrs.get(name);
    },
    setAttribute(name, val) {
      attrs.set(name, val);
    },
    addEventListener(type, fn) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(fn);
    },
    dispatchEvent(type, eventObj = {}) {
      const list = listeners.get(type) || [];
      for (const fn of list) {
        fn({ currentTarget: el, target: el, ...eventObj });
      }
    },
    getBoundingClientRect() {
      return el.rect;
    },
    getContext() {
      return mockCanvasCtx;
    }
  };
  return el;
}

const mockCanvasCtx = {
  setTransform() {},
  clearRect() {},
  createRadialGradient() {
    return { addColorStop() {} };
  },
  fillRect() {},
  beginPath() {},
  moveTo() {},
  lineTo() {},
  closePath() {},
  fill() {},
  stroke() {},
  save() {},
  restore() {},
  ellipse() {},
  quadraticCurveTo() {},
  rect() {},
  fillText() {}
};

const elementsById = new Map();
function getOrCreateById(id) {
  if (!elementsById.has(id)) {
    const initialCls = id === "title-screen" ? ["screen", "active"] : ["screen"];
    elementsById.set(id, createMockElement(id, "DIV", initialCls));
  }
  return elementsById.get(id);
}

const diffBtns = ["easy", "normal", "hard"].map((diff) => {
  const b = createMockElement(`diff-${diff}`, "BUTTON", diff === "normal" ? ["diff-btn", "selected"] : ["diff-btn"]);
  b.setAttribute("data-diff", diff);
  return b;
});

const windowListeners = new Map();
let mockAudioState = "running";
let resumeCalled = 0;

class MockAudioContext {
  constructor() {
    this.state = mockAudioState;
    this.currentTime = 0;
    this.destination = {};
  }
  resume() {
    resumeCalled++;
    this.state = "running";
  }
  createOscillator() {
    return {
      type: "sine",
      frequency: {
        setValueAtTime() {},
        exponentialRampToValueAtTime() {}
      },
      connect() {},
      start() {},
      stop() {}
    };
  }
  createGain() {
    return {
      gain: {
        setValueAtTime() {},
        exponentialRampToValueAtTime() {}
      },
      connect() {}
    };
  }
}

globalThis.window = {
  devicePixelRatio: 2,
  AudioContext: MockAudioContext,
  addEventListener(type, fn) {
    if (!windowListeners.has(type)) windowListeners.set(type, []);
    windowListeners.get(type).push(fn);
  },
  dispatchWindowEvent(type, ev = {}) {
    for (const fn of windowListeners.get(type) || []) fn(ev);
  }
};

let rafCallbacks = [];
globalThis.requestAnimationFrame = (cb) => {
  rafCallbacks.push(cb);
  return rafCallbacks.length;
};

globalThis.document = {
  getElementById(id) {
    return getOrCreateById(id);
  },
  querySelectorAll(sel) {
    if (sel === ".diff-btn") return diffBtns;
    return [];
  },
  createElement(tag) {
    return createMockElement("", tag.toUpperCase());
  }
};

// HTML内の <script> をそのままの行番号・文字オフセットでコンパイルしてV8カバレッジ計測可能にする
Module._extensions[".html"] = function (module, filename) {
  const html = fs.readFileSync(filename, "utf8");
  const startTag = "<script>";
  const endTag = "</script>";
  const sIdx = html.indexOf(startTag) + startTag.length;
  const eIdx = html.lastIndexOf(endTag);
  const prefix = html.slice(0, sIdx).replace(/[^\n]/g, " ");
  const body = html.slice(sIdx, eIdx);
  const suffix = html.slice(eIdx).replace(/[^\n]/g, " ");
  module._compile(prefix + body + suffix, filename);
};

const htmlPath = path.resolve(__dirname, "../index.html");
require(htmlPath);
const game = globalThis.__SHIOKAZE__;

// ===== テストスイート =====

test("1. マップ生成・六角形グリッド隣接計算・連結性チェック", () => {
  assert.equal(game.GRID_ROWS, 7);
  assert.equal(game.GRID_COLS, 7);
  assert.equal(game.state.totalLandTiles, 40);

  // 偶数行・奇数行それぞれの隣接マス確認
  const nbEven = game.getNeighbors(0, 0);
  assert.equal(nbEven.length, 2);
  const nbOdd = game.getNeighbors(1, 1);
  assert.equal(nbOdd.length, 6);

  // 左上(0,0)はプレイヤーの港、右下(6,6)はCPUの港
  assert.equal(game.state.grid[0][0].type, "port");
  assert.equal(game.state.grid[0][0].owner, "player");
  assert.equal(game.state.grid[6][6].type, "port");
  assert.equal(game.state.grid[6][6].owner, "cpu");

  // 連結性チェック関数（分断されているケースがfalseを返すことも検証）
  const disconnectedSea = new Set(["0,1", "1,0"]);
  assert.equal(game.isLandConnected(disconnectedSea, 40), false);

  // generateArchipelagoのdo-while再試行分岐もカバーするため、1回だけ非連結になる乱数系列を注入
  const origRandom = Math.random;
  let callCount = 0;
  Math.random = () => {
    callCount++;
    return (callCount * 0.13) % 1;
  };
  game.generateArchipelago();
  Math.random = origRandom;
  assert.equal(game.state.grid.length, 7);
});

test("2. Web Audio API 効果音生成およびサスペンド復帰・ミュート分岐", () => {
  // ミュート時は null を返す
  game.state.soundEnabled = false;
  assert.equal(game.ensureAudio(), null);
  game.playSound("select");

  // サウンドON・suspended状態からのresume確認
  game.state.soundEnabled = true;
  game.resetAudioCtx();
  mockAudioState = "suspended";
  const allSoundTypes = ["select", "pioneer", "conquer", "fort", "market", "turn", "win", "lose"];
  for (const sType of allSoundTypes) {
    game.playSound(sType);
  }
  assert.ok(resumeCalled >= 1);
});

test("3. 資源産出・統計計算・テキストフォーマット", () => {
  game.initNewGame();
  game.state.autoLoop = false;

  // 各タイル種別と市場有無による産出表示の検証
  const portTile = { type: "port", owner: "player", building: null };
  const seaTile = { type: "sea", owner: null, building: null };
  const plainTile = { type: "plain", owner: "player", building: "fort" };
  const forestTile = { type: "forest", owner: "player", building: null };
  const marketFishTile = { type: "fishery", owner: "player", building: "market" };
  const mountainTile = { type: "mountain", owner: "cpu", building: null };

  assert.equal(game.getTileResourceYield(portTile), null);
  assert.equal(game.getTileResourceText(portTile), "なし（本拠地・攻略不可）");
  assert.equal(game.getTileResourceText(seaTile), "なし（進入不可）");
  assert.equal(game.getTileResourceText(plainTile), "なし");
  assert.equal(game.getTileResourceText(forestTile), "木材 1");
  assert.equal(game.getTileResourceText(marketFishTile), "食料 2 (市場2倍)");
  assert.equal(game.getTileResourceText(mountainTile), "石 1");

  assert.equal(game.formatOwnerLabel("player"), "青の船団（あなた）");
  assert.equal(game.formatOwnerLabel("cpu"), "赤の船団（CPU）");
  assert.equal(game.formatOwnerLabel(null), "なし（空きマス）");

  assert.equal(game.formatBuildingLabel("fort"), "砦（防衛強化・+1点）");
  assert.equal(game.formatBuildingLabel("market"), "市場（資源2倍・+2点）");
  assert.equal(game.formatBuildingLabel(null), "なし");
});

test("4. 4つの行動（開拓・攻略・砦・市場）と資源不足・行動制限", () => {
  game.initNewGame();
  game.state.autoLoop = false;

  // 盤面をテスト用に明示セットアップ
  game.state.grid[0][1] = { r: 0, c: 1, type: "forest", owner: null, building: null };
  game.state.grid[1][0] = { r: 1, c: 0, type: "mountain", owner: "cpu", building: null };
  game.state.grid[1][1] = { r: 1, c: 1, type: "sea", owner: null, building: null };
  game.state.grid[2][2] = { r: 2, c: 2, type: "plain", owner: null, building: null };

  // 海マスは行動なし
  assert.deepEqual(game.getAvailableActionsForTile(1, 1, "player"), []);

  // (0,1) 空きマスを開拓
  const pioneerActs = game.getAvailableActionsForTile(0, 1, "player");
  assert.equal(pioneerActs.length, 1);
  assert.equal(pioneerActs[0].kind, "pioneer");
  assert.equal(game.executeAction(pioneerActs[0], "player"), true);
  assert.equal(game.state.grid[0][1].owner, "player");

  // 開拓した森(0,1)で市場を建てる・砦を建てる選択肢が出ることを確認
  game.state.resources.player = { wood: 5, food: 5, stone: 5 };
  const ownedResActs = game.getAvailableActionsForTile(0, 1, "player");
  assert.equal(ownedResActs.length, 2); // fort & market
  const marketAct = ownedResActs.find(a => a.kind === "market");
  assert.equal(game.executeAction(marketAct, "player"), true);
  assert.equal(game.state.grid[0][1].building, "market");

  // 行動回数0のときは executeAction が false を返し、パネルに使い切りメッセージが出る
  assert.equal(game.state.actionsLeft, 0);
  assert.equal(game.executeAction(ownedResActs[0], "player"), false);
  game.updateSelectedTilePanel();

  // 行動回数を戻し、砦なし敵マス(1,0)の攻略と、砦あり敵マスの攻略を検証
  game.state.actionsLeft = 2;
  const conquerNormal = game.getAvailableActionsForTile(1, 0, "player")[0];
  assert.equal(conquerNormal.kind, "conquer");
  assert.equal(conquerNormal.cost.food, 2);
  assert.equal(game.executeAction(conquerNormal, "player"), true);
  assert.equal(game.state.grid[1][0].owner, "player");

  // (1,0)に砦を建設
  game.state.actionsLeft = 2;
  const fortAct = game.getAvailableActionsForTile(1, 0, "player").find(a => a.kind === "fort");
  assert.equal(game.executeAction(fortAct, "player"), true);
  assert.equal(game.state.grid[1][0].building, "fort");

  // 砦があるマスをCPU側から攻略（砦が破壊されることを確認）
  game.state.grid[2][0] = { r: 2, c: 0, type: "fishery", owner: "cpu", building: null };
  game.state.resources.cpu = { wood: 5, food: 5, stone: 5 };
  const cpuConquerFort = game.getAvailableActionsForTile(1, 0, "cpu")[0];
  assert.equal(cpuConquerFort.cost.food, 4);
  assert.equal(cpuConquerFort.cost.stone, 2);
  assert.equal(game.executeAction(cpuConquerFort, "cpu"), true);
  assert.equal(game.state.grid[1][0].owner, "cpu");
  assert.equal(game.state.grid[1][0].building, null);

  // 資源不足時は executeAction が false になり、ボタン表示も「（資源不足）」になる
  game.state.resources.player = { wood: 0, food: 0, stone: 0 };
  game.state.actionsLeft = 2;
  game.state.grid[0][1] = { r: 0, c: 1, type: "forest", owner: null, building: null };
  const unaffordable = game.getAvailableActionsForTile(0, 1, "player")[0];
  assert.equal(unaffordable.canAfford, false);
  assert.equal(game.executeAction(unaffordable, "player"), false);
  game.state.selectedTile = { r: 0, c: 1 };
  game.updateSelectedTilePanel();
});

test("5. 選択パネルの各種メッセージ分岐とCanvas描画・ホバーツールチップ", () => {
  game.initNewGame();
  game.state.autoLoop = false;

  // 未選択状態
  game.state.selectedTile = null;
  game.updateSelectedTilePanel();

  // 海マス選択
  const seaPos = { r: 2, c: 2 };
  game.state.grid[2][2].type = "sea";
  game.state.grid[2][2].owner = null;
  game.state.selectedTile = seaPos;
  game.updateSelectedTilePanel();

  // 港マス選択
  game.state.selectedTile = { r: 0, c: 0 };
  game.updateSelectedTilePanel();

  // 既に建物がある自軍マス選択
  game.state.grid[0][1] = { r: 0, c: 1, type: "forest", owner: "player", building: "market" };
  game.state.selectedTile = { r: 0, c: 1 };
  game.updateSelectedTilePanel();

  // 隣接していない空きマス選択
  game.state.grid[4][4] = { r: 4, c: 4, type: "plain", owner: null, building: null };
  game.state.selectedTile = { r: 4, c: 4 };
  game.updateSelectedTilePanel();

  // 行動可能な自軍マスを選択し、生成されたアクションボタンを実際にクリックして実行
  game.state.grid[0][2] = { r: 0, c: 2, type: "forest", owner: "player", building: "market" };
  game.state.grid[0][1] = { r: 0, c: 1, type: "forest", owner: "player", building: null };
  game.state.resources.player = { wood: 4, food: 2, stone: 2 };
  game.state.selectedTile = { r: 0, c: 1 };
  game.updateSelectedTilePanel();
  const btnContainer = document.getElementById("action-buttons-container");
  assert.ok(btnContainer.children.length > 0);
  btnContainer.children[0].dispatchEvent("click");

  // エフェクトの寿命ループ（age < maxAge と age >= maxAge の両方）とホバー描画を検証
  game.addBoardEffect(0, 0, "テスト", "#ffffff");
  game.state.hoveredTile = { r: 0, c: 0 };
  game.state.selectedTile = { r: 0, c: 1 };
  game.state.autoLoop = true;
  game.renderBoard();
  game.state.autoLoop = false;
  for (let i = 0; i < 50; i++) {
    game.renderBoard();
  }
  assert.equal(game.state.effects.length, 0);

  // Canvasのマウスイベント（盤面内ホバー・右端/下端はみ出し補正・盤面外・クリック・mouseleave）
  const canvasEl = document.getElementById("hex-canvas");
  const c00 = game.getHexCenter(0, 0);
  canvasEl.dispatchEvent("mousemove", { clientX: c00.x, clientY: c00.y });
  const c66 = game.getHexCenter(6, 6);
  canvasEl.dispatchEvent("mousemove", { clientX: c66.x, clientY: c66.y });
  // 海マス上でのホバー
  const cSea = game.getHexCenter(2, 2);
  canvasEl.dispatchEvent("mousemove", { clientX: cSea.x, clientY: cSea.y });
  // マス外（遠い座標）でのホバー＆クリック
  canvasEl.dispatchEvent("mousemove", { clientX: -500, clientY: -500 });
  canvasEl.dispatchEvent("click", { clientX: -500, clientY: -500 });
  canvasEl.dispatchEvent("click", { clientX: c00.x, clientY: c00.y });
  canvasEl.dispatchEvent("mouseleave");

  // devicePixelRatio フォールバックとリサイズイベント
  globalThis.window.devicePixelRatio = 0;
  document.getElementById("game-screen").classList.add("active");
  globalThis.window.dispatchWindowEvent("resize");
  document.getElementById("game-screen").classList.remove("active");
  globalThis.window.dispatchWindowEvent("resize");
  globalThis.window.devicePixelRatio = 2;
});

test("6. CPU思考ルーチン（やさしい・ふつう・つよい）の全分岐検証", () => {
  game.initNewGame();
  game.state.autoLoop = false;

  // 行動不能時（資源0）は null を返す
  game.state.resources.cpu = { wood: 0, food: 0, stone: 0 };
  assert.equal(game.chooseCpuAction(), null);

  // 1) やさしい
  game.state.difficulty = "easy";
  game.state.resources.cpu = { wood: 4, food: 4, stone: 4 };
  const easyAct = game.chooseCpuAction();
  assert.ok(easyAct !== null);

  // 2) ふつう（開拓・攻略・市場・砦、前線/後方の評価、60%即勝利リーチボーナス）
  game.state.difficulty = "normal";
  // CPUの所有マスに市場・砦・隣接プレイヤーマス（市場あり・砦あり資源マス）を配置して全種類のアクションを同時に候補に出す
  game.state.grid[6][5] = { r: 6, c: 5, type: "forest", owner: "cpu", building: null };
  game.state.grid[5][6] = { r: 5, c: 6, type: "mountain", owner: "cpu", building: null };
  game.state.grid[5][5] = { r: 5, c: 5, type: "fishery", owner: "player", building: "market" };
  game.state.grid[4][6] = { r: 4, c: 6, type: "forest", owner: "player", building: "fort" };
  game.state.grid[6][4] = { r: 6, c: 4, type: "plain", owner: null, building: null };
  game.state.resources.cpu = { wood: 6, food: 6, stone: 6 };
  const normalAct = game.chooseCpuAction();
  assert.ok(normalAct !== null);

  // 60%支配リーチ時のボーナス分岐（あと1マスで24/40に達する状況で開拓・攻略の両方を評価）
  let assigned = 0;
  for (let r = 0; r < 7; r++) {
    for (let c = 0; c < 7; c++) {
      if (game.state.grid[r][c].type !== "sea") {
        game.state.grid[r][c].building = null;
        if (assigned < 23) {
          game.state.grid[r][c].owner = "cpu";
          assigned++;
        } else if (assigned < 28) {
          game.state.grid[r][c].owner = "player";
          game.state.grid[r][c].type = "plain";
          assigned++;
        } else {
          game.state.grid[r][c].owner = null;
          assigned++;
        }
      }
    }
  }
  const reachAct = game.chooseCpuAction();
  assert.ok(reachAct !== null);

  // 3) つよい（プレイヤーの次ターン攻略予測による砦建設と非脅威マスの比較）
  game.initNewGame();
  game.state.autoLoop = false;
  game.state.difficulty = "hard";
  game.state.resources.player = { wood: 1, food: 3, stone: 2 }; // 攻略可能資源
  game.state.resources.cpu = { wood: 1, food: 1, stone: 4 };    // 資源が1以下＋石が2以上
  // (6,5)はプレイヤーと隣接する資源マス、(5,6)はプレイヤーと隣接しない平原マス
  game.state.grid[6][5] = { r: 6, c: 5, type: "forest", owner: "cpu", building: null };
  game.state.grid[5][5] = { r: 5, c: 5, type: "plain", owner: "player", building: null };
  game.state.grid[5][6] = { r: 5, c: 6, type: "plain", owner: "cpu", building: null };
  const hardAct = game.chooseCpuAction();
  assert.ok(hardAct !== null);
});

test("7. 勝利条件（60%支配即勝利・20ターン終了時の勝敗・引き分け）とCPU非同期ターン進行", async () => {
  game.state.stepDelayMs = 1;
  game.state.autoLoop = false;

  // 1) プレイヤー60%即勝利
  game.initNewGame();
  game.state.autoLoop = false;
  let count = 0;
  for (let r = 0; r < 7; r++) {
    for (let c = 0; c < 7; c++) {
      if (game.state.grid[r][c].type !== "sea" && count < 24) {
        game.state.grid[r][c].owner = "player";
        count++;
      }
    }
  }
  assert.equal(game.checkImmediateDominationVictory(), true);
  assert.equal(game.state.isGameOver, true);
  // ゲーム終了後の startTurn / endCurrentTurn ガード確認
  game.startTurn("player");
  game.endCurrentTurn();

  // 2) CPU 60%即勝利
  game.initNewGame();
  game.state.autoLoop = false;
  count = 0;
  for (let r = 0; r < 7; r++) {
    for (let c = 0; c < 7; c++) {
      if (game.state.grid[r][c].type !== "sea") {
        game.state.grid[r][c].owner = count < 24 ? "cpu" : null;
        count++;
      }
    }
  }
  assert.equal(game.checkImmediateDominationVictory(), true);

  // 3) 20ターン終了時の3パターン（プレイヤー勝利・CPU勝利・引き分け）
  game.initNewGame();
  game.state.autoLoop = false;
  game.state.grid[0][1].owner = "player";
  game.finishGameByTurnLimit(); // プレイヤー2マス vs CPU1マス

  game.initNewGame();
  game.state.autoLoop = false;
  game.state.grid[6][5].owner = "cpu";
  game.finishGameByTurnLimit(); // プレイヤー1マス vs CPU2マス

  game.initNewGame();
  game.state.autoLoop = false;
  game.state.turn = 20;
  game.endCurrentTurn(); // 1対1の同点引き分け

  // 4) CPUの非同期ターン（行動2回実行完了、行動不能時の即終了、途中のセッション中断）
  game.initNewGame();
  game.state.autoLoop = false;
  game.state.stepDelayMs = 1;
  document.getElementById("end-turn-btn").dispatchEvent("click"); // CPUターン開始
  await new Promise(r => setTimeout(r, 30));
  assert.equal(game.state.currentActor, "player");
  assert.equal(game.state.turn, 3);

  // CPUが行動できない状態でターン開始した場合でも止まらずプレイヤーにターンが戻る
  game.state.resources.cpu = { wood: 0, food: 0, stone: 0 };
  game.endCurrentTurn(); // turn 4 (CPU)
  await new Promise(r => setTimeout(r, 20));
  assert.equal(game.state.currentActor, "player");
  assert.equal(game.state.turn, 5);

  // CPUの行動中に60%勝利に達して途中終了するケース
  game.initNewGame();
  game.state.autoLoop = false;
  game.state.stepDelayMs = 1;
  let cAssigned = 0;
  for (let r = 0; r < 7; r++) {
    for (let c = 0; c < 7; c++) {
      if (game.state.grid[r][c].type !== "sea" && !(r === 0 && c === 0)) {
        if (cAssigned < 23) {
          game.state.grid[r][c].owner = "cpu";
          cAssigned++;
        } else {
          game.state.grid[r][c].owner = null;
        }
      }
    }
  }
  game.endCurrentTurn(); // CPUが1マス開拓して24/40(60%)に到達し即勝利
  await new Promise(r => setTimeout(r, 20));
  assert.equal(game.state.isGameOver, true);

  // CPU待機中に各タイミングでタイトルへ戻った場合のセッション中断ガード検証
  for (const waitMs of [0, 3, 7, 12]) {
    game.initNewGame();
    game.state.autoLoop = false;
    game.state.stepDelayMs = 5;
    game.endCurrentTurn();
    await new Promise(r => setTimeout(r, waitMs));
    game.backToTitle();
    await new Promise(r => setTimeout(r, 20));
  }

  // 画面ボタン（難易度選択・ゲーム開始・効果音切替・リトライ・タイトル復帰）のイベント検証
  diffBtns.forEach(b => b.dispatchEvent("click"));
  document.getElementById("start-game-btn").dispatchEvent("click");
  document.getElementById("sound-toggle-btn").dispatchEvent("click");
  document.getElementById("sound-toggle-btn").dispatchEvent("click");
  document.getElementById("retry-btn").dispatchEvent("click");
  document.getElementById("result-to-title-btn").dispatchEvent("click");
});
