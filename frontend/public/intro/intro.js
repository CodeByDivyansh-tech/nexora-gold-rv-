/*
 * intro.js: the 3D scroll story on /intro/ (three.js r160 and its addons, vendored in /pitch/vendor/).
 *
 * One scene, driven by how far the page is scrolled (s = 0 … 5, one unit per chapter):
 *   0 hero      gold particles swirl in and assemble into four ingots, one per contract (cursor turns them liquid)
 *   1 problem   the four ingots, labelled with their contract sizes
 *   2 gaps      the particles become dust; the camera flies along 15 years of real daily gaps (weekly columns)
 *   3 wall      the cost line rises as a glowing wall; columns above it light up
 *   4 solution  coloured bands under the timeline: clean test, training, test year, after it
 *   5 answer    the particles re-form into the word "No."
 *
 * Every number comes from the site's own data files (../data/). Nothing moves with "reduce motion"
 * (index.html then shows a still page and this file does nothing).
 */
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

const root = document.documentElement;
const STILL = root.classList.contains('still');
const COL = { c1: '#BC8424', c2: '#2193E0', c3: '#CD6199', c4: '#7D4DAD', up: '#6FCF9A', hot: '#F3D184', gold: '#E5B04A' };   // the site's own contract colours (app/theme.js)
const M = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const fd = (s) => { const p = s.split('-'); return (+p[2]) + ' ' + M[+p[1] - 1] + ' ' + p[0]; };
const inr = (n) => '₹' + Math.round(Math.abs(n)).toLocaleString('en-IN');
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const smooth = (a, b, v) => { const t = clamp((v - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };

// ---------------------------------------------------------------- data and text
const [D, HC] = await Promise.all([
  fetch('../data/site-data.json').then((r) => r.json()),
  fetch('../data/history_charts.json').then((r) => r.json())
]);
const L = D.longrun, hurdle = D.today[0].hurdle;
// one pair's gap from normal, every trading day 2011 → today
const P0 = HC.pairs.M_PETAL, P1 = D.pairs.M_PETAL;
const days = [];
[P0, P1].forEach((P) => P.d.forEach((d, i) => { if (P.mu[i] != null && P.s[i] != null) days.push([d, P.s[i] - P.mu[i]]); }));
const above = days.filter((x) => Math.abs(x[1]) > hurdle).length;
const fill = {
  first: days[0][0].slice(0, 4), asOf: fd(D.asOf), years: String(+D.asOf.slice(0, 4) - +days[0][0].slice(0, 4)),
  hurdle: hurdle.toFixed(1), pct: Math.round(above / days.length * 100) + '%',
  rows: L.allRows.toLocaleString('en-IN'), contracts: String(L.allContracts), days: L.allDays.toLocaleString('en-IN'),
  clean: L.start.slice(0, 4) + '–' + L.end.slice(0, 4), cleanLong: fd(L.start) + ' to ' + fd(L.end),
  net: inr(L.net), net0: inr(L.net0), n: String(L.n), losing: L.losingYears + ' of ' + L.years,
  // the sentence follows the sign of each number (Oct-2026: after the lifecycle correction the zero-slippage result is a profit)
  netVerb: L.net < 0 ? 'lost' : 'made',
  zeroClause: L.net0 < 0 ? ', and ' + inr(L.net0) + ' even with zero slippage' : ', though with zero slippage it would have made ' + inr(L.net0) + ': costs decide it'
};
document.querySelectorAll('[data-k]').forEach((el) => { const v = fill[el.dataset.k]; if (v != null) el.textContent = v; });
if (STILL) await new Promise(() => {});   // reduced motion or no WebGL: the text above is the whole page

// ---------------------------------------------------------------- renderer, camera, glow
const canvas = document.getElementById('scene');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
const PHONE = matchMedia('(pointer: coarse)').matches || innerWidth < 760;
renderer.setPixelRatio(Math.min(devicePixelRatio || 1, PHONE ? 1.5 : 1.75));
renderer.setSize(innerWidth, innerHeight, false);
renderer.setClearColor(0x000000, 0);
const scene = new THREE.Scene();
scene.fog = new THREE.FogExp2(0x0e0a05, 0.016);
const camera = new THREE.PerspectiveCamera(50, innerWidth / innerHeight, 0.1, 200);
const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), 0.6, 0.45, 0.32);
composer.addPass(bloom);
composer.addPass(new OutputPass());

