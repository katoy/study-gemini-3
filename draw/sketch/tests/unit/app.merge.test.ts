import { describe, expect, it } from 'vitest';
import { mergeServerElements, defaultConverter } from '../../src/mergeServerElements';

describe('mergeServerElements for Sketch', () => {
  it('既存シーンに新しい要素を追加する', () => {
    const current = [{ id: 'box1', type: 'rectangle', x: 0, y: 0, width: 100, height: 50 }];
    const serverElems = [{ id: 'box2', type: 'oval', x: 150, y: 0, width: 80, height: 80 }];

    const result = mergeServerElements(current, serverElems, defaultConverter);
    expect(result).toHaveLength(2);
    expect(result.map((e) => e.id)).toEqual(['box1', 'box2']);
  });

  it('同一IDの要素は上書きされ、version がインクリメントされる', () => {
    const current = [{ id: 'box1', type: 'rectangle', x: 0, y: 0, width: 100, height: 50, version: 1 }];
    const serverElems = [{ id: 'box1', type: 'rectangle', x: 10, y: 20, width: 120, height: 60 }];

    const result = mergeServerElements(current, serverElems, defaultConverter);
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({
      id: 'box1',
      x: 10,
      y: 20,
      width: 120,
      height: 60,
      version: 2,
    });
  });

  it('DEL 形式の要素で指定されたIDを削除する', () => {
    const current = [
      { id: 'box1', type: 'rectangle', x: 0, y: 0 },
      { id: 'box2', type: 'rectangle', x: 100, y: 0 },
      { id: 'box3', type: 'rectangle', x: 200, y: 0 },
    ];
    const serverElems = [{ type: 'delete', ids: 'box1, box3' }];

    const result = mergeServerElements(current, serverElems, defaultConverter);
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('box2');

    // 全削除（ids: '*'）
    const cleared = mergeServerElements(current, [{ type: 'delete', ids: '*' }], defaultConverter);
    expect(cleared).toHaveLength(0);
  });

  it('cameraUpdate は無視される', () => {
    const current = [{ id: 'box1', type: 'rectangle', x: 0, y: 0 }];
    const serverElems = [{ type: 'cameraUpdate', x: 100, y: 100 }];

    const result = mergeServerElements(current, serverElems, defaultConverter);
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('box1');
  });

  it('近接する古いテキスト要素は重複排除される', () => {
    const current = [{ id: 'txt1', type: 'text', x: 100, y: 100, text: 'Old Title' }];
    const serverElems = [{ id: 'txt2', type: 'text', x: 105, y: 102, text: 'New Title' }];

    const result = mergeServerElements(current, serverElems, defaultConverter);
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe('txt2');
    expect(result[0].text).toBe('New Title');
  });

  it('points や arrowheads、angle、label を持つ要素を適切に変換する', () => {
    const serverElems = [
      {
        id: 'poly1',
        type: 'polygon',
        x: 10,
        y: 10,
        points: [[0, 0], [10, 0], [5, 10]],
        angle: 45,
        startArrowhead: null,
        endArrowhead: 'arrow',
        label: { text: 'Poly Label', fontSize: 14, strokeColor: '#123456' },
      },
      {
        id: 'line1',
        type: 'line',
        x: 0,
        y: 0,
        label: 'String Label',
      }
    ];

    const result = mergeServerElements([], serverElems, defaultConverter);
    expect(result).toHaveLength(2);
    expect(result[0].points).toEqual([[0, 0], [10, 0], [5, 10]]);
    expect(result[0].angle).toBe(45);
    expect(result[0].endArrowhead).toBe('arrow');
    expect(result[0].label?.text).toBe('Poly Label');
    expect(result[1].points).toEqual([[0, 0], [140, 70]]);
    expect(result[1].label?.text).toBe('String Label');
  });

  it('オセロの列ラベル (A〜H, 間隔60px) のように隣接するテキストは削除されず保持される', () => {
    const colLabels = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];
    let current: any[] = [];

    // アニメーションキューのように1つずつ追加
    colLabels.forEach((label, i) => {
      const newElem = [{ id: `col_${label}`, type: 'text', x: 155 + i * 60, y: 110, text: label }];
      current = mergeServerElements(current, newElem, defaultConverter);
    });

    expect(current).toHaveLength(8);
    expect(current.map((e) => e.text)).toEqual(['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']);
  });

  it('arrow/line の points や angle, label プロパティを正しく保持する', () => {
    const serverElems = [
      {
        type: 'arrow',
        id: 'arr1',
        x: 10,
        y: 20,
        width: 100,
        height: 50,
        angle: 0.5,
        startArrowhead: null,
        endArrowhead: 'arrow',
        label: { text: 'Flow', fontSize: 14, strokeColor: '#f97316' },
      },
      {
        type: 'rectangle',
        text: 'Card Box',
      },
    ];

    const result = mergeServerElements([], serverElems, defaultConverter);
    expect(result).toHaveLength(2);
    expect(result[0].endArrowhead).toBe('arrow');
    expect(result[0].angle).toBe(0.5);
    expect(result[0].label?.text).toBe('Flow');
    expect(result[1].label?.text).toBe('Card Box');
  });
});
