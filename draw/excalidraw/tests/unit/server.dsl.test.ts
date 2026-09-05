import { describe, expect, it } from 'vitest';
import { parseDSLToElements, getThinkingConfigFor, COLOR_PALETTE } from '../../dsl';

describe('parseDSLToElements', () => {
  it('RECT を rectangle 要素に変換する', () => {
    const [elem] = parseDSLToElements(['RECT|box1|10|20|140|70|blue|Hello']);
    expect(elem).toMatchObject({
      type: 'rectangle',
      id: 'box1',
      x: 10,
      y: 20,
      width: 140,
      height: 70,
      text: 'Hello',
      strokeColor: COLOR_PALETTE.blue.stroke,
      backgroundColor: COLOR_PALETTE.blue.fill,
    });
  });

  it('ELLIPSE / DIAMOND をそれぞれの shape type に変換する', () => {
    const [ellipse] = parseDSLToElements(['ELLIPSE|e1|0|0|100|50|green|']);
    const [diamond] = parseDSLToElements(['DIAMOND|d1|0|0|100|50|red|']);
    expect(ellipse.type).toBe('ellipse');
    expect(diamond.type).toBe('diamond');
  });

  it('TEXT をテキスト要素に変換する', () => {
    const [elem] = parseDSLToElements(['TEXT|txt1|5|5|18|dark|1 + 2 = 3']);
    expect(elem).toMatchObject({
      type: 'text',
      id: 'txt1',
      text: '1 + 2 = 3',
      fontSize: 18,
    });
  });

  it('DEL は delete マーカーに変換される（実際の要素削除はクライアント側が担当）', () => {
    const [elem] = parseDSLToElements(['DEL|box1,box2']);
    expect(elem).toEqual({ type: 'delete', ids: 'box1,box2' });
  });

  it('CLEAR は ids=* の delete マーカーに変換される', () => {
    const [elem] = parseDSLToElements(['CLEAR']);
    expect(elem).toEqual({ type: 'delete', ids: '*' });
  });

  it('未知のコマンドタイプは無視する', () => {
    const elements = parseDSLToElements(['UNKNOWN|foo|bar']);
    expect(elements).toEqual([]);
  });

  it('ARROW は同一コマンド配列内の既存要素IDを座標解決に使う', () => {
    const elements = parseDSLToElements([
      'RECT|box1|0|0|100|60|blue|A',
      'RECT|box2|300|0|100|60|blue|B',
      'ARROW|arr1|box1|box2|dark|',
    ]);
    const arrow = elements.find((e) => e.id === 'arr1');
    // box1 中心(50,30) -> box2 中心(350,30)
    expect(arrow.x).toBe(50);
    expect(arrow.y).toBe(30);
    expect(arrow.points).toEqual([[0, 0], [300, 0]]);
  });

  it('ARROW は座標指定 "x,y" 形式もサポートする', () => {
    const [arrow] = parseDSLToElements(['ARROW|arr1|0,0|100,50|dark|']);
    expect(arrow.x).toBe(0);
    expect(arrow.y).toBe(0);
    expect(arrow.points).toEqual([[0, 0], [100, 50]]);
  });

  it('elementMap を呼び出し間で共有すると、以前の呼び出しで作った要素も ARROW から参照できる', () => {
    const sharedMap = new Map<string, any>();
    parseDSLToElements(['RECT|box1|0|0|100|60|blue|A'], sharedMap);
    const [arrow] = parseDSLToElements(['ARROW|arr1|box1|500,0|dark|'], sharedMap);
    // box1 中心(50,30) が2回目の呼び出しでも解決できていること
    expect(arrow.x).toBe(50);
    expect(arrow.y).toBe(30);
  });

  it('同一IDのRECTを2回渡すと後勝ちで elementMap が更新される', () => {
    const elements = parseDSLToElements([
      'RECT|box1|0|0|100|60|blue|A',
      'RECT|box1|10|10|100|60|red|A-updated',
    ]);
    expect(elements).toHaveLength(2);
    expect(elements[1]).toMatchObject({ id: 'box1', x: 10, y: 10, backgroundColor: COLOR_PALETTE.red.fill });
  });
});