// ---------------------------------------------------------------- particles: nebula → ingots → dust → "No."
const N = PHONE ? 12000 : 26000;
const CONTRACTS = [
  { name: 'GOLDM', size: '100 g', col: COL.c1, scale: 1.0 },
  { name: 'GOLDTEN', size: '10 g', col: COL.c2, scale: 0.8 },
  { name: 'GOLDGUINEA', size: '8 g', col: COL.c3, scale: 0.74 },
  { name: 'GOLDPETAL', size: '1 g', col: COL.c4, scale: 0.55 }
];
function ingotCentres(aspect) {
  if (aspect < 0.95) return [[-1.1, 3.3], [1.1, 3.3], [-0.95, 2.1], [1.0, 2.1]].map(([x, y]) => new THREE.Vector3(x, y, 0));
  return [[2.0, 2.0], [4.3, 2.0], [2.55, 0.55], [4.55, 0.55]].map(([x, y]) => new THREE.Vector3(x, y, 0));
}
// a point on the surface of a trapezoid ingot (like the logo's bars), centred on the origin
function ingotPoint(scale) {
  const W = 1.7 * scale, Wt = 1.25 * scale, H = 0.6 * scale, Dp = 0.85 * scale;
  const half = (y) => (W + (Wt - W) * (y / H)) / 2;
  const r = Math.random();
  let x, y, z;
  if (r < 0.34) { y = Math.random() * H; x = (Math.random() * 2 - 1) * half(y); z = (Math.random() < 0.5 ? -1 : 1) * Dp / 2; }
  else if (r < 0.62) { x = (Math.random() * 2 - 1) * Wt / 2; z = (Math.random() * 2 - 1) * Dp / 2; y = H; }
  else if (r < 0.84) { y = Math.random() * H; z = (Math.random() * 2 - 1) * Dp / 2; x = (Math.random() < 0.5 ? -1 : 1) * half(y); }
  else { x = (Math.random() * 2 - 1) * W / 2; z = (Math.random() * 2 - 1) * Dp / 2; y = 0; }
  return [x, y - H / 2, z];
}
// the word "No." sampled from a canvas
async function textPoints() {
  try { await document.fonts.load('800 300px Geist'); } catch (e) {}
  const cw = 1100, ch = 420, c = document.createElement('canvas'); c.width = cw; c.height = ch;
  const g = c.getContext('2d'); g.fillStyle = '#fff'; g.font = '800 330px Geist, system-ui, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.fillText('No.', cw / 2, ch / 2 + 10);
  const px = g.getImageData(0, 0, cw, ch).data, pts = [];
  for (let y = 0; y < ch; y += 3) for (let x = 0; x < cw; x += 3) if (px[(y * cw + x) * 4 + 3] > 128) pts.push([x, y]);
  const wide = innerWidth / innerHeight < 0.95 ? 3.6 : 6.2;
  return pts.map(([x, y]) => [(x / cw - 0.5) * wide, (0.5 - y / ch) * wide * ch / cw + (innerWidth / innerHeight < 0.95 ? 4.1 : 2.35), 0]);
}

