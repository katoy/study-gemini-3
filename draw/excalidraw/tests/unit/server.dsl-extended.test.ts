import { describe, expect, it } from 'vitest';
import {
  resolveColor,
  parseStyleProps,
  evaluateSimpleMath,
  interpolateTemplate,
  parseDSLToElements,
  preprocessDSL,
  resolveAnchor,
} from '../../dsl';

describe('dsl.ts extended coverage', () => {
  describe('resolveColor & parseStyleProps', () => {
    it('resolveColor のフォールバックと純白ヘックスの暗色ストローク', () => {
      const fb = { fill: '#123456', stroke: '#654321' };
      expect(resolveColor('', fb)).toEqual(fb);
      expect(resolveColor('#ffffff')).toEqual({ fill: '#ffffff', stroke: '#1e1e1e' });
      expect(resolveColor('#fff')).toEqual({ fill: '#ffffff', stroke: '#1e1e1e' });
      expect(resolveColor('#aabbcc')).toEqual({ fill: '#aabbcc', stroke: '#aabbcc' });
      expect(resolveColor('unknownColor', fb)).toEqual(fb);
    });

    it('parseStyleProps の各種スタイル指定を網羅パースする', () => {
      expect(parseStyleProps('')).toEqual({});
      expect(parseStyleProps(undefined)).toEqual({});

      // solid=fill, stroke=solid, fill=solid, crosshatch, fill=dots, etc.
      const p1 = parseStyleProps('solid=fill,stroke=solid,crosshatch,rough=2,opacity=80,w4');
      expect(p1.fillStyle).toBe('cross-hatch');
      expect(p1.strokeStyle).toBe('solid');
      expect(p1.roughness).toBe(2);
      expect(p1.opacity).toBe(80);
      expect(p1.strokeWidth).toBe(4);

      const p2 = parseStyleProps('solid,fill=solid,fill=cross-hatch,fill=dots,roundness=1,virgil');
      expect(p2.strokeStyle).toBe('solid');
      expect(p2.fillStyle).toBe('dots');
      expect(p2.roundness).toEqual({ type: 3 });
      expect(p2.fontFamily).toBe(1);

      const p3 = parseStyleProps('sharp,roundness=none,sans,valign=top,start=none,end=none,arrowhead=both');
      expect(p3.roundness).toBeNull();
      expect(p3.fontFamily).toBe(2);
      expect(p3.verticalAlign).toBe('top');
      expect(p3.startArrowhead).toBe('arrow');
      expect(p3.endArrowhead).toBe('arrow');

      const p4 = parseStyleProps('mono,left,verticalalign=middle,start=arrow,end=arrow,both');
      expect(p4.fontFamily).toBe(3);
      expect(p4.textAlign).toBe('left');
      expect(p4.verticalAlign).toBe('middle');
      expect(p4.startArrowhead).toBe('arrow');
      expect(p4.endArrowhead).toBe('arrow');

      const p5 = parseStyleProps('font=1,align=right,valign=bottom,double');
      expect(p5.fontFamily).toBe(1);
      expect(p5.textAlign).toBe('right');
      expect(p5.verticalAlign).toBe('bottom');
      expect(p5.startArrowhead).toBe('arrow');
      expect(p5.endArrowhead).toBe('arrow');

      const p6 = parseStyleProps('font=2,textalign=center,strokewidth=3,width=5');
      expect(p6.fontFamily).toBe(2);
      expect(p6.textAlign).toBe('center');
      expect(p6.strokeWidth).toBe(5);

      const p7 = parseStyleProps('font=3,fontfamily=virgil,hand,center');
      expect(p7.fontFamily).toBe(1);
      expect(p7.textAlign).toBe('center');

      const p8 = parseStyleProps('code,helvetica,right');
      expect(p8.fontFamily).toBe(2);
      expect(p8.textAlign).toBe('right');

      const p9 = parseStyleProps('cascadia');
      expect(p9.fontFamily).toBe(3);
    });
  });

  describe('evaluateSimpleMath & interpolateTemplate', () => {
    it('evaluateSimpleMath の例外処理と構文エラー', () => {
      expect(evaluateSimpleMath('1 /')).toBeNaN();
      expect(evaluateSimpleMath('(((')).toBeNaN();
      expect(evaluateSimpleMath('abc')).toBeNaN();
    });

    it('interpolateTemplate で変数なしの純粋計算式', () => {
      const result = interpolateTemplate('{10 + 20}', {});
      expect(result).toBe('30');
    });

    it('interpolateTemplate で未定義変数はプレースホルダーのまま維持', () => {
      const result = interpolateTemplate('{foo_bar}', {});
      expect(result).toBe('{foo_bar}');
    });
  });

  describe('preprocessDSL: REPEAT & ROW/COL with CIRCLE', () => {
    it('REPEAT ループを展開する', () => {
      const commands = preprocessDSL(['REPEAT|3|RECT|r_{i}|{i * 100}|50|80|40|teal|R{i}']);
      expect(commands).toHaveLength(3);
      expect(commands[0]).toContain('r_0|0|50|80|40|teal|R0');
      expect(commands[1]).toContain('r_1|100|50|80|40|teal|R1');
      expect(commands[2]).toContain('r_2|200|50|80|40|teal|R2');
    });

    it('ROW および COL で CIRCLE や未知コマンドをオートレイアウトする', () => {
      const rowCmds = preprocessDSL([
        'ROW|x=10,y=20,gap=15|CIRCLE|c1|||30|green|C1;UNKNOWN|u1'
      ]);
      expect(rowCmds[0]).toBe('CIRCLE|c1|40|50|30|green|C1');
      expect(rowCmds[1]).toBe('UNKNOWN|u1');

      const colCmds = preprocessDSL([
        'COL|x=10,y=20,gap=15|CIRCLE|c2|||30|green|C2'
      ]);
      expect(colCmds[0]).toBe('CIRCLE|c2|40|50|30|green|C2');
    });
  });

  describe('parseDSLToElements: フォールバック構文と各種操作', () => {
    it('空行や非文字列入力をスキップする', () => {
      const elements = parseDSLToElements(['', '   ', null as any, undefined as any]);
      expect(elements).toHaveLength(0);
    });

    it('MOVE_BY / RESIZE / SCALE で elementMap が同期更新される', () => {
      const map = new Map<string, any>();
      map.set('box1', { id: 'box1', x: 100, y: 100, width: 50, height: 50 });

      const elements = parseDSLToElements([
        'MOVE_BY|box1|10,20',
        'RESIZE|box1|80|60',
        'SCALE|box1|2',
      ], map);

      expect(elements).toHaveLength(3);
      expect(map.get('box1').x).toBe(110);
      expect(map.get('box1').y).toBe(120);
      expect(map.get('box1').width).toBe(160);
      expect(map.get('box1').height).toBe(120);
    });

    it('RESIZE のカンマ区切り座標指定', () => {
      const elements = parseDSLToElements(['RESIZE|box2|120,90']);
      expect(elements[0]).toMatchObject({ type: 'resize', id: 'box2', width: 120, height: 90 });
    });

    it('RECT のカンマ座標 TYPE|id|x,y|width|height|color|label|angle|styles 形式', () => {
      const [r1] = parseDSLToElements(['RECT|r1|50,60|120|80|red|Label|0|solid']);
      expect(r1.x).toBe(50);
      expect(r1.y).toBe(60);
      expect(r1.width).toBe(120);
      expect(r1.height).toBe(80);

      const [r2] = parseDSLToElements(['RECT|r2|50,60|yellow|Label2']);
      expect(r2.x).toBe(50);
      expect(r2.y).toBe(60);
      expect(r2.text).toBe('Label2');
    });

    it('CIRCLE のカンマ座標指定', () => {
      const [c] = parseDSLToElements(['CIRCLE|c1|100,120,40|orange|Center|solid']);
      expect(c.x).toBe(60);
      expect(c.y).toBe(80);
      expect(c.width).toBe(80);
      expect(c.height).toBe(80);
    });

    it('ELLIPSE のカンマ座標指定（4要素, 2要素, 幅高さ別）', () => {
      const [e1] = parseDSLToElements(['ELLIPSE|e1|10,20,100,50|cyan|El1|0|dashed']);
      expect(e1.x).toBe(10);
      expect(e1.y).toBe(20);
      expect(e1.width).toBe(100);
      expect(e1.height).toBe(50);

      const [e2] = parseDSLToElements(['ELLIPSE|e2|30,40|120|60|lime|El2|0|solid']);
      expect(e2.x).toBe(30);
      expect(e2.y).toBe(40);
      expect(e2.width).toBe(120);
      expect(e2.height).toBe(60);

      const [e3] = parseDSLToElements(['ELLIPSE|e3|50,60|pink|El3']);
      expect(e3.x).toBe(50);
      expect(e3.y).toBe(60);
    });

    it('DIAMOND のカンマ座標指定', () => {
      const [d1] = parseDSLToElements(['DIAMOND|d1|10,20,80,80|yellow|D1']);
      expect(d1.x).toBe(10);
      expect(d1.y).toBe(20);
      expect(d1.width).toBe(80);

      const [d2] = parseDSLToElements(['DIAMOND|d2|30,40|70|70|teal|D2']);
      expect(d2.x).toBe(30);
      expect(d2.y).toBe(40);

      const [d3] = parseDSLToElements(['DIAMOND|d3|50,60|blue|D3']);
      expect(d3.x).toBe(50);
      expect(d3.y).toBe(60);
    });

    it('STAR のカンマ座標指定', () => {
      const [s1] = parseDSLToElements(['STAR|s1|100,100,40|yellow|Star1']);
      expect(s1.type).toBe('line');
      expect(s1.width).toBeGreaterThan(50);

      const [s2] = parseDSLToElements(['STAR|s2|50,50,80,80|orange|Star2']);
      expect(s2.type).toBe('line');

      const [s3] = parseDSLToElements(['STAR|s3|60,60|100|100|red|Star3']);
      expect(s3.type).toBe('line');

      const [s4] = parseDSLToElements(['STAR|s4|70,70|purple|Star4']);
      expect(s4.type).toBe('line');
    });

    it('CLOUD のカンマ座標指定', () => {
      const c1 = parseDSLToElements(['CLOUD|cl1|20,30,120,60|blue|Cloud1']);
      expect(c1.length).toBeGreaterThan(0);

      const c2 = parseDSLToElements(['CLOUD|cl2|40,50|140|70|cyan|Cloud2']);
      expect(c2.length).toBeGreaterThan(0);

      const c3 = parseDSLToElements(['CLOUD|cl3|60,70|teal|Cloud3']);
      expect(c3.length).toBeGreaterThan(0);
    });

    it('FRAME のカンマ座標指定', () => {
      const [f1] = parseDSLToElements(['FRAME|fr1|10,10,300,200|dark|Frame1']);
      expect(f1.x).toBe(10);
      expect(f1.y).toBe(10);
      expect(f1.width).toBe(300);

      const [f2] = parseDSLToElements(['FRAME|fr2|20,20|200|150|gray|Frame2']);
      expect(f2.x).toBe(20);
      expect(f2.y).toBe(20);

      const [f3] = parseDSLToElements(['FRAME|fr3|30,30|dark|Frame3']);
      expect(f3.x).toBe(30);
      expect(f3.y).toBe(30);
    });

    it('CARD のカンマ座標指定', () => {
      const [card1] = parseDSLToElements(['CARD|cd1|10,10,200,100|blue|Title1|Body1']);
      expect(card1.x).toBe(10);
      expect(card1.y).toBe(10);
      expect(card1.width).toBe(200);

      const [card2] = parseDSLToElements(['CARD|cd2|20,20|180|90|green|Title2|Body2']);
      expect(card2.x).toBe(20);
      expect(card2.y).toBe(20);

      const [card3] = parseDSLToElements(['CARD|cd3|30,30|yellow|Title3|Body3']);
      expect(card3.x).toBe(30);
      expect(card3.y).toBe(30);
    });

    it('TRIANGLE のカンマ座標指定（3頂点およびバリエーション）', () => {
      const [t1] = parseDSLToElements(['TRIANGLE|tr1|10,10,100,10,50,90|red|Tri1']);
      expect(t1.type).toBe('line');

      const [t2] = parseDSLToElements(['TRIANGLE|tr2|10,10|100,10|50,90|blue|Tri2']);
      expect(t2.type).toBe('line');

      const [t3] = parseDSLToElements(['TRIANGLE|tr3|20,20|100|80|green|Tri3']);
      expect(t3.type).toBe('line');
    });

    it('POLYGON および POLYLINE のカンマ座標指定', () => {
      const [p1] = parseDSLToElements(['POLYGON|pg1|0,0,100,0,100,100,0,100|yellow|Poly1']);
      expect(p1.type).toBe('line');

      const [p2] = parseDSLToElements(['POLYGON|pg2|0,0|100,0|100,100|0,100|yellow|Poly2']);
      expect(p2.type).toBe('line');

      const [pl1] = parseDSLToElements(['POLYLINE|pl1|0,0,50,50,100,0|dark|Line1']);
      expect(pl1.type).toBe('line');
    });

    it('GRID のカンマ座標指定およびセル生成', () => {
      const elements = parseDSLToElements(['GRID|g1|50,50,200,200|4,4|blue|yellow|sharp']);
      expect(elements.length).toBeGreaterThan(1);
    });

    it('ARROW / LINE のアンカー解決で空参照やフォールバック', () => {
      const [arr] = parseDSLToElements(['ARROW|a1|||blue|arr']);
      expect(arr.type).toBe('arrow');
    });

    it('ELBOW で縦方向優先の直角ルーティング (dy > dx)', () => {
      const [elbow] = parseDSLToElements(['ELBOW|el1|100,100|150,300|dark|flow']);
      expect(elbow.type).toBe('arrow');
      expect(elbow.points.length).toBe(4);
    });

    it('各種図形に opacity スタイルが正しく設定される', () => {
      const elements = parseDSLToElements([
        'ELLIPSE|e1|10|20|100|50|blue||0|opacity=60',
        'ELLIPSE|e2|10,20,100,50|blue||0|opacity=60',
        'DIAMOND|d1|10|20|80|80|yellow||0|opacity=70',
        'DIAMOND|d2|10,20,80,80|yellow||0|opacity=70',
        'CLOUD|c1|10|20|120|60|teal||opacity=80',
        'CLOUD|c2|10,20,120,60|teal||opacity=80',
        'FRAME|fr1|10|20|200|150|dark||opacity=90',
        'FRAME|fr2|10,20,200,150|dark||opacity=90',
        'POLYGON|pg1|0,0|100,0|100,100|0,100|yellow||opacity=50',
        'POLYLINE|pl1|0,0,50,50|dark||opacity=40',
        'GRID|gr1|0|0|200|200|2,2|blue|white|opacity=30',
        'STAR|st1|10|20|100|100|orange||opacity=65',
        'STAR|st2|100|100|50|yellow||opacity=55',
        'STAR|st3|100,100,50|yellow||opacity=55',
        'TRIANGLE|tr1|10,10,100,10,50,90|red||opacity=50',
        'LINE|ln1|0,0|100,100|dark||opacity=50',
        'CIRCLE|c_op|100|100|50|blue|Label|opacity=50',
        'CARD|card_op|100|100|200|100|blue|Title|Body|opacity=50',
        'CHESSBOARD|chess_op|100|100|400|#f0d9b5|#b58863|init|opacity=50',
      ]);
      expect(elements.length).toBeGreaterThan(10);
      expect(elements.some((e: any) => e.opacity === 60)).toBe(true);
      expect(elements.some((e: any) => e.opacity === 70)).toBe(true);
      expect(elements.some((e: any) => e.opacity === 65)).toBe(true);
    });

    it('CHESSBOARD のカンマ区切り座標指定 (x,y,size)', () => {
      const elements = parseDSLToElements(['CHESSBOARD|chess_c|100,100,400|#f0d9b5|#b58863|init|solid']);
      expect(elements.length).toBeGreaterThan(64);
    });

    it('MOVE_BY の個別引数形式 (x, y) および TEXT の opacity スタイル', () => {
      const map = new Map<string, any>();
      map.set('b1', { id: 'b1', x: 10, y: 20 });

      const elements = parseDSLToElements([
        'MOVE_BY|b1|15|25',
        'TEXT|t_op|100|100|16|dark|Text|opacity=50'
      ], map);

      expect(map.get('b1').x).toBe(25);
      expect(map.get('b1').y).toBe(45);
      expect(elements[1].opacity).toBe(50);
    });

    it('resolveAnchor の空文字・デフォルト解決', () => {
      const map = new Map<string, any>();
      expect(resolveAnchor('', map, 50, 60)).toEqual([50, 60]);
    });
  });
});