describe('parseDSLToElements の分岐カバレッジ（デフォルト値・不正入力）', () => {
  it('文字列でないコマンドや空文字コマンドは無視する', () => {
    const elements = parseDSLToElements([null as any, '   ', 'RECT|box1|0|0|10|10|blue|A']);
    expect(elements).toHaveLength(1);
    expect(elements[0].id).toBe('box1');
  });

  it('DEL は id 省略時 ids が空文字になる', () => {
    const [elem] = parseDSLToElements(['DEL']);
    expect(elem).toEqual({ type: 'delete', ids: '' });
  });

  it('RECT は全パラメータ省略時にデフォルト値を使う', () => {
    const [elem] = parseDSLToElements(['RECT']);
    expect(elem.id).toMatch(/^elem_/);
    expect(elem).toMatchObject({ type: 'rectangle', x: 100, y: 100, width: 140, height: 70 });
    expect(elem.backgroundColor).toBe(COLOR_PALETTE.blue.fill);
  });

  it('RECT は未知の色キー指定時 blue にフォールバックする', () => {
    const [elem] = parseDSLToElements(['RECT|box1|0|0|10|10|nosuchcolor|A']);
    expect(elem.backgroundColor).toBe(COLOR_PALETTE.blue.fill);
  });

  it('TEXT は全パラメータ省略時にデフォルト値を使う', () => {
    const [elem] = parseDSLToElements(['TEXT']);
    expect(elem.id).toMatch(/^txt_/);
    expect(elem).toMatchObject({ type: 'text', x: 100, y: 100, fontSize: 18, text: '' });
    expect(elem.strokeColor).toBe(COLOR_PALETTE.dark.stroke);
  });

  it('TEXT は未知の色キー指定時 dark にフォールバックする', () => {
    const [elem] = parseDSLToElements(['TEXT|t1|0|0|18|nosuchcolor|hi']);
    expect(elem.strokeColor).toBe(COLOR_PALETTE.dark.stroke);
  });

  it('ARROW は全パラメータ省略時にデフォルト値を使う', () => {
    const [elem] = parseDSLToElements(['ARROW']);
    expect(elem.id).toMatch(/^arr_/);
    expect(elem.strokeColor).toBe(COLOR_PALETTE.dark.stroke);
  });

  it('ARROW は未知の色キー指定時 dark にフォールバックする', () => {
    const [elem] = parseDSLToElements(['ARROW|a1|0,0|100,0|nosuchcolor|']);
    expect(elem.strokeColor).toBe(COLOR_PALETTE.dark.stroke);
  });

  it('ARROW は from/to が存在しないIDのとき原点付近のデフォルト座標になる', () => {
    const [elem] = parseDSLToElements(['ARROW|a1|missingFrom|missingTo|dark|']);
    expect(elem.x).toBe(0);
    expect(elem.y).toBe(0);
    expect(elem.points).toEqual([[0, 0], [100, 0]]);
  });

  it('ARROW の座標指定で x 部分が 0（falsy）のときは 100 にフォールバックする', () => {
    const [elem] = parseDSLToElements(['ARROW|a1|0,0|0,50|dark|']);
    // toRef "0,50" -> endX = Number('0') || 100 = 100
    expect(elem.points).toEqual([[0, 0], [100, 50]]);
  });

  it('ARROW の始点と終点の x が同じとき width は 1 にフォールバックする', () => {
    const [elem] = parseDSLToElements(['ARROW|a1|50,0|50,80|dark|']);
    expect(elem.width).toBe(1);
  });

  it('ARROW はラベル指定時に text を返す', () => {
    const [elem] = parseDSLToElements(['ARROW|a1|0,0|100,0|dark|接続']);
    expect(elem.text).toBe('接続');
  });

  it('LINE は矢頭なしの line 要素を返す', () => {
    const [elem] = parseDSLToElements(['LINE|l1|10,20|110,120|red|直線']);
    expect(elem.type).toBe('line');
    expect(elem.startArrowhead).toBeNull();
    expect(elem.endArrowhead).toBeNull();
    expect(elem.text).toBe('直線');
  });

  it('TRIANGLE は3点から閉じた line 要素（三角形）を生成する', () => {
    const [elem] = parseDSLToElements(['TRIANGLE|tri1|100,200|100,100|200,200|green|直角三角形']);
    expect(elem.type).toBe('line');
    expect(elem.x).toBe(100);
    expect(elem.y).toBe(100);
    expect(elem.width).toBe(100);
    expect(elem.height).toBe(100);
    expect(elem.text).toBe('直角三角形');
    expect(elem.points).toEqual([[0, 100], [0, 0], [100, 100], [0, 100]]);
  });

  it('POLYGON は4点以上の頂点から閉じた多角形（line要素）を生成する', () => {
    const [elem] = parseDSLToElements(['POLYGON|poly1|100,100|200,120|180,220|80,200|orange|傾いた四角形']);
    expect(elem.type).toBe('line');
    expect(elem.x).toBe(80);
    expect(elem.y).toBe(100);
    expect(elem.width).toBe(120);
    expect(elem.height).toBe(120);
    expect(elem.text).toBe('傾いた四角形');
    expect(elem.points).toEqual([
      [20, 0],
      [120, 20],
      [100, 120],
      [0, 100],
      [20, 0]
    ]);
  });

  it('RECT は angle（度数法・ラジアン）の回転プロパティをサポートする', () => {
    const [degElem] = parseDSLToElements(['RECT|r1|10|20|100|50|blue||45']);
    expect(degElem.angle).toBeCloseTo((45 * Math.PI) / 180, 5);

    const [radElem] = parseDSLToElements(['RECT|r2|10|20|100|50|blue||0.5']);
    expect(radElem.angle).toBe(0.5);
  });

  it('RECT および TEXT はカンマ区切りの座標形式をフォールバックパースする', () => {
    const [rect] = parseDSLToElements(['RECT|r1|200,100,120,80|yellow|ラベル|30']);
    expect(rect.x).toBe(200);
    expect(rect.y).toBe(100);
    expect(rect.width).toBe(120);
    expect(rect.height).toBe(80);
    expect(rect.text).toBe('ラベル');
    expect(rect.angle).toBeCloseTo((30 * Math.PI) / 180, 5);

    const [text] = parseDSLToElements(['TEXT|t1|150,250|20|dark|数式']);
    expect(text.x).toBe(150);
    expect(text.y).toBe(250);
    expect(text.fontSize).toBe(20);
    expect(text.text).toBe('数式');
  });
});