const geo = new THREE.BufferGeometry();
const aNeb = new Float32Array(N * 3), aIng = new Float32Array(N * 3), aCen = new Float32Array(N * 3), aDust = new Float32Array(N * 3), aTxt = new Float32Array(N * 3);
const aCol = new Float32Array(N * 3), aCol2 = new Float32Array(N * 3), aSeed = new Float32Array(N);
const kOf = new Uint8Array(N);
const shares = CONTRACTS.map((c) => c.scale * c.scale); const sumS = shares.reduce((a, b) => a + b, 0);
const tmp = new THREE.Color();
for (let i = 0; i < N; i++) {
  // which ingot: in proportion to its surface
  let r = Math.random() * sumS, k = 0; while (r > shares[k] && k < 3) { r -= shares[k]; k++; }
  kOf[i] = k;
  // nebula: a colourful spiral cloud the ingots assemble from
  const t = Math.random() * Math.PI * 2, rad = 3 + Math.random() * 7, arm = (k * Math.PI) / 2;
  aNeb.set([Math.cos(t + arm + rad * 0.35) * rad, (Math.random() - 0.5) * 3 + 1, Math.sin(t + arm + rad * 0.35) * rad * 0.6 - 2], i * 3);
  // dust: spread along the whole flight path, so scrolling feels like moving through space
  aDust.set([(Math.random() - 0.5) * 46, -2.5 + Math.random() * 11, -30 + Math.random() * 38], i * 3);
  aSeed[i] = Math.random();
  tmp.set(CONTRACTS[k].col).lerp(new THREE.Color(COL.hot), Math.random() * 0.35);
  aCol.set([tmp.r, tmp.g, tmp.b], i * 3);
}
function layout() {
  const cen = ingotCentres(innerWidth / innerHeight);
  for (let i = 0; i < N; i++) {
    const k = kOf[i], p = ingotPoint(CONTRACTS[k].scale), c = cen[k];
    aIng.set([p[0] + c.x, p[1] + c.y, p[2] + c.z], i * 3); aCen.set([c.x, c.y, c.z], i * 3);
  }
  ['aIng', 'aCen'].forEach((n) => { if (geo.attributes[n]) geo.attributes[n].needsUpdate = true; });
  return cen;
}
let centres = layout();
const tp = await textPoints();
for (let i = 0; i < N; i++) {
  const q = tp[i % tp.length];
  aTxt.set([q[0] + (Math.random() - 0.5) * 0.03, q[1] + (Math.random() - 0.5) * 0.03, (Math.random() - 0.5) * 0.25], i * 3);
  tmp.set('#F8DB97').lerp(new THREE.Color('#B98428'), clamp(q[0] / 6 + 0.5, 0, 1) * 0.7);   // gold foil, as the site's headlines
  aCol2.set([tmp.r, tmp.g, tmp.b], i * 3);
}
geo.setAttribute('position', new THREE.BufferAttribute(aIng, 3));
[['aNeb', aNeb], ['aIng', aIng], ['aCen', aCen], ['aDust', aDust], ['aTxt', aTxt], ['aCol', aCol], ['aCol2', aCol2]].forEach(([n, a]) => geo.setAttribute(n, new THREE.BufferAttribute(a, 3)));
geo.setAttribute('aSeed', new THREE.BufferAttribute(aSeed, 1));
geo.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0, -10), 60);

