import { describe, expect, it } from 'vitest';
import { mergeServerElements } from '../../src/mergeServerElements';

// 実際の @excalidraw/excalidraw の convertToExcalidrawElements はブラウザ実行を前提とした
// 初期化コードを含み Node の単体テスト環境では読み込めないため、
// テストでは最低限の既定値（version / versionNonce）を補うだけの軽量スタブを注入する。
const fakeConvert = (raw: any[]) => raw.map((el) => ({ version: 1, versionNonce: 1, ...el }));

describe('mergeServerElements', () => {
  it('既存要素が無い場合、新規要素をそのまま追加する', () => {
    const result = mergeServerElements([], [
      { type: 'rectangle', id: 'box1', x: 0, y: 0, width: 100, height: 60 },
    ], fakeConvert);
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({ id: 'box1', type: 'rectangle' });
  });

  it('同一IDの要素は上書きされ version が増える', () => {
    const existing = [{ id: 'box1', type: 'rectangle', x: 0, y: 0, version: 1 }];
    const result = mergeServerElements(existing, [
      { type: 'rectangle', id: 'box1', x: 50, y: 50, width: 100, height: 60 },
    ], fakeConvert);
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('box1');
    expect(result[0].x).toBe(50);
    expect(result[0].version).toBeGreaterThan(1);
  });

  it('近接位置のテキスト要素は重複排除され、新しい方だけが残る', () => {
    const existing = [{ id: 'txt-old', type: 'text', x: 100, y: 100, text: '1 + 2 =' }];
    const result = mergeServerElements(existing, [
      { type: 'text', id: 'txt-new', x: 105, y: 102, text: '1 + 2 = 3' },
    ], fakeConvert);
    const ids = result.map((e: any) => e.id);
    expect(ids).not.toContain('txt-old');
    expect(ids).toContain('txt-new');
  });

  it('離れた位置のテキスト要素は重複排除されず両方残る', () => {
    const existing = [{ id: 'txt-old', type: 'text', x: 0, y: 0, text: 'A' }];
    const result = mergeServerElements(existing, [
      { type: 'text', id: 'txt-new', x: 1000, y: 1000, text: 'B' },
    ], fakeConvert);
    const ids = result.map((e: any) => e.id);
    expect(ids).toContain('txt-old');
    expect(ids).toContain('txt-new');
  });

  it('type: delete の要素は対象IDをシーンから削除する', () => {
    const existing = [
      { id: 'box1', type: 'rectangle', x: 0, y: 0 },
      { id: 'box2', type: 'rectangle', x: 200, y: 0 },
    ];
    const result = mergeServerElements(existing, [
      { type: 'delete', ids: 'box1' },
    ], fakeConvert);
    const ids = result.map((e: any) => e.id);
    expect(ids).not.toContain('box1');
    expect(ids).toContain('box2');
  });

  it('type: delete で ids が無い場合は何も削除しない', () => {
    const existing = [{ id: 'box1', type: 'rectangle', x: 0, y: 0 }];
    const result = mergeServerElements(existing, [{ type: 'delete' }], fakeConvert);
    expect(result.map((e: any) => e.id)).toContain('box1');
  });

  it('type/id/x/y 省略時はデフォルト値で補完される', () => {
    const [elem] = mergeServerElements([], [{}], fakeConvert);
    expect(elem.type).toBe('rectangle');
    expect(elem.id).toMatch(/^elem_/);
    expect(elem.x).toBe(100);
    expect(elem.y).toBe(100);
  });

  it('roundness / points / endArrowhead が指定されればそのまま反映される', () => {
    const [elem] = mergeServerElements([], [
      { type: 'arrow', id: 'a1', roundness: { type: 3 }, points: [[0, 0], [5, 5]], endArrowhead: 'triangle' },
    ], fakeConvert);
    expect(elem.roundness).toEqual({ type: 3 });
    expect(elem.points).toEqual([[0, 0], [5, 5]]);
    expect(elem.endArrowhead).toBe('triangle');
  });

  it('arrow/line で points 省略時は width/height からデフォルトの points を組み立てる', () => {
    const [elem] = mergeServerElements([], [{ type: 'arrow', id: 'a2', width: 10, height: 20 }], fakeConvert);
    expect(elem.points).toEqual([[0, 0], [10, 20]]);
  });

  it('text 要素で text が無い場合 label.text → label(文字列) → "Text" の順にフォールバックする', () => {
    const [byLabelText] = mergeServerElements([], [{ type: 'text', id: 't1', label: { text: 'ラベル文字' } }], fakeConvert);
    expect(byLabelText.text).toBe('ラベル文字');

    const [byLabelString] = mergeServerElements([], [{ type: 'text', id: 't2', label: 'プレーンラベル' }], fakeConvert);
    expect(byLabelString.text).toBe('プレーンラベル');

    const [byDefault] = mergeServerElements([], [{ type: 'text', id: 't3' }], fakeConvert);
    expect(byDefault.text).toBe('Text');
  });

  it('text以外の要素で label オブジェクト指定時はフォントサイズ・色も反映される', () => {
    const [withFont] = mergeServerElements([], [
      { type: 'rectangle', id: 'r1', label: { text: 'ラベルA', fontSize: 20, strokeColor: '#111' } },
    ], fakeConvert);
    expect(withFont.label).toEqual({ text: 'ラベルA', fontSize: 20, strokeColor: '#111' });

    const [withDefaultFont] = mergeServerElements([], [{ type: 'rectangle', id: 'r2', label: { text: 'ラベルB' } }], fakeConvert);
    expect(withDefaultFont.label).toEqual({ text: 'ラベルB', fontSize: 16, strokeColor: '#1e1e1e' });
  });

  it('label が文字列で直接渡された場合もラベルとして反映される', () => {
    const [elem] = mergeServerElements([], [{ type: 'rectangle', id: 'r3', label: '直接文字列ラベル' }], fakeConvert);
    expect(elem.label).toEqual({ text: '直接文字列ラベル', fontSize: 16, strokeColor: '#1e1e1e' });
  });

  it('label.text が空文字なら label は付与されない', () => {
    const [elem] = mergeServerElements([], [{ type: 'rectangle', id: 'r4', label: { text: '' } }], fakeConvert);
    expect(elem.label).toBeUndefined();
  });

  it('text以外の要素で label が無く text だけある場合はそこからラベルを作る', () => {
    const [elem] = mergeServerElements([], [{ type: 'rectangle', id: 'r5', text: 'ただの文字列' }], fakeConvert);
    expect(elem.label).toEqual({ text: 'ただの文字列', fontSize: 16 });
  });

  it('型が異なる要素同士は近接していても重複排除されない', () => {
    const existing = [{ id: 'rectA', type: 'rectangle', x: 0, y: 0 }];
    const result = mergeServerElements(existing, [{ type: 'rectangle', id: 'rectB', x: 500, y: 500 }], fakeConvert);
    const ids = result.map((e: any) => e.id);
    expect(ids).toContain('rectA');
    expect(ids).toContain('rectB');
  });

  it('テキスト要素の座標が0でもフォールバック計算により重複排除される', () => {
    const existing = [{ id: 'txt-a', type: 'text', x: 0, y: 0, text: 'A' }];
    const result = mergeServerElements(existing, [{ type: 'text', id: 'txt-b', x: 0, y: 0, text: 'B' }], fakeConvert);
    const ids = result.map((e: any) => e.id);
    expect(ids).not.toContain('txt-a');
    expect(ids).toContain('txt-b');
  });

  it('既存要素に version が無い場合、上書き後は 2 になる', () => {
    const existing = [{ id: 'boxV', type: 'rectangle', x: 0, y: 0 }];
    const result = mergeServerElements(existing, [{ type: 'rectangle', id: 'boxV', x: 10, y: 10 }], fakeConvert);
    expect(result[0].version).toBe(2);
  });

  it('type: cameraUpdate はシーン要素に影響しない', () => {
    const existing = [{ id: 'box1', type: 'rectangle', x: 0, y: 0 }];
    const result = mergeServerElements(existing, [
      { type: 'cameraUpdate', x: 0, y: 0, zoom: 1 },
    ], fakeConvert);
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('box1');
  });

  it('angle と startArrowhead が指定された場合は正しく引き継ぐ', () => {
    const [elem] = mergeServerElements([], [
      { type: 'rectangle', id: 'rot1', angle: 0.785, startArrowhead: null },
    ], fakeConvert);
    expect(elem.angle).toBe(0.785);
    expect(elem.startArrowhead).toBeNull();
  });
});
