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
      strokeColor: COLOR_PALETTE.blue.stroke,
      backgroundColor: COLOR_PALETTE.blue.fill,
      label: { text: 'Hello' },
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

describe('getThinkingConfigFor', () => {
  it('flash 系モデルは thinkingBudget を 0 にする', () => {
    expect(getThinkingConfigFor('gemini-3.6-flash')).toEqual({ thinkingBudget: 0 });
    expect(getThinkingConfigFor('gemini-3.5-flash-lite')).toEqual({ thinkingBudget: 0 });
  });

  it('pro 系モデルは thinkingBudget を最小許容値(128)にする', () => {
    expect(getThinkingConfigFor('gemini-3.1-pro-preview')).toEqual({ thinkingBudget: 128 });
  });
});