const U = {
  uTime: { value: 0 }, uA: { value: 0 }, uB: { value: 0 }, uC: { value: 0 }, uSpin: { value: 0 },
  uMouse: { value: new THREE.Vector3(99, 99, 0) }, uVel: { value: new THREE.Vector2() }, uPres: { value: 0 },
  uPix: { value: renderer.getPixelRatio() }, uSize: { value: PHONE ? 22 : 19 }
};
const mat = new THREE.ShaderMaterial({
  uniforms: U, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
  vertexShader: `
    attribute vec3 aNeb, aIng, aCen, aDust, aTxt, aCol, aCol2; attribute float aSeed;
    uniform float uTime, uA, uB, uC, uSpin, uPres, uPix, uSize; uniform vec3 uMouse; uniform vec2 uVel;
    varying vec3 vCol; varying float vA;
    mat2 rot(float a){ float c = cos(a), s = sin(a); return mat2(c, -s, s, c); }
    void main(){
      vec3 ing = aIng - aCen; ing.xz = rot(uSpin * (0.7 + aSeed * 0.04)) * ing.xz; ing += aCen;
      float a = smoothstep(0.0, 1.0, clamp(uA * 1.25 - aSeed * 0.25, 0.0, 1.0));
      vec3 p = mix(aNeb, ing, a);
      vec3 dust = aDust + vec3(sin(uTime * 0.15 + aSeed * 30.0), cos(uTime * 0.12 + aSeed * 21.0), 0.0) * 0.35;
      float b = smoothstep(0.0, 1.0, clamp(uB * 1.3 - aSeed * 0.3, 0.0, 1.0));
      p = mix(p, dust, b);
      float c = smoothstep(0.0, 1.0, clamp(uC * 1.35 - aSeed * 0.35, 0.0, 1.0));
      p = mix(p, aTxt, c);
      // liquid: the cursor pushes and swirls the material near it
      vec2 d = p.xy - uMouse.xy; float f = exp(-dot(d, d) / 0.7) * uPres * (1.0 - b * (1.0 - c)) * (1.0 - 0.55 * c);
      vec2 n = d / (length(d) + 0.0001);
      p.xy += n * f * 0.75 + vec2(-n.y, n.x) * f * 0.55 + uVel * f * 0.6;
      p.z += sin(aSeed * 50.0 + uTime * 3.0) * f * 0.6;
      p += vec3(sin(uTime * 1.7 + aSeed * 60.0), cos(uTime * 1.3 + aSeed * 40.0), 0.0) * 0.012;
      vec4 mv = modelViewMatrix * vec4(p, 1.0);
      gl_Position = projectionMatrix * mv;
      gl_PointSize = uSize * uPix * (0.55 + aSeed * 0.7) * (1.0 + f * 0.8) / -mv.z;
      vCol = mix(aCol, aCol2, c) * (1.0 + f * 0.9);
      vA = (0.32 + 0.3 * a) * mix(1.0, 0.7, b * (1.0 - c)) * mix(1.0, 1.35, c);
    }`,
  fragmentShader: `
    varying vec3 vCol; varying float vA;
    void main(){ vec2 q = gl_PointCoord - 0.5; float r = length(q); if (r > 0.5) discard;
      float s = smoothstep(0.5, 0.0, r); gl_FragColor = vec4(vCol * s, s * vA); }`
});
const points = new THREE.Points(geo, mat);
scene.add(points);

// ---------------------------------------------------------------- labels (sprites drawn on a canvas)
function label(text, color, sizeY = 0.32) {
  const lines = Array.isArray(text) ? text : [text];
  const c = document.createElement('canvas'), g = c.getContext('2d'), fs = 64, lh = fs * 1.3;
  g.font = `600 ${fs}px Geist, system-ui, sans-serif`;
  c.width = Math.ceil(Math.max(...lines.map((l) => g.measureText(l).width))) + 40; c.height = Math.round(lh * lines.length + 30);
  g.font = `600 ${fs}px Geist, system-ui, sans-serif`; g.textBaseline = 'middle';
  lines.forEach((l, i) => { g.fillStyle = i ? '#E8D9B8' : color; g.fillText(l, 20, 15 + lh * (i + 0.5)); });
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, transparent: true, depthWrite: false, opacity: 0, fog: false }));
  s.scale.set(sizeY * lines.length * c.width / c.height, sizeY * lines.length, 1);
  return s;
}
await (document.fonts ? document.fonts.ready : Promise.resolve());
const ingotLabels = CONTRACTS.map((c) => { const s = label(c.name + ' · ' + c.size, c.col, 0.26); scene.add(s); return s; });
function placeLabels() { ingotLabels.forEach((s, k) => s.position.set(centres[k].x, centres[k].y + 0.75 * CONTRACTS[k].scale + 0.2, 0.3)); }
placeLabels();

