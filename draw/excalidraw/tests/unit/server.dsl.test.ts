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