describe('getThinkingConfigFor', () => {
  it('flash 系モデルは thinkingBudget を 0 にする', () => {
    expect(getThinkingConfigFor('gemini-3.6-flash')).toEqual({ thinkingBudget: 0 });
    expect(getThinkingConfigFor('gemini-3.5-flash-lite')).toEqual({ thinkingBudget: 0 });
  });

  it('pro 系モデルは thinkingBudget を最小許容値(128)にする', () => {
    expect(getThinkingConfigFor('gemini-3.1-pro-preview')).toEqual({ thinkingBudget: 128 });
  });
});

describe('拡張 DSL 機能（スタイル・新形状・矢印・テキスト）', () => {
  it('拡張カラーパレット（pink, cyan, violet, lime, indigo）を解決できる', () => {
    const [p] = parseDSLToElements(['RECT|r1|0|0|100|100|pink|']);
    const [c] = parseDSLToElements(['RECT|r2|0|0|100|100|cyan|']);
    const [v] = parseDSLToElements(['RECT|r3|0|0|100|100|violet|']);
    const [l] = parseDSLToElements(['RECT|r4|0|0|100|100|lime|']);
    const [i] = parseDSLToElements(['RECT|r5|0|0|100|100|indigo|']);

    expect(p.backgroundColor).toBe(COLOR_PALETTE.pink.fill);
    expect(c.backgroundColor).toBe(COLOR_PALETTE.cyan.fill);
    expect(v.backgroundColor).toBe(COLOR_PALETTE.violet.fill);
    expect(l.backgroundColor).toBe(COLOR_PALETTE.lime.fill);
    expect(i.backgroundColor).toBe(COLOR_PALETTE.indigo.fill);
  });

  it('スタイル指定（dashed, hachure, round, strokeWidth, opacity）がRECTに適用される', () => {
    const [elem] = parseDSLToElements(['RECT|r1|10|20|100|50|blue|Box|0|dashed,hachure,round,w=4,opacity=75']);
    expect(elem.strokeStyle).toBe('dashed');
    expect(elem.fillStyle).toBe('hachure');
    expect(elem.roundness).toEqual({ type: 3 });
    expect(elem.strokeWidth).toBe(4);
    expect(elem.opacity).toBe(75);
  });

  it('CIRCLE コマンドで ellipse 要素を正円として生成できる', () => {
    const [elem] = parseDSLToElements(['CIRCLE|c1|200|150|60|green|円|dotted,dots']);
    expect(elem.type).toBe('ellipse');
    expect(elem.x).toBe(140); // 200 - 60
    expect(elem.y).toBe(90);  // 150 - 60
    expect(elem.width).toBe(120);
    expect(elem.height).toBe(120);
    expect(elem.text).toBe('円');
    expect(elem.strokeStyle).toBe('dotted');
    expect(elem.fillStyle).toBe('dots');
  });

  it('STAR コマンドで星型の閉じた多角形（line要素）を生成できる', () => {
    const [elem] = parseDSLToElements(['STAR|s1|100,100,50|yellow|Star|w=3']);
    expect(elem.type).toBe('line');
    expect(elem.points.length).toBeGreaterThan(10);
    // 最初の点と最後の点が閉じる
    expect(elem.points[0]).toEqual(elem.points[elem.points.length - 1]);
    expect(elem.strokeWidth).toBe(3);
    expect(elem.text).toBe('Star');
  });

  it('CLOUD コマンドで雲型のモコモコ形状（line要素）を生成できる', () => {
    const [elem] = parseDSLToElements(['CLOUD|cloud1|50|50|200|120|teal|クラウド|w=2']);
    expect(elem.type).toBe('line');
    expect(elem.width).toBeGreaterThan(0);
    expect(elem.height).toBeGreaterThan(0);
    expect(elem.text).toBe('クラウド');
    expect(elem.points.length).toBeGreaterThanOrEqual(16);
  });

  it('FRAME / CONTAINER コマンドで外枠と上部タイトルテキストが生成される', () => {
    const elements = parseDSLToElements(['FRAME|f1|50|50|300|200|gray|コンテナタイトル|dashed']);
    expect(elements).toHaveLength(2);

    const [frameBox, label] = elements;
    expect(frameBox.type).toBe('rectangle');
    expect(frameBox.strokeStyle).toBe('dashed');
    expect(frameBox.roundness).toEqual({ type: 3 });

    expect(label.type).toBe('text');
    expect(label.text).toBe('コンテナタイトル');
    expect(label.id).toBe('f1_label');
  });

  it('CARD コマンドで背景・タイトル・本文テキストが生成される', () => {
    const elements = parseDSLToElements(['CARD|c1|100|100|200|120|blue|タイトル|詳細な本文です']);
    expect(elements).toHaveLength(3);

    const [cardBox, titleElem, bodyElem] = elements;
    expect(cardBox.type).toBe('rectangle');
    expect(cardBox.roundness).toEqual({ type: 3 });
    expect(titleElem.type).toBe('text');
    expect(titleElem.text).toBe('タイトル');
    expect(bodyElem.type).toBe('text');
    expect(bodyElem.text).toBe('詳細な本文です');
  });

  it('BIARROW / ARROW2 で両端矢頭の arrow 要素が生成される', () => {
    const [elem] = parseDSLToElements(['BIARROW|ba1|0,0|100,50|red|双方向|w=3']);
    expect(elem.type).toBe('arrow');
    expect(elem.startArrowhead).toBe('arrow');
    expect(elem.endArrowhead).toBe('arrow');
    expect(elem.strokeWidth).toBe(3);
    expect(elem.text).toBe('双方向');
  });

  it('ELBOW コマンドでクランク状の直角折れ線矢印が生成される', () => {
    const [elem] = parseDSLToElements(['ELBOW|elb1|0,0|200,100|dark|ルーティング']);
    expect(elem.type).toBe('arrow');
    expect(elem.points.length).toBe(4);
    expect(elem.points[0]).toEqual([0, 0]);
    expect(elem.points[3]).toEqual([200, 100]);
    // 水平 -> 垂直 -> 水平 の経由点
    expect(elem.points[1]).toEqual([100, 0]);
    expect(elem.points[2]).toEqual([100, 100]);
  });

  it('POLYLINE コマンドで開いた複数点折れ線が生成される', () => {
    const [elem] = parseDSLToElements(['POLYLINE|poly1|0,0|50,80|100,20|150,100|purple|折れ線|dashed']);
    expect(elem.type).toBe('line');
    expect(elem.points).toHaveLength(4);
    expect(elem.strokeStyle).toBe('dashed');
    expect(elem.startArrowhead).toBeNull();
    expect(elem.endArrowhead).toBeNull();
  });

  it('TEXT コマンドでフォントやアライメント、スタイルが反映される', () => {
    const [elem] = parseDSLToElements(['TEXT|txt1|50|50|24|dark|見出し|font=mono,align=center,valign=middle']);
    expect(elem.type).toBe('text');
    expect(elem.fontFamily).toBe(3); // 3: Cascadia / mono
    expect(elem.textAlign).toBe('center');
    expect(elem.verticalAlign).toBe('middle');
  });

  it('GRID コマンドでグリッド・市松模様盤が生成される', () => {
    const elements = parseDSLToElements(['GRID|othello|100|100|400|400|8,8|#007B3E|#005A2B']);
    // 1 border + 64 cells = 65 elements
    expect(elements).toHaveLength(65);
    expect(elements[0].id).toBe('othello_board');
    expect(elements[1].type).toBe('rectangle');
    expect(elements[1].width).toBe(50);
    expect(elements[1].height).toBe(50);
  });

  it('CHESSBOARD コマンドで盤面・座標ラベル・全32駒が1コマンドで完全生成される', () => {
    const elements = parseDSLToElements(['CHESSBOARD|chess1|100|100|400']);
    // 1 wooden border + 16 coordinate labels + 64 cells + 32 pieces = 113 elements
    expect(elements).toHaveLength(113);
    
    // 木枠の確認
    const border = elements.find((e) => e.id === 'chess1_border');
    expect(border).toBeDefined();

    // マス目の確認 (a8, e1 などチェス座標ID)
    const a8Square = elements.find((e) => e.id === 'chess1_a8');
    expect(a8Square).toBeDefined();

    // 黒ポーン (♟) と白キング (♔) が配置されていること
    const blackPawn = elements.find((e) => e.text === '♟');
    expect(blackPawn).toBeDefined();

    const whiteKing = elements.find((e) => e.text === '♔');
    expect(whiteKing).toBeDefined();
  });

  it('MOVE / MOVE_BY コマンドが正しくパースされ、同一バッチ内の elementMap も更新される', () => {
    const sharedMap = new Map<string, any>();
    const elements = parseDSLToElements([
      'RECT|box1|100|100|100|50|blue|',
      'MOVE|box1|300,400',
      'MOVE_BY|box1|10,20',
    ], sharedMap);

    expect(elements).toHaveLength(3);
    expect(elements[1]).toEqual({ type: 'move', id: 'box1', x: 300, y: 400, isRelative: false });
    expect(elements[2]).toEqual({ type: 'move', id: 'box1', dx: 10, dy: 20, isRelative: true });
    expect(sharedMap.get('box1').x).toBe(310);
    expect(sharedMap.get('box1').y).toBe(420);
  });

  it('RESIZE / SCALE コマンドが正しくパースされる', () => {
    const elements = parseDSLToElements([
      'RECT|box1|100|100|100|50|blue|',
      'RESIZE|box1|200,80',
      'SCALE|box1|1.5',
    ]);
    expect(elements[1]).toEqual({ type: 'resize', id: 'box1', width: 200, height: 80, isScale: false });
    expect(elements[2]).toEqual({ type: 'resize', id: 'box1', scaleFactor: 1.5, isScale: true });
  });

  it('ROTATE / ROTATE_BY コマンドが正しくパースされる', () => {
    const elements = parseDSLToElements([
      'RECT|box1|100|100|100|50|blue|',
      'ROTATE|box1|45',
      'ROTATE_BY|box1|15',
    ]);
    expect(elements[1].type).toBe('rotate');
    expect(elements[1].angle).toBeCloseTo((45 * Math.PI) / 180);
    expect(elements[1].isRelative).toBe(false);

    expect(elements[2].type).toBe('rotate');
    expect(elements[2].angle).toBeCloseTo((15 * Math.PI) / 180);
    expect(elements[2].isRelative).toBe(true);
  });

  it('HIDE / SHOW コマンドが正しくパースされる', () => {
    const elements = parseDSLToElements([
      'HIDE|box1,box2',
      'SHOW|box1|80',
    ]);
    expect(elements[0]).toEqual({ type: 'hide', ids: 'box1,box2' });
    expect(elements[1]).toEqual({ type: 'show', ids: 'box1', opacity: 80 });
  });

  it('LET コマンドで変数定義および数式計算が展開される', () => {
    const [elem] = parseDSLToElements([
      'LET|baseX=100|baseW=120|theme=teal',
      'RECT|box1|{baseX + 50}|100|{baseW}|70|{theme}|Test',
    ]);
    expect(elem.x).toBe(150);
    expect(elem.width).toBe(120);
    expect(elem.backgroundColor).toBe(COLOR_PALETTE.teal.fill);
  });

  it('DEF / CALL コマンドでメソッド定義と呼び出しができる', () => {
    const elements = parseDSLToElements([
      'DEF|node(id, x, y, label)|RECT|{id}|{x}|{y}|100|50|blue|{label}',
      'CALL|node|n1|100|100|Start',
      'CALL|node|n2|250|100|End',
    ]);
    expect(elements).toHaveLength(2);
    expect(elements[0].id).toBe('n1');
    expect(elements[0].text).toBe('Start');
    expect(elements[1].id).toBe('n2');
    expect(elements[1].x).toBe(250);
  });

  it('FOR / REPEAT コマンドでループ展開ができる', () => {
    const elements = parseDSLToElements([
      'FOR|i|0..2|RECT|item_{i}|{100 + i * 120}|100|100|50|green|Item {i}',
    ]);
    expect(elements).toHaveLength(3);
    expect(elements[0].id).toBe('item_0');
    expect(elements[0].x).toBe(100);
    expect(elements[1].id).toBe('item_1');
    expect(elements[1].x).toBe(220);
    expect(elements[2].id).toBe('item_2');
    expect(elements[2].x).toBe(340);
  });

  it('CONNECT コマンドで連鎖矢印が一括生成される', () => {
    const elements = parseDSLToElements([
      'CONNECT|svc1 -> svc2 -> svc3|dark|HTTP;dashed',
    ]);
    expect(elements).toHaveLength(2);
    expect(elements[0].type).toBe('arrow');
    expect(elements[0].points).toBeDefined();
    expect(elements[0].text).toBe('HTTP');
    expect(elements[0].strokeStyle).toBe('dashed');
  });

  it('ROW / COL コマンドで要素が自動配置される', () => {
    const rowElements = parseDSLToElements([
      'ROW|x=100,y=200,gap=30|RECT|r1|0|0|100|50|blue|; RECT|r2|0|0|100|50|blue|',
    ]);
    expect(rowElements[0].x).toBe(100);
    expect(rowElements[1].x).toBe(230); // 100 + 100 + 30
    expect(rowElements[1].y).toBe(200);

    const colElements = parseDSLToElements([
      'COL|x=100,y=100,gap=20|RECT|c1|0|0|100|60|blue|; RECT|c2|0|0|100|60|blue|',
    ]);
    expect(colElements[0].y).toBe(100);
    expect(colElements[1].y).toBe(180); // 100 + 60 + 20
    expect(colElements[1].x).toBe(100);
  });

  it('Excalidraw MCP 連携コマンド (GROUP, UNGROUP, LINK, FRONT, BACK) がパースされる', () => {
    const elements = parseDSLToElements([
      'GROUP|grp_cards|card1,card2',
      'UNGROUP|card1',
      'LINK|btn1|https://github.com',
      'FRONT|top1,top2',
      'BACK|bg1',
    ]);
    expect(elements[0]).toEqual({ type: 'group', groupId: 'grp_cards', ids: 'card1,card2' });
    expect(elements[1]).toEqual({ type: 'ungroup', ids: 'card1' });
    expect(elements[2]).toEqual({ type: 'link', id: 'btn1', link: 'https://github.com' });
    expect(elements[3]).toEqual({ type: 'layer', ids: 'top1,top2', position: 'front' });
    expect(elements[4]).toEqual({ type: 'layer', ids: 'bg1', position: 'back' });
  });
});