// ---------------------------------------------------------------- the 15-year timeline of gaps
const TL = new THREE.Group(); TL.position.set(0, 0, -20); scene.add(TL);
const span = 32, K = 0.022;   // world units: timeline length, height per bps
const t0 = Date.parse(days[0][0]), t1 = Date.parse(days[days.length - 1][0]);
const xOf = (d) => -span / 2 + (Date.parse(d) - t0) / (t1 - t0) * span;
const weeks = [];
for (let i = 0; i < days.length; i += 5) {
  let best = days[i]; for (let j = i; j < Math.min(i + 5, days.length); j++) if (Math.abs(days[j][1]) > Math.abs(best[1])) best = days[j];
  weeks.push([days[i][0], Math.abs(best[1])]);
}
const colGeo = new THREE.BoxGeometry(1, 1, 1); colGeo.translate(0, 0.5, 0);
const colMat = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false });
const cols = new THREE.InstancedMesh(colGeo, colMat, weeks.length);
const mtx = new THREE.Matrix4(), cLow = new THREE.Color(COL.c2), cHigh = new THREE.Color(COL.hot), cTmp = new THREE.Color();
const colW = span / weeks.length * 0.55;
weeks.forEach(([d, g], i) => {
  const h = Math.max(0.02, Math.min(g, 160) * K);
  mtx.makeScale(colW, h, 0.35); mtx.setPosition(xOf(d), 0, 0); cols.setMatrixAt(i, mtx);
  cTmp.copy(g > hurdle ? cHigh : cLow).multiplyScalar(g > hurdle ? 0.62 : 0.45 + g / hurdle * 0.45); cols.setColorAt(i, cTmp);
});
TL.add(cols);
// one real trade: the biggest gap from normal the frozen rule traded on this pair in the clean test
const gapOn = new Map(days);
const pick = HC.pairs.M_PETAL.trades['5'].filter((t) => gapOn.has(t[1])).sort((a, b) => Math.abs(gapOn.get(b[1])) - Math.abs(gapOn.get(a[1])))[0];
const trade = pick && { entry: pick[1], exit: pick[2], side: pick[3], net: pick[5], gap: Math.abs(gapOn.get(pick[1])) };
const LOSS = '#FF8E7E';
let tradeBits = [];
if (trade) {
  const tx = xOf(trade.entry), top = Math.min(trade.gap, 160) * K;
  const beam = new THREE.Mesh(new THREE.BoxGeometry(0.06, top + 0.55, 0.06), new THREE.MeshBasicMaterial({ color: new THREE.Color(LOSS).multiplyScalar(1.3), transparent: true, opacity: 0 }));
  beam.position.set(tx, (top + 0.55) / 2, 0.25); TL.add(beam);
  const ringM = new THREE.Mesh(new THREE.TorusGeometry(0.32, 0.035, 8, 40), new THREE.MeshBasicMaterial({ color: new THREE.Color(LOSS).multiplyScalar(1.4), transparent: true, opacity: 0 }));
  ringM.position.set(tx, top + 0.6, 0.25); TL.add(ringM);
  const verb = trade.side < 0 ? 'Sold GOLDM, bought GOLDPETAL' : 'Bought GOLDM, sold GOLDPETAL';
  const tag = label(['One real trade · ' + fd(trade.entry), verb + ', gap ' + Math.round(trade.gap) + ' bps from normal', 'Closed ' + fd(trade.exit) + ': ' + (trade.net < 0 ? '−' : '+') + inr(trade.net) + ' after costs'], LOSS, 0.19);
  tag.position.set(tx - tag.scale.x / 2 - 0.35, top + 0.5, 0.9); TL.add(tag);   // ends just left of the marker: the chapter card sits on the right
  tradeBits = [beam, ringM, tag];
  Object.assign(fill, { tradeDate: fd(trade.entry), tradeGap: String(Math.round(trade.gap)), tradeNet: (trade.net < 0 ? '−' : '+') + inr(trade.net) });
  document.querySelectorAll('[data-k^="trade"]').forEach((el) => { const v = fill[el.dataset.k]; if (v != null) el.textContent = v; });
}
// the cost wall
const wallH = hurdle * K;
const wall = new THREE.Mesh(new THREE.PlaneGeometry(span + 3, wallH), new THREE.MeshBasicMaterial({ color: COL.gold, transparent: true, opacity: 0, depthWrite: false, side: THREE.DoubleSide }));
wall.position.set(0, wallH / 2, 0.05); TL.add(wall);
const edge = new THREE.Mesh(new THREE.BoxGeometry(span + 3, 0.04, 0.04), new THREE.MeshBasicMaterial({ color: new THREE.Color(COL.hot).multiplyScalar(1.4), transparent: true, opacity: 0 }));
edge.position.set(0, wallH, 0.05); TL.add(edge);
const wallLabel = label('Cost line ' + hurdle.toFixed(1) + ' bps', COL.hot, 0.42); wallLabel.position.set(-span / 2 + 2.6, wallH + 0.45, 0.3); TL.add(wallLabel);
// the study's periods as coloured bands under the timeline
const bands = [
  [days[0][0], L.end, COL.c4, 'Clean test ' + L.start.slice(0, 4) + '–' + L.end.slice(0, 4)],
  [D.split.train_start, D.split.train_end, COL.c1, 'Training'],
  [D.split.test_start, D.split.test_end, COL.c3, 'Test year'],
  [D.split.test_end, D.asOf, COL.up, 'After']
].map(([a, b, c, name], i) => {
  const x0 = xOf(a), x1 = xOf(b), m = new THREE.Mesh(new THREE.BoxGeometry(Math.max(0.08, x1 - x0), 0.06, 5.5), new THREE.MeshBasicMaterial({ color: new THREE.Color(c).multiplyScalar(0.85), transparent: true, opacity: 0, depthWrite: false }));
  m.position.set((x0 + x1) / 2, -0.06, 0.6); TL.add(m);
  // short periods sit close together: their names go on separate rows
  const l = label(name, c, i ? 0.8 : 1.0); l.position.set(i ? Math.min((x0 + x1) / 2, span / 2 - 1.5) : (x0 + x1) / 2, 0.4, 4.4 + Math.max(0, i - 1) * 1.6); TL.add(l);
  return { m, l };
});
const years = [];
for (let y = +days[0][0].slice(0, 4); y <= +D.asOf.slice(0, 4); y += 1) {
  if (y % 3 && y !== +D.asOf.slice(0, 4)) continue;
  const l = label(String(y), '#C9B794', 0.34); l.position.set(xOf(y + '-01-01' < days[0][0] ? days[0][0] : y + '-01-01'), -0.45, 0.9); TL.add(l); years.push(l);
}

