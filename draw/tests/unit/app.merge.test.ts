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

  it('type: cameraUpdate はシーン要素に影響しない', () => {
    const existing = [{ id: 'box1', type: 'rectangle', x: 0, y: 0 }];
    const result = mergeServerElements(existing, [
      { type: 'cameraUpdate', x: 0, y: 0, zoom: 1 },
    ], fakeConvert);
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('box1');
  });
});
