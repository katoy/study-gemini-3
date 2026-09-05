import { describe, expect, it } from 'vitest';
import { parseDSLToElements, getThinkingConfigFor, COLOR_PALETTE } from '../../dsl';

describe('parseDSLToElements for Sketch', () => {
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

  it('OVAL / ELLIPSE / DIAMOND をそれぞれの shape type に変換する', () => {
    const [oval] = parseDSLToElements(['OVAL|o1|0|0|100|50|green|']);
    const [ellipse] = parseDSLToElements(['ELLIPSE|e1|0|0|100|50|green|']);
    const [diamond] = parseDSLToElements(['DIAMOND|d1|0|0|100|50|red|']);
    expect(oval.type).toBe('oval');
    expect(ellipse.type).toBe('oval');
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

  it('DEL は delete マーカーに変換される', () => {
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

  it('TRIANGLE をポリゴン要素として変換する', () => {
    const [tri] = parseDSLToElements(['TRIANGLE|tri1|0,0|100,0|50,80|green|Label']);
    expect(tri.type).toBe('triangle');
    expect(tri.x).toBe(0);
    expect(tri.y).toBe(0);
    expect(tri.width).toBe(100);
    expect(tri.height).toBe(80);
    expect(tri.text).toBe('Label');
  });

  it('カンマ区切りRECT (x,y,w,h) を正しく解釈する', () => {
    const [elem] = parseDSLToElements(['RECT|box1|50,60,200,100|sketch|Card|45']);
    expect(elem).toMatchObject({
      type: 'rectangle',
      id: 'box1',
      x: 50,
      y: 60,
      width: 200,
      height: 100,
      text: 'Card',
      strokeColor: COLOR_PALETTE.sketch.stroke,
    });
    expect(elem.angle).toBeCloseTo((45 * Math.PI) / 180);
  });
});

describe('getThinkingConfigFor', () => {
  it('gemini-3 系モデルでは thinkingBudget: 0 を返す', () => {
    expect(getThinkingConfigFor('gemini-3.7-flash')).toEqual({ thinkingBudget: 0 });
    expect(getThinkingConfigFor('gemini-2.5-flash')).toEqual({ thinkingBudget: 0 });
  });

  it('非対象モデルでは undefined を返す', () => {
    expect(getThinkingConfigFor('gemini-1.5-pro')).toBeUndefined();
  });
});