// ---------------------------------------------------------------- camera path, one key per chapter
const narrow = () => innerWidth / innerHeight < 0.95;
const V = (x, y, z) => new THREE.Vector3(x, y, z);
function keys() {
  const n = narrow();
    const hero = { pos: n ? V(0, 1.4, 10.5) : V(0, 0.9, 8.4), look: n ? V(0, 1.3, 0) : V(0, 0.9, 0) };
    const prob = { pos: n ? V(0.6, 2.8, 9.4) : V(1.2, 2.3, 7.6), look: n ? V(0, 1.9, 0) : V(1.5, 1.1, 0) };
    const wallv = { pos: V(0, 4.0, n ? 6 : -2), look: V(0, 1.0, -20) };
    const bandv = { pos: V(0, n ? 40 : 22, n ? -2 : -4.5), look: V(0, 0, n ? -14 : -15.5) };
    const ans = { pos: n ? V(0, 2.2, 10.5) : V(0, 1.4, 8.2), look: n ? V(0, 1.6, 0) : V(0, 1.7, 0) };
    return [
      { s: 0, ...hero }, { s: 0.3, ...hero },
      { s: 0.85, ...prob }, { s: 1.3, ...prob },
      { s: 1.95, pos: V(-span / 2 - 1, 2.6, -11.5), look: V(-span / 2 + 5, 1.0, -20) },
      { s: 2.75, pos: V(span / 2 - 6, 2.6, -11.5), look: V(span / 2 + 1, 1.0, -20) },
      { s: 3.15, ...wallv }, { s: 3.6, ...wallv },
      { s: 4.0, ...bandv }, { s: 4.35, ...bandv },
      { s: 4.85, ...ans }, { s: 5, ...ans }
    ];
}
let K_ = keys();
const camPos = new THREE.Vector3(), camLook = new THREE.Vector3();
function cameraAt(s) {
  let i = 0; while (i < K_.length - 2 && s > K_[i + 1].s) i++;
  const a = K_[i], b = K_[i + 1], t = smooth(a.s, b.s, s);
  camPos.lerpVectors(a.pos, b.pos, t); camLook.lerpVectors(a.look, b.look, t);
}

// ---------------------------------------------------------------- scroll, chapters, cursor
const sections = [...document.querySelectorAll('section[data-ch]')];
const dots = document.getElementById('dots');
const names = ['Same gold, four prices', 'The problem', 'The gaps are real', 'The cost wall', 'Our solution', 'The answer'];
sections.forEach((sec, i) => {
  const b = document.createElement('button'); b.type = 'button'; b.setAttribute('aria-label', 'Go to: ' + names[i]); b.dataset.label = names[i];
  b.addEventListener('click', () => scrollTo({ top: sec.offsetTop + (i === 2 ? 0 : 1), behavior: 'smooth' })); dots.appendChild(b);
});
const WASH = [
  'radial-gradient(80% 60% at 70% 25%, rgba(229,176,74,.24), transparent 60%), radial-gradient(70% 60% at 15% 85%, rgba(185,132,40,.16), transparent 60%)',
  'radial-gradient(80% 60% at 75% 30%, rgba(229,176,74,.20), transparent 60%), radial-gradient(60% 50% at 85% 20%, rgba(33,147,224,.10), transparent 60%)',
  'radial-gradient(90% 70% at 50% 20%, rgba(229,176,74,.16), transparent 60%), radial-gradient(70% 60% at 85% 85%, rgba(33,147,224,.12), transparent 60%)',
  'radial-gradient(90% 60% at 50% 30%, rgba(243,209,132,.22), transparent 60%), radial-gradient(70% 60% at 10% 80%, rgba(185,132,40,.14), transparent 60%)',
  'radial-gradient(80% 60% at 30% 30%, rgba(229,176,74,.18), transparent 60%), radial-gradient(70% 60% at 85% 80%, rgba(125,77,173,.14), transparent 60%)',
  'radial-gradient(80% 60% at 50% 30%, rgba(229,176,74,.26), transparent 60%), radial-gradient(70% 60% at 50% 90%, rgba(185,132,40,.18), transparent 60%)'
];
const wash = document.getElementById('wash'), bar = document.getElementById('bar'), flash = document.getElementById('flash');
let target = 0, sNow = 0, chapter = -1;
function readScroll() {
  const y = scrollY, vh = innerHeight;
  let s = 0;
  for (let i = 0; i < sections.length; i++) {
    const top = sections[i].offsetTop, h = Math.max(1, sections[i].offsetHeight - (i === sections.length - 1 ? vh : vh * 0.35));
    if (y >= top) s = i + clamp((y - top) / h, 0, 1);
  }
  target = clamp(s, 0, 5);
  bar.style.transform = 'scaleX(' + clamp(y / Math.max(1, document.body.scrollHeight - vh), 0, 1) + ')';
}
addEventListener('scroll', readScroll, { passive: true });
readScroll();

const ray = new THREE.Raycaster(), ndc = new THREE.Vector2(), plane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0), hit = new THREE.Vector3();
let presT = 0, lastM = new THREE.Vector3(99, 99, 0), mouseX = 0, mouseY = 0;
addEventListener('pointermove', (e) => {
  ndc.set(e.clientX / innerWidth * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
  mouseX = ndc.x; mouseY = ndc.y;
  ray.setFromCamera(ndc, camera);
  if (ray.ray.intersectPlane(plane, hit)) { U.uVel.value.set(clamp((hit.x - lastM.x) * 4, -1, 1), clamp((hit.y - lastM.y) * 4, -1, 1)); U.uMouse.value.copy(hit); lastM.copy(hit); presT = 1; }
}, { passive: true });
addEventListener('pointerleave', () => { presT = 0; });
document.addEventListener('mouseleave', () => { presT = 0; });
addEventListener('pointerup', (e) => { if (e.pointerType !== 'mouse') presT = 0; });

addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight, false); composer.setSize(innerWidth, innerHeight); bloom.setSize(innerWidth, innerHeight);
  centres = layout(); placeLabels(); K_ = keys(); readScroll();
});

// ---------------------------------------------------------------- the loop
gsapIntro();
function gsapIntro() {
  const start = performance.now();
  (function step() { const t = (performance.now() - start) / 3200; U.uA.value = clamp(t, 0, 1); if (t < 1) requestAnimationFrame(step); })();
}
const clock = new THREE.Clock();
function frame() {
  const dt = Math.min(clock.getDelta(), 0.05), time = clock.elapsedTime;
  sNow += (target - sNow) * (1 - Math.pow(0.0009, dt));   // smooth follow of the scroll
  const s = sNow;
  U.uTime.value = time;
  U.uB.value = smooth(1.35, 1.9, s);
  U.uC.value = smooth(4.4, 4.9, s);
  U.uSpin.value = time * 0.22 + s * 1.6;
  U.uPres.value += (presT * (1 - U.uB.value + U.uC.value) - U.uPres.value) * 0.08;
  U.uVel.value.multiplyScalar(0.92);
  const tl = smooth(1.4, 1.9, s) * (1 - smooth(4.35, 4.75, s));
  colMat.opacity = tl * (0.8 - 0.55 * smooth(3.55, 3.95, s));
  const w = smooth(2.75, 3.1, s) * (1 - smooth(4.35, 4.75, s));
  wall.material.opacity = w * 0.16; edge.material.opacity = w; wallLabel.material.opacity = w;
  wall.scale.y = 0.001 + smooth(2.7, 3.15, s); wall.position.y = wallH * wall.scale.y / 2;
  edge.position.y = wallH * wall.scale.y; wallLabel.position.y = edge.position.y + 0.45;
  const tv = smooth(1.85, 2.1, s) * (1 - smooth(3.5, 3.8, s));
  tradeBits.forEach((m) => { m.material.opacity = tv; });
  if (tradeBits[1]) tradeBits[1].rotation.y = time * 1.4;
  const bd = smooth(3.6, 3.95, s) * (1 - smooth(4.4, 4.75, s));
  bands.forEach(({ m, l }) => { m.material.opacity = bd * 0.9; l.material.opacity = bd; });
  years.forEach((l) => { l.material.opacity = tl * 0.9; });
  const lab = smooth(0.45, 0.8, s) * (1 - smooth(1.25, 1.45, s));
  ingotLabels.forEach((l) => { l.material.opacity = lab; });
  bloom.strength = 0.55 + w * 0.15;
  cameraAt(s);
  camera.position.copy(camPos).add(new THREE.Vector3(mouseX * 0.35, mouseY * 0.2, 0));
  camera.lookAt(camLook);
  const ch = clamp(Math.round(s - 0.3), 0, 5);
  if (ch !== chapter) {
    if (chapter >= 0 && flash) { flash.classList.remove('go'); void flash.offsetWidth; flash.classList.add('go'); }
    chapter = ch; wash.style.background = WASH[ch];
    [...dots.children].forEach((b, i) => b.setAttribute('aria-current', i === ch ? 'true' : 'false'));
  }
  composer.render();
  requestAnimationFrame(frame);
}
frame();
window.__intro = { get s() { return sNow; }, N, weeks: weeks.length, pct: fill.pct };
