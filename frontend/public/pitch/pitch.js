/**
 * Gold RV Intelligence — Cinematic 3D Presentation Pitch
 * Team NEXORA (Divyansh, Ishant Bhaudhira, Noni Gopal Das)
 * Hack in Hills '26 · Problem Statement 03
 *
 * Built with Three.js r160 (local vendor), GSAP 3.12.5 (local vendor), Web Speech API.
 * Apple Keynote aesthetic: Pure black #000000, Bullion Gold #F2A93B.
 */

import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';

// Slow-laptop safety: disable lag smoothing so count-ups and animations never freeze halfway
if (typeof gsap !== 'undefined' && gsap.ticker) {
  gsap.ticker.lagSmoothing(0);
}

// ============================================================
// GLOBAL STATE & DATA
// ============================================================

const state = {
  currentStage: 'opening', // 'opening' | '3d-bars' | 'slides'
  currentSlide: 1,
  totalSlides: 17,
  voiceEnabled: true,
  mascotVisible: true,
  notesVisible: false,
  isNormalized: false,
  isSpeaking: false,
  isTransitioning: false,
  pointer: { x: window.innerWidth / 2, y: window.innerHeight / 2, ndcX: 0, ndcY: 0 },
};

// Spoken voice lines for Goldie (All 17 Slides)
const spokenLines = {
  opening: "Hi judges! I'm Goldie. MCX sells the same gold in four sizes, at four different prices. Team NEXORA asked one question: is the gap real money, or a mirage?",
  stage2: "Look at the raw prices. They seem far apart. Now watch me price them the same way. The real gap is only six hundred eighty-seven rupees per ten grams.",
  1: "Meet Team NEXORA. Divyansh built the data and quant pipeline, Ishant built the frontend, and Noni led research and the pitch.",
  2: "Big raw gap, tiny real gap. Lot sizes, purity, expiry and costs all hide the truth, and backtests can easily cheat by peeking at the future.",
  3: "Step one: price every contract the same way. When we divide by purity and quote grams, the gap shrinks from one lakh thirty-four thousand rupees to just six hundred eighty-seven rupees.",
  4: "Step two: track the gap over three years. Notice the gold dots: eight trades won big during the twenty twenty-six crash, but outside that crash, trades were flat or negative.",
  5: "Step three: the z-score. We only look when the gap is more than two standard deviations from normal. Today, only the mini versus petal pair flags at minus two point one four.",
  6: "Step four: the cost hurdle. Even if the z-score flags, the gap must beat forty-eight point eight basis points of round-trip costs. Today, thirty-five point eight basis points fails this check.",
  7: "Here is a real example from thirty September. The gap is unusual, but it is only thirty-five point eight basis points, and a trade needs forty-eight point eight. One failed check is enough. So I stay quiet.",
  8: "Step five: the walk-forward test. We train on twenty-four months, lock every rule, and test on the next twelve months. Signals at today's close only execute tomorrow. One honest caveat: we revised the rule after first seeing that year, so our clean test is thirteen earlier years the rule never saw.",
  9: "The test year looks good: twenty trades and one lakh thirteen thousand rupees profit, but a t-statistic of only one point eight nine. On the clean test, two thousand eleven to twenty twenty-three, the same frozen rule lost five lakh forty-nine thousand rupees. So no, it is not real.",
  10: "Break it down by pair. Mini versus guinea made fifty-two thousand rupees. Guinea versus ten made twenty-eight thousand. All five pairs that traded made money, but with two to five trades each, sample sizes are tiny.",
  11: "Where did the profit come from? Look at the three-D columns: eight trades during the twenty twenty-six crash made one lakh thirty-eight thousand rupees. The other twelve trades lost twenty-four thousand. One crash carried the strategy.",
  12: "Slippage is deadly, and daily data cannot measure it. Training only breaks even at about three point eight basis points. At ten basis points, test profit drops to fifty-two thousand rupees and training loses almost one lakh. And on thirteen earlier years the rule loses money even with zero slippage.",
  13: "The normal gap isn't constant. Guinea versus petal sat around two hundred fifty basis points, then in one week of November twenty twenty-four Petal repriced and the gap fell to near zero. A static model breaks when market structure shifts.",
  14: "Zero runtime servers. A Python pipeline processes eleven thousand nine hundred fifty-four rows with forty-two automated tests, producing static JSON. Nothing can crash during the demo.",
  15: "MCX gold trading grew three point four times in a single year, reaching twenty-eight thousand crore rupees daily. The market is large and growing.",
  16: "Four key takeaways: normalization matters, costs dominate, crash attribution reveals the truth, and clean data is non-negotiable. Our next step is paper trading with live tick data.",
  17: "Thank you, judges! Please try the live terminal at gold-r-v dot vercel dot app while we take your questions.",
};

// Speaker Notes for Judges / Presenter (N key)
const speakerNotes = {
  1: "Welcome judges. Team NEXORA built Gold RV Intelligence to investigate cross-contract commodity pricing on MCX. We mathematically normalized all four gold contracts to pure gold and tested whether cross-contract spreads survive real-world execution costs. Our headline finding is simple and honest: the gaps are real, but a proven edge after costs is not.",
  2: "Raw quotes look wildly dispersed—over 1.3 lakh rupees apart—because MCX quotes 1g, 8g, 10g, and 100g in different quote units and purities. Once normalized to pure gold, the actual gap is only 687 rupees, or 46 basis points. The problem is that once you account for real trading costs, carry, and liquidity, this apparent arbitrage completely evaporates.",
  3: "Slide 3 explains our mathematical normalization. MCX quotes 1g, 8g, 10g, and 100g contracts in different quote units and purities (995 vs 999). By dividing close price by quote grams and purity, we bring every contract to an identical 10g pure gold baseline. This collapses the superficial ₹1,34,186 raw gap down to an honest ₹687 (46.2 bps).",
  4: "Slide 4 shows the 3-year historical time series of the GOLDM-GOLDPETAL gap. Over 750 trading days, the gap fluctuates around its rolling mean within a 2-sigma band. Most importantly, look at the distribution of trades: 8 trades during the Q1 2026 crash delivered ₹1,37,985 in gains, while the 12 trades outside the crash netted -₹24,387.",
  5: "Slide 5 introduces the statistical entry rule: the Z-score. A trade is only considered when the spread deviates more than 2 standard deviations from its rolling mean. In today's snapshot, only GOLDM vs GOLDPETAL passes this first hurdle at z = -2.14, while all 5 other pairs sit within the normal zone.",
  6: "Slide 6 breaks down our transaction cost hurdle. Cross-contract trades pay exchange turnover charges, SEBI turnover fees, stamp duty, STT/CTT, GST, and realistic bid-ask slippage (5 bps per leg). The round-trip cost is 24.4 bps, requiring a minimum gap of 2x cost = 48.8 bps before entering. Today's gap of 35.8 bps fails this gate.",
  7: "This live example from September 30, 2026 demonstrates our discipline. The z-score of 2.14 exceeds the 2.0 hurdle, but the gap of 35.8 basis points is less than twice our round-trip transaction costs of 48.8 basis points. The gate fails, so the system stays quiet rather than generating unprofitable churn.",
  8: "Slide 8 details our walk-forward validation framework. We train on 24 months (Oct 2023 - Sep 2025) and evaluate on the next 12 months (Oct 2025 - Sep 2026). Safeguards against look-ahead bias: t+1 execution, no parameter tuning on test data, liquidity filters and full cost deductions. Caveat we state openly: the five-check rule was written on 4 Oct 2026, after the original study's test-year results were known, so the test year is not a clean out-of-sample test. The clean test is 2011-2023, from our own MCX download: the rule was frozen before that data was used.",
  9: "Slide 9: the test year made +₹1,13,598 over 20 trades (+39.4 bps a trade), but the t-statistic is 1.89 (p = 0.07; 0.22 allowing for the 3 rule versions we scored on that year), and training lost -₹16,514 over 38 trades. The clean test, 2011-2023 with the rule frozen, made 151 trades and lost -₹5,49,070 (t = -3.63), and lost -₹2,35,391 even at zero slippage. No persistent edge is proven after costs.",
  10: "Slide 10 decomposes results across all 6 contract pairs. GOLDM-GOLDGUINEA contributed +₹52,883 across 5 trades and GOLDGUINEA-GOLDTEN +₹28,348 across 5 trades; GOLDM-GOLDPETAL made +₹22,916 across 4. All five pairs that traded were profitable (GOLDM-GOLDTEN made no trades), but 2 to 5 trades per pair make statistical significance impossible to claim.",
  11: "Slide 11 delivers our crucial honest attribution. In the 3D columns, the 8 crash trades in Jan-Mar 2026 generated +₹1,37,985, while all other 12 trades lost -₹24,387. The waterfall on the right: spread moves +₹1,85,431 plus gold +₹1,745 give ₹1,87,176 gross; ₹73,578 of costs leave ₹1,13,598 net. The crash window was named after we saw the results, so this split is a check, not a test.",
  12: "Slide 12 tests robustness across varying slippage assumptions: 0 bps, 2 bps, 5 bps (our baseline), and 10 bps. At zero slippage the test year shows +₹1,74,771 and training +₹65,048; at 10 bps the test year falls to +₹52,425 and training to -₹98,076. Training breaks even at about 4.0 bps per order. Daily data cannot measure slippage (both standard estimators find no spread on most contracts; the hard floor is half a tick, at most 0.34 bps), so only real broker fills can settle it. The 2011-2023 clean test loses money even at zero slippage.",
  13: "Slide 13 reveals why static relative value models fail in commodity markets: structural basis drift. GOLDGUINEA vs GOLDPETAL averaged about +255 bps from May to Nov 2024, then GOLDPETAL repriced: the sharpest move was 4-11 Nov 2024 (+203 to +19 bps, inside one contract), and the gap has sat near -29 bps since Feb 2025. We found no MCX notice explaining it. A rule relying on a fixed historical 'normal' will suffer catastrophic drawdowns during regime shifts.",
  14: "Slide 14 details our zero-runtime-server architecture. Our automated Python pipeline ingests official MCX Bhavcopy, normalizes contract specifications, and verifies data integrity across 12,267 rows and 149 contracts with 42 automated tests. The entire output compiles to static JSON for instant offline delivery.",
  15: "Slide 15 highlights the commercial scale. MCX gold futures turnover surged 3.4x to ₹28,340 crore daily, with gold accounting for 57% of total exchange bullion turnover. This massive liquidity pool makes even modest relative value strategies viable for proprietary trading desks and hedgers.",
  16: "Slide 16 summarizes our key takeaways and engineering roadmap. The four core principles: normalize first, respect costs, attribute profits honestly, and automate tests. Our roadmap outlines immediate live paper trading, near-term tick-level slippage measurement, and later cross-commodity expansion to silver.",
  17: "Thank you judges for your time and thoughtful evaluation. We invite you to explore the live Gold RV Intelligence terminal or review our audited codebase on GitHub. We are now open for your questions.",
};
// pitch/data.js rewrites the result lines from the pipeline's JSON, so the deck never contradicts the site
window.GRV_PITCH = { spokenLines, speakerNotes };

// 4 Contracts Data
const contractData = {
  GOLDM: {
    name: "GOLDM (100 g)",
    raw: "₹1,47,908 / 10 g (995 pure)",
    pure: "₹1,48,651",
    lot: 100,
    size: [2.5, 1.1, 1.2],
    posRaw: [-4.2, 0.9, 0],
    posNorm: [-4.2, 0.8, 0],
    scaleNorm: [1.4, 0.7, 0.8],
  },
  GOLDTEN: {
    name: "GOLDTEN (10 g)",
    raw: "₹1,48,322 / 10 g (999)",
    pure: "₹1,48,470",
    lot: 10,
    size: [1.6, 0.75, 0.85],
    posRaw: [-1.4, 0.6, 0.4],
    posNorm: [-1.4, 0.8, 0],
    scaleNorm: [1.4, 0.7, 0.8],
  },
  GOLDGUINEA: {
    name: "GOLDGUINEA (8 g)",
    raw: "₹1,19,207 / 8 g (999)",
    pure: "₹1,49,158",
    lot: 8,
    size: [1.4, 0.65, 0.75],
    posRaw: [1.4, 0.9, -0.2],
    posNorm: [1.4, 0.8, 0],
    scaleNorm: [1.4, 0.7, 0.8],
  },
  GOLDPETAL: {
    name: "GOLDPETAL (1 g)",
    raw: "₹14,893 / 1 g (999)",
    pure: "₹1,49,079",
    lot: 1,
    size: [0.85, 0.4, 0.45],
    posRaw: [4.0, 0.5, 0.2],
    posNorm: [4.0, 0.8, 0],
    scaleNorm: [1.4, 0.7, 0.8],
  },
};

// Helper: Indian numbering format (1,13,598)
function formatIndian(val) {
  const absVal = Math.round(Math.abs(val));
  const str = absVal.toString();
  const lastThree = str.substring(str.length - 3);
  const otherNumbers = str.substring(0, str.length - 3);
  const formatted = otherNumbers !== '' ? otherNumbers.replace(/\B(?=(\d{2})+(?!\d))/g, ',') + ',' + lastThree : lastThree;
  return (val < 0 ? '-' : '') + formatted;
}

// ============================================================
// VOICE CONTROLLER (WEB SPEECH API)
// ============================================================

class VoiceController {
  constructor() {
    this.synth = window.speechSynthesis || null;
    this.voice = null;
    this.captionEl = document.getElementById('caption-bar');
    this.captionTimeout = null;
    this.initVoices();
  }

  initVoices() {
    if (!this.synth) return;
    const loadVoices = () => {
      const voices = this.synth.getVoices();
      if (!voices || voices.length === 0) return;
      // Preference: en-IN -> en-GB -> en-US -> en
      this.voice = voices.find(v => v.lang === 'en-IN' || v.lang.startsWith('en-IN'))
        || voices.find(v => v.lang === 'en-GB' || v.lang.startsWith('en-GB'))
        || voices.find(v => v.lang === 'en-US' || v.lang.startsWith('en-US'))
        || voices.find(v => v.lang.startsWith('en'))
        || voices[0];
    };
    loadVoices();
    if (this.synth.onvoiceschanged !== undefined) {
      this.synth.onvoiceschanged = loadVoices;
    }
  }

  speak(text) {
    if (this.captionTimeout) clearTimeout(this.captionTimeout);
    this.stop();

    if (!text) return;

    // Show subtitles in bottom caption bar
    if (this.captionEl) {
      this.captionEl.textContent = text;
      this.captionEl.classList.add('visible');
    }

    if (!state.voiceEnabled || !this.synth) {
      const words = text.split(/\s+/).length;
      const readingDurationMs = Math.max(3000, words * 320);
      this.captionTimeout = setTimeout(() => {
        if (this.captionEl) this.captionEl.classList.remove('visible');
      }, readingDurationMs);
      return;
    }

    const utterance = new SpeechSynthesisUtterance(text);
    if (this.voice) utterance.voice = this.voice;
    utterance.rate = 1.0;
    utterance.pitch = 1.15;

    utterance.onstart = () => {
      state.isSpeaking = true;
      if (goldieMascot) goldieMascot.setSpeaking(true);
    };

    utterance.onend = () => {
      state.isSpeaking = false;
      if (goldieMascot) goldieMascot.setSpeaking(false);
      this.captionTimeout = setTimeout(() => {
        if (this.captionEl) this.captionEl.classList.remove('visible');
      }, 1200);
    };

    utterance.onerror = () => {
      state.isSpeaking = false;
      if (goldieMascot) goldieMascot.setSpeaking(false);
      this.captionTimeout = setTimeout(() => {
        if (this.captionEl) this.captionEl.classList.remove('visible');
      }, 2000);
    };

    this.synth.speak(utterance);
  }

  stop() {
    if (this.synth && this.synth.speaking) {
      this.synth.cancel();
    }
    state.isSpeaking = false;
    if (goldieMascot) goldieMascot.setSpeaking(false);
  }
}

const voiceController = new VoiceController();

// ============================================================
// 3D MASCOT "GOLDIE" (BRIGHT SHINY GOLD #F2A93B + ROOMENVIRONMENT)
// ============================================================

class GoldieMascot {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.isSpeaking = false;
    this.blinkTimer = null;
    this.mouth = null;
    this.pupilL = null;
    this.pupilR = null;
    this.waveArm = null;
    this.bodyGroup = null;

    if (!this.canvas) return;
    this.initScene();
  }

  initScene() {
    const width = this.canvas.clientWidth || 140;
    const height = this.canvas.clientHeight || 140;

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(36, width / height, 0.1, 50);
    this.camera.position.set(0, 0, 5.2);

    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      alpha: true,
      antialias: true,
      powerPreference: 'high-performance'
    });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.25;

    // RoomEnvironment (PMREMGenerator) for brilliant reflections
    try {
      const pmrem = new THREE.PMREMGenerator(this.renderer);
      this.scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    } catch (e) {
      // fallback
    }

    // High quality studio lights
    const keyLight = new THREE.DirectionalLight(0xFFF0D0, 2.8);
    keyLight.position.set(4, 5, 4);
    this.scene.add(keyLight);

    const rimLight = new THREE.DirectionalLight(0xF2A93B, 2.2);
    rimLight.position.set(-4, -2, -3);
    this.scene.add(rimLight);

    const ambLight = new THREE.AmbientLight(0xFFE8B8, 1.4);
    this.scene.add(ambLight);

    this.buildGoldie();
    this.startBlinking();
    this.animate();
  }

  buildGoldie() {
    this.bodyGroup = new THREE.Group();
    this.scene.add(this.bodyGroup);

    // Ultra-polished metallic gold material (#F2A93B)
    const goldMat = new THREE.MeshStandardMaterial({
      color: 0xF2A93B,
      metalness: 0.85,
      roughness: 0.18,
    });

    // Bottom Gold Bar (shifted right)
    const bottomGeom = new RoundedBoxGeometry(2.1, 0.72, 1.05, 5, 0.14);
    const bottomBar = new THREE.Mesh(bottomGeom, goldMat);
    bottomBar.position.set(0.24, -0.42, 0);
    this.bodyGroup.add(bottomBar);

    // Top Gold Bar
    const topGeom = new RoundedBoxGeometry(2.1, 0.86, 1.05, 5, 0.16);
    const topBar = new THREE.Mesh(topGeom, goldMat);
    topBar.position.set(-0.2, 0.38, 0.05);
    this.bodyGroup.add(topBar);

    // Eyes
    const eyeWhiteMat = new THREE.MeshBasicMaterial({ color: 0xFFFFFF });
    const eyeGeom = new THREE.SphereGeometry(0.26, 24, 24);

    const eyeL = new THREE.Mesh(eyeGeom, eyeWhiteMat);
    eyeL.position.set(-0.52, 0.44, 0.52);
    eyeL.scale.set(1, 1.25, 0.7);
    this.bodyGroup.add(eyeL);

    const eyeR = new THREE.Mesh(eyeGeom, eyeWhiteMat);
    eyeR.position.set(0.12, 0.44, 0.52);
    eyeR.scale.set(1, 1.25, 0.7);
    this.bodyGroup.add(eyeR);

    // Pupils
    const pupilMat = new THREE.MeshBasicMaterial({ color: 0x070D14 });
    const pupilGeom = new THREE.SphereGeometry(0.12, 16, 16);

    this.pupilL = new THREE.Mesh(pupilGeom, pupilMat);
    this.pupilL.position.set(-0.52, 0.44, 0.65);
    this.bodyGroup.add(this.pupilL);

    this.pupilR = new THREE.Mesh(pupilGeom, pupilMat);
    this.pupilR.position.set(0.12, 0.44, 0.65);
    this.bodyGroup.add(this.pupilR);

    // Catchlights (sparkle)
    const glintMat = new THREE.MeshBasicMaterial({ color: 0xFFFFFF });
    const glintGeom = new THREE.SphereGeometry(0.04, 8, 8);

    const glintL = new THREE.Mesh(glintGeom, glintMat);
    glintL.position.set(-0.56, 0.49, 0.72);
    this.bodyGroup.add(glintL);

    const glintR = new THREE.Mesh(glintGeom, glintMat);
    glintR.position.set(0.08, 0.49, 0.72);
    this.bodyGroup.add(glintR);

    // Cheeks
    const cheekMat = new THREE.MeshBasicMaterial({ color: 0xFF8F85, transparent: true, opacity: 0.55 });
    const cheekGeom = new THREE.SphereGeometry(0.12, 12, 12);

    const cheekL = new THREE.Mesh(cheekGeom, cheekMat);
    cheekL.position.set(-0.84, 0.22, 0.48);
    cheekL.scale.set(1, 0.5, 0.5);
    this.bodyGroup.add(cheekL);

    const cheekR = new THREE.Mesh(cheekGeom, cheekMat);
    cheekR.position.set(0.44, 0.22, 0.48);
    cheekR.scale.set(1, 0.5, 0.5);
    this.bodyGroup.add(cheekR);

    // Animated Mouth (talking animation)
    const mouthMat = new THREE.MeshBasicMaterial({ color: 0x3D2400 });
    const mouthGeom = new THREE.CylinderGeometry(0.1, 0.1, 0.05, 16);
    this.mouth = new THREE.Mesh(mouthGeom, mouthMat);
    this.mouth.rotation.x = Math.PI / 2;
    this.mouth.position.set(-0.2, 0.16, 0.56);
    this.mouth.scale.set(1.4, 0.25, 0.6);
    this.bodyGroup.add(this.mouth);

    // Small Gold Waving Arm
    const armGeom = new RoundedBoxGeometry(0.25, 0.65, 0.25, 3, 0.06);
    this.waveArm = new THREE.Mesh(armGeom, goldMat);
    this.waveArm.position.set(0.95, 0.35, 0.1);
    this.waveArm.rotation.z = -0.4;
    this.bodyGroup.add(this.waveArm);
  }

  startBlinking() {
    const doBlink = () => {
      if (this.pupilL && this.pupilR) {
        gsap.to([this.pupilL.scale, this.pupilR.scale], {
          y: 0.08,
          duration: 0.1,
          yoyo: true,
          repeat: 1,
          ease: 'power2.inOut',
          onComplete: () => {
            const nextDelay = 2200 + Math.random() * 3400;
            this.blinkTimer = setTimeout(doBlink, nextDelay);
          }
        });
      }
    };
    this.blinkTimer = setTimeout(doBlink, 2500);
  }

  setSpeaking(speaking) {
    this.isSpeaking = speaking;
  }

  setWaving(waving) {
    if (this.waveArm) {
      if (waving) {
        gsap.to(this.waveArm.rotation, {
          z: 0.6,
          duration: 0.35,
          yoyo: true,
          repeat: 6,
          ease: 'sine.inOut',
          onComplete: () => {
            gsap.to(this.waveArm.rotation, { z: -0.4, duration: 0.4 });
          }
        });
      }
    }
  }

  update(time) {
    // 1. Hover & Gentle breathing float
    if (this.bodyGroup) {
      this.bodyGroup.position.y = Math.sin(time * 2.2) * 0.08;
      this.bodyGroup.rotation.y = (state.pointer.ndcX * 0.35);
      this.bodyGroup.rotation.x = -(state.pointer.ndcY * 0.2);
    }

    // 2. Cursor-Following Pupils (look directly at cursor)
    if (this.pupilL && this.pupilR) {
      const offsetX = state.pointer.ndcX * 0.08;
      const offsetY = state.pointer.ndcY * 0.06;
      this.pupilL.position.x = -0.52 + offsetX;
      this.pupilL.position.y = 0.44 + offsetY;
      this.pupilR.position.x = 0.12 + offsetX;
      this.pupilR.position.y = 0.44 + offsetY;
    }

    // 3. Mouth talking animation while speaking
    if (this.mouth) {
      if (this.isSpeaking) {
        const talkScale = 0.3 + Math.abs(Math.sin(time * 14)) * 0.85;
        this.mouth.scale.y = talkScale;
      } else {
        this.mouth.scale.y = 0.25;
      }
    }

    this.renderer.render(this.scene, this.camera);
  }

  animate() {
    const clock = new THREE.Clock();
    const renderLoop = () => {
      requestAnimationFrame(renderLoop);
      this.update(clock.getElapsedTime());
    };
    renderLoop();
  }
}

let goldieMascot = null;

// ============================================================
// DEDICATED 3D RESULTS COLUMNS (#crash-columns-canvas on Slide 11)
// ============================================================

class CrashColumnsRenderer {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;

    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.colCrash = null;
    this.colOther = null;
    this.hasAnimated = false;

    this.init();
  }

  init() {
    const width = this.canvas.clientWidth || 480;
    const height = this.canvas.clientHeight || 190;

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(36, width / height, 0.1, 50);
    this.camera.position.set(0, 0.45, 4.6);

    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      alpha: true,
      antialias: true,
      powerPreference: 'high-performance'
    });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    // Lighting
    const keyLight = new THREE.DirectionalLight(0xFFF2C2, 2.0);
    keyLight.position.set(3, 4, 3);
    this.scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight(0x93A3B4, 1.0);
    fillLight.position.set(-3, 2, 2);
    this.scene.add(fillLight);

    const ambLight = new THREE.AmbientLight(0x18232F, 1.2);
    this.scene.add(ambLight);

    // Dedicated underglow for red column (-₹24,387) below floor
    const redUnderLight = new THREE.PointLight(0xFF8F85, 3.2, 4.0);
    redUnderLight.position.set(1.3, -0.6, 0.6);
    this.scene.add(redUnderLight);

    // Dedicated uplight for green column (+₹1,37,985)
    const greenUpLight = new THREE.PointLight(0x4FD1A1, 2.2, 5.0);
    greenUpLight.position.set(-1.3, 1.4, 0.8);
    this.scene.add(greenUpLight);

    // Semi-transparent floor plane at y = 0
    const floorGeom = new THREE.BoxGeometry(5.6, 0.02, 1.8);
    const floorMat = new THREE.MeshStandardMaterial({
      color: 0x0F1822,
      metalness: 0.8,
      roughness: 0.2,
      transparent: true,
      opacity: 0.35,
      depthWrite: false,
    });
    const floor = new THREE.Mesh(floorGeom, floorMat);
    floor.position.set(0, 0, 0);
    this.scene.add(floor);

    // Glowing equator zero-line at y = 0
    const lineGeom = new THREE.BoxGeometry(5.6, 0.02, 0.04);
    const lineMat = new THREE.MeshBasicMaterial({ color: 0xF2A93B });
    const zeroLine = new THREE.Mesh(lineGeom, lineMat);
    zeroLine.position.set(0, 0.01, 0);
    this.scene.add(zeroLine);

    // 1. Gold/Green Rising Column: +₹1,37,985 (8 Crash Trades)
    const crashGeom = new RoundedBoxGeometry(0.95, 1.0, 0.95, 4, 0.06);
    const crashMat = new THREE.MeshStandardMaterial({
      color: 0x4FD1A1,
      metalness: 0.4,
      roughness: 0.2,
      emissive: 0x228B5E,
      emissiveIntensity: 0.6,
    });
    this.colCrash = new THREE.Mesh(crashGeom, crashMat);
    this.colCrash.position.set(-1.3, 0.001, 0);
    this.colCrash.scale.set(1.0, 0.001, 1.0);
    this.scene.add(this.colCrash);

    // 2. Bright Red Dipping Column: -₹24,387 (12 Other Trades)
    const otherGeom = new RoundedBoxGeometry(0.95, 1.0, 0.95, 4, 0.06);
    const otherMat = new THREE.MeshStandardMaterial({
      color: 0xFF8F85,
      metalness: 0.3,
      roughness: 0.2,
      emissive: 0xFF4D3D,
      emissiveIntensity: 0.85,
    });
    this.colOther = new THREE.Mesh(otherGeom, otherMat);
    this.colOther.position.set(1.3, -0.001, 0);
    this.colOther.scale.set(1.0, 0.001, 1.0);
    this.scene.add(this.colOther);

    window.addEventListener('resize', () => this.onResize());
    this.animateLoop();
  }

  onResize() {
    if (!this.canvas) return;
    const width = this.canvas.clientWidth || 480;
    const height = this.canvas.clientHeight || 190;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }

  forceFinal() {
    if (!this.colCrash || !this.colOther) return;
    gsap.killTweensOf(this.colCrash.scale);
    gsap.killTweensOf(this.colOther.scale);

    const t = this.targets();
    this.colCrash.scale.set(1.0, t.crashH, 1.0);
    this.colCrash.position.y = t.crashSign * t.crashH * 0.5;
    this.colOther.scale.set(1.0, t.otherH, 1.0);
    this.colOther.position.y = t.otherSign * t.otherH * 0.5;
  }

  // heights and directions from the data (pitch/data.js sets window.GRV_CRASH); up = profit, down = loss
  targets() {
    const v = window.GRV_CRASH || { crash: 137985, other: -24387 };
    const mx = Math.max(1, Math.abs(v.crash), Math.abs(v.other));
    const paint = (mesh, val) => {
      const up = val >= 0;
      mesh.material.color.setHex(up ? 0x4FD1A1 : 0xFF8F85);
      mesh.material.emissive.setHex(up ? 0x228B5E : 0xFF4D3D);
    };
    paint(this.colCrash, v.crash); paint(this.colOther, v.other);
    return { crashH: Math.max(0.04, 2.0 * Math.abs(v.crash) / mx), crashSign: v.crash >= 0 ? 1 : -1,
             otherH: Math.max(0.04, 2.0 * Math.abs(v.other) / mx), otherSign: v.other >= 0 ? 1 : -1 };
  }

  triggerAnimation() {
    if (!this.colCrash || !this.colOther) return;

    const t = this.targets();

    this.colCrash.scale.set(1.0, 0.001, 1.0);
    this.colCrash.position.y = 0.001 * t.crashSign;

    this.colOther.scale.set(1.0, 0.001, 1.0);
    this.colOther.position.y = 0.001 * t.otherSign;

    gsap.to(this.colCrash.scale, {
      y: t.crashH,
      duration: 1.5,
      ease: 'power3.out',
      onUpdate: () => {
        this.colCrash.position.y = t.crashSign * this.colCrash.scale.y * 0.5;
      }
    });

    gsap.to(this.colOther.scale, {
      y: t.otherH,
      duration: 1.3,
      delay: 0.25,
      ease: 'power3.out',
      onUpdate: () => {
        this.colOther.position.y = t.otherSign * this.colOther.scale.y * 0.5;
      }
    });
  }

  animateLoop() {
    const clock = new THREE.Clock();
    const loop = () => {
      requestAnimationFrame(loop);
      const time = clock.getElapsedTime();

      // Gentle camera orbit
      if (this.camera) {
        this.camera.position.x = Math.sin(time * 0.4) * 0.45;
        this.camera.lookAt(0, 0.2, 0);
      }
      if (this.renderer && this.scene && this.camera) {
        this.renderer.render(this.scene, this.camera);
      }
    };
    loop();
  }
}

let crashColumnsRenderer = null;

// ============================================================
// MAIN 3D SCENE (STAGE 1 OPENING & STAGE 2 BARS)
// ============================================================

class Main3DWorld {
  constructor() {
    this.canvas = document.getElementById('bg-canvas');
    if (!this.canvas) {
      console.error('bg-canvas not found');
      initFallback2D();
      return;
    }

    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.composer = null;
    this.particleSystem = null;
    this.particlePositions = [];
    this.particleTargets = [];
    this.particleSpeeds = [];
    this.barsGroup = null;
    this.contractBars = {};
    this.slide17Logo = null;
    this.raycaster = new THREE.Raycaster();
    this.hoveredBar = null;

    this.init();
  }

  init() {
    const width = window.innerWidth;
    const height = window.innerHeight;

    // 1. Scene & Camera
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x000000);

    this.camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
    this.camera.position.set(0, 0.2, 12.5);

    // 2. WebGL Renderer
    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      antialias: true,
      powerPreference: 'high-performance',
      alpha: false,
    });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.25;

    // 3. Post-Processing: UnrealBloomPass
    try {
      const renderPass = new RenderPass(this.scene, this.camera);
      const bloomPass = new UnrealBloomPass(
        new THREE.Vector2(width, height),
        0.45,  // subtle strength
        0.5,   // radius
        0.82   // threshold
      );
      this.composer = new EffectComposer(this.renderer);
      this.composer.addPass(renderPass);
      this.composer.addPass(bloomPass);
    } catch (e) {
      this.composer = null;
    }

    // 4. Lights
    const ambientLight = new THREE.AmbientLight(0x221B12, 1.2);
    this.scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xFFE5A3, 2.2);
    dirLight.position.set(5, 8, 7);
    this.scene.add(dirLight);

    const rimLight = new THREE.DirectionalLight(0x975600, 1.6);
    rimLight.position.set(-6, -4, -5);
    this.scene.add(rimLight);

    this.pointLight = new THREE.PointLight(0xF2A93B, 2.0, 20);
    this.pointLight.position.set(0, 2, 4);
    this.scene.add(this.pointLight);

    // 5. Environment Map
    try {
      const pmrem = new THREE.PMREMGenerator(this.renderer);
      this.scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    } catch (e) {}

    // 6. Build Elements
    this.setupParticles();
    this.setupContractBars();
    this.setupSlide17Visuals();

    // 7. Event Listeners
    window.addEventListener('resize', () => this.onResize());
    window.addEventListener('pointermove', (e) => this.onPointerMove(e));

    this.animate();
  }

  setupParticles() {
    const count = 1800;
    const geom = new THREE.BufferGeometry();
    const positions = new Float32Array(count * 3);
    const targets = new Float32Array(count * 3);
    const colors = new Float32Array(count * 3);
    const speeds = new Float32Array(count);

    const goldPalette = [
      new THREE.Color(0xF2A93B),
      new THREE.Color(0xFFE082),
      new THREE.Color(0xDCA335),
      new THREE.Color(0xB56E0D),
    ];

    for (let i = 0; i < count; i++) {
      const i3 = i * 3;
      // Start in a wide cinematic space
      positions[i3] = (Math.random() - 0.5) * 24;
      positions[i3 + 1] = (Math.random() - 0.5) * 16;
      positions[i3 + 2] = (Math.random() - 0.5) * 12;

      // Targets: Form the Nexora Logo (2 Gold Bars, bottom one shifted right)
      const isTopBar = i < count * 0.5;
      let tx, ty, tz;
      if (isTopBar) {
        tx = -0.5 + (Math.random() - 0.5) * 3.6;
        ty = 0.7 + (Math.random() - 0.5) * 0.95;
        tz = (Math.random() - 0.5) * 0.4;
      } else {
        tx = 0.5 + (Math.random() - 0.5) * 3.6; // shifted right
        ty = -0.7 + (Math.random() - 0.5) * 0.95;
        tz = (Math.random() - 0.5) * 0.4;
      }
      targets[i3] = tx;
      targets[i3 + 1] = ty;
      targets[i3 + 2] = tz;

      const col = goldPalette[Math.floor(Math.random() * goldPalette.length)];
      colors[i3] = col.r;
      colors[i3 + 1] = col.g;
      colors[i3 + 2] = col.b;

      speeds[i] = 0.3 + Math.random() * 0.7;
    }

    geom.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geom.setAttribute('color', new THREE.BufferAttribute(colors, 3));

    // Particle texture
    const pCanvas = document.createElement('canvas');
    pCanvas.width = 32;
    pCanvas.height = 32;
    const pCtx = pCanvas.getContext('2d');
    const grad = pCtx.createRadialGradient(16, 16, 0, 16, 16, 16);
    grad.addColorStop(0, 'rgba(255,255,255,1)');
    grad.addColorStop(0.35, 'rgba(242,169,59,0.85)');
    grad.addColorStop(1, 'rgba(0,0,0,0)');
    pCtx.fillStyle = grad;
    pCtx.fillRect(0, 0, 32, 32);
    const pTexture = new THREE.CanvasTexture(pCanvas);

    const mat = new THREE.PointsMaterial({
      size: 1.5,
      sizeAttenuation: false,
      vertexColors: true,
      map: pTexture,
      transparent: true,
      opacity: 0.35,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });

    this.particleSystem = new THREE.Points(geom, mat);
    this.scene.add(this.particleSystem);

    this.particlePositions = positions;
    this.particleTargets = targets;
    this.particleSpeeds = speeds;
  }

  setupContractBars() {
    this.barsGroup = new THREE.Group();
    this.scene.add(this.barsGroup);
    this.barsGroup.visible = false;

    const goldMat = new THREE.MeshStandardMaterial({
      color: 0xF2A93B,
      metalness: 0.7,
      roughness: 0.28,
    });

    Object.keys(contractData).forEach((key) => {
      const data = contractData[key];
      const geom = new RoundedBoxGeometry(data.size[0], data.size[1], data.size[2], 4, 0.08);
      const mesh = new THREE.Mesh(geom, goldMat.clone());
      mesh.position.set(...data.posRaw);
      mesh.userData = { key, data, basePos: [...data.posRaw] };

      this.barsGroup.add(mesh);
      this.contractBars[key] = mesh;
    });
  }

  setupSlide17Visuals() {
    this.slide17Logo = new THREE.Group();
    this.scene.add(this.slide17Logo);
    this.slide17Logo.visible = false;
    this.slide17Logo.position.set(0, 0.6, -3);

    const goldMat = new THREE.MeshStandardMaterial({
      color: 0xF2A93B,
      metalness: 0.7,
      roughness: 0.28,
    });

    const barGeom = new RoundedBoxGeometry(3.2, 1.2, 0.9, 4, 0.14);
    const topBar = new THREE.Mesh(barGeom, goldMat);
    topBar.position.set(-0.35, 0.7, 0);
    this.slide17Logo.add(topBar);

    const bottomBar = new THREE.Mesh(barGeom, goldMat);
    bottomBar.position.set(0.45, -0.7, 0); // shifted right!
    this.slide17Logo.add(bottomBar);
  }

  onResize() {
    const width = window.innerWidth;
    const height = window.innerHeight;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
    if (this.composer) this.composer.setSize(width, height);
  }

  onPointerMove(e) {
    state.pointer.x = e.clientX;
    state.pointer.y = e.clientY;
    state.pointer.ndcX = (e.clientX / window.innerWidth) * 2 - 1;
    state.pointer.ndcY = -(e.clientY / window.innerHeight) * 2 + 1;

    // Raycast on Stage 2 contract bars
    if (state.currentStage === '3d-bars' && this.barsGroup && this.barsGroup.visible) {
      this.raycaster.setFromCamera(
        new THREE.Vector2(state.pointer.ndcX, state.pointer.ndcY),
        this.camera
      );
      const intersects = this.raycaster.intersectObjects(this.barsGroup.children);
      const hoverCard = document.getElementById('hover-card-3d');

      if (intersects.length > 0) {
        const hit = intersects[0].object;
        if (this.hoveredBar !== hit) {
          if (this.hoveredBar) this.hoveredBar.material.emissive.setHex(0x000000);
          this.hoveredBar = hit;
          hit.material.emissive.setHex(0x3B2808);

          if (hoverCard && hit.userData && hit.userData.data) {
            document.getElementById('hover-card-title').textContent = hit.userData.data.name;
            document.getElementById('hover-card-raw').textContent = hit.userData.data.raw;
            document.getElementById('hover-card-pure').textContent = hit.userData.data.pure;
            hoverCard.classList.add('visible');
          }
        }

        if (hoverCard) {
          hoverCard.style.left = `${e.clientX}px`;
          hoverCard.style.top = `${e.clientY}px`;
        }
      } else {
        if (this.hoveredBar) {
          this.hoveredBar.material.emissive.setHex(0x000000);
          this.hoveredBar = null;
        }
        if (hoverCard) hoverCard.classList.remove('visible');
      }
    }
  }

  normalizeContractBars() {
    state.isNormalized = true;
    Object.keys(this.contractBars).forEach((key) => {
      const bar = this.contractBars[key];
      const data = contractData[key];
      gsap.to(bar.position, {
        x: data.posNorm[0],
        y: data.posNorm[1],
        z: data.posNorm[2],
        duration: 1.2,
        ease: 'power3.inOut',
      });
      gsap.to(bar.scale, {
        x: data.scaleNorm[0] / data.size[0],
        y: data.scaleNorm[1] / data.size[1],
        z: data.scaleNorm[2] / data.size[2],
        duration: 1.2,
        ease: 'power3.inOut',
      });
    });

    const callout = document.getElementById('normalize-callout');
    if (callout) callout.classList.add('visible');
    voiceController.speak(spokenLines.stage2);
  }

  showStage(stage) {
    state.currentStage = stage;
    const hoverCard = document.getElementById('hover-card-3d');
    if (hoverCard) hoverCard.classList.remove('visible');

    if (stage === 'opening') {
      this.barsGroup.visible = false;
      if (this.slide17Logo) this.slide17Logo.visible = false;
      document.body.classList.remove('stage-3d-active');
      gsap.to(this.camera.position, { x: 0, y: 0.2, z: 12.5, duration: 1.2 });
    } else if (stage === '3d-bars') {
      this.barsGroup.visible = true;
      if (this.slide17Logo) this.slide17Logo.visible = false;
      document.body.classList.add('stage-3d-active');
      gsap.to(this.camera.position, { x: 0, y: 0.6, z: 12.0, duration: 1.2, ease: 'power3.out' });
      voiceController.speak(spokenLines.stage2);
    } else if (stage === 'slides') {
      this.barsGroup.visible = false;
      document.body.classList.remove('stage-3d-active');
    }
  }

  animateSlideVisuals(slideNum) {
    if (this.slide17Logo) {
      this.slide17Logo.visible = (slideNum === 17);
      if (goldieMascot) goldieMascot.setWaving(slideNum === 17);
    }
  }

  update(time) {
    // 1. Particle Motion & Logo Morphing
    if (this.particleSystem) {
      const positions = this.particleSystem.geometry.attributes.position.array;
      const count = positions.length / 3;

      if (state.currentStage === 'opening') {
        for (let i = 0; i < count; i++) {
          const i3 = i * 3;
          positions[i3] += (this.particleTargets[i3] - positions[i3]) * 0.04;
          positions[i3 + 1] += (this.particleTargets[i3 + 1] - positions[i3 + 1]) * 0.04;
          positions[i3 + 2] += (this.particleTargets[i3 + 2] - positions[i3 + 2]) * 0.04;
        }
      } else {
        for (let i = 0; i < count; i++) {
          const i3 = i * 3;
          positions[i3 + 1] -= this.particleSpeeds[i] * 0.015;
          if (positions[i3 + 1] < -10) positions[i3 + 1] = 10;
        }
      }
      this.particleSystem.geometry.attributes.position.needsUpdate = true;
    }

    // 2. Parallax camera drift
    if (this.camera) {
      const targetCamX = state.pointer.ndcX * 0.8;
      const targetCamY = 0.2 + state.pointer.ndcY * 0.4;
      this.camera.position.x += (targetCamX - this.camera.position.x) * 0.05;
      this.camera.position.y += (targetCamY - this.camera.position.y) * 0.05;
      this.camera.lookAt(0, 0.4, 0);
    }

    // 3. Contract Bars rotation
    if (this.barsGroup && this.barsGroup.visible) {
      Object.keys(this.contractBars).forEach((key, idx) => {
        const bar = this.contractBars[key];
        bar.rotation.y = Math.sin(time * 0.8 + idx) * 0.18;
        bar.rotation.x = Math.cos(time * 0.6 + idx) * 0.12;
      });
    }

    // 4. Slide 17 Logo slow spin
    if (this.slide17Logo && this.slide17Logo.visible) {
      this.slide17Logo.rotation.y = Math.sin(time * 0.6) * 0.25;
    }

    // 5. Point light drift
    if (this.pointLight) {
      this.pointLight.position.x = Math.sin(time * 0.7) * 5;
      this.pointLight.position.y = Math.cos(time * 0.5) * 3;
    }

    // Render pass
    if (this.composer) {
      this.composer.render();
    } else {
      this.renderer.render(this.scene, this.camera);
    }
  }

  animate() {
    const clock = new THREE.Clock();
    const renderLoop = () => {
      requestAnimationFrame(renderLoop);
      this.update(clock.getElapsedTime());
    };
    renderLoop();
  }
}

let main3DWorld = null;

// ============================================================
// PRESENTATION SLIDES MANAGER (KEYNOTE STYLE - 17 SLIDES)
// ============================================================

class PitchDeckManager {
  constructor() {
    this.slidesContainer = document.getElementById('slides-container');
    this.stageOpening = document.getElementById('stage-opening');
    this.stage3dUi = document.getElementById('stage-3d-ui');
    this.progressBar = document.getElementById('top-progress-bar');
    this.slideBadge = document.getElementById('slide-counter-badge');
    this.notesPanel = document.getElementById('speaker-notes-panel');
    this.notesContent = document.getElementById('notes-content');
    this.goldieWrap = document.getElementById('goldie-canvas-wrap');
    this.failsafeTimeout = null;

    this.bindEvents();
    this.updateNotes();
  }

  bindEvents() {
    // Stage 1 Button
    const btnBegin = document.getElementById('btn-begin');
    if (btnBegin) {
      btnBegin.addEventListener('click', () => {
        this.goTo3DScene();
      });
    }

    // Stage 2 Buttons
    const btnNormalize = document.getElementById('btn-normalize-bars');
    if (btnNormalize) {
      btnNormalize.addEventListener('click', () => {
        if (main3DWorld) main3DWorld.normalizeContractBars();
      });
    }

    const btnOpenPitch = document.getElementById('btn-open-pitch');
    if (btnOpenPitch) {
      btnOpenPitch.addEventListener('click', () => {
        this.goToPitch(1);
      });
    }

    // Header Controls
    const btnBack3D = document.getElementById('btn-back-3d');
    if (btnBack3D) {
      btnBack3D.addEventListener('click', () => this.goTo3DScene());
    }

    const btnOpenGrid = document.getElementById('btn-open-grid');
    if (btnOpenGrid) {
      btnOpenGrid.addEventListener('click', () => this.toggleGridModal());
    }

    const btnCloseGrid = document.getElementById('btn-close-grid');
    if (btnCloseGrid) {
      btnCloseGrid.addEventListener('click', () => this.toggleGridModal(false));
    }

    const modal = document.getElementById('overview-grid-modal');
    if (modal) {
      modal.addEventListener('click', (e) => {
        if (e.target === modal || e.target.id === 'grid-backdrop') this.toggleGridModal(false);
      });
    }

    const btnToggleNotes = document.getElementById('btn-toggle-notes');
    if (btnToggleNotes) {
      btnToggleNotes.addEventListener('click', () => this.toggleNotes());
    }

    const btnCloseNotes = document.getElementById('btn-close-notes');
    if (btnCloseNotes) {
      btnCloseNotes.addEventListener('click', () => this.toggleNotes(false));
    }

    const btnToggleVoice = document.getElementById('btn-toggle-voice');
    if (btnToggleVoice) {
      btnToggleVoice.addEventListener('click', () => this.toggleVoice());
    }

    const btnToggleMascot = document.getElementById('btn-toggle-mascot');
    if (btnToggleMascot) {
      btnToggleMascot.addEventListener('click', () => this.toggleMascot());
    }

    const btnFullscreen = document.getElementById('btn-fullscreen');
    if (btnFullscreen) {
      btnFullscreen.addEventListener('click', () => this.toggleFullscreen());
    }

    // Prev / Next Floating Arrows
    const btnPrev = document.getElementById('btn-prev-slide');
    if (btnPrev) btnPrev.addEventListener('click', () => this.prevSlide());

    const btnNext = document.getElementById('btn-next-slide');
    if (btnNext) btnNext.addEventListener('click', () => this.nextSlide());

    // Click on Mascot repeats the spoken line
    if (this.goldieWrap) {
      this.goldieWrap.addEventListener('click', () => {
        const text = state.currentStage === 'slides'
          ? spokenLines[state.currentSlide]
          : spokenLines[state.currentStage === 'opening' ? 'opening' : 'stage2'];
        voiceController.speak(text);
      });
    }

    // Keyboard Shortcuts
    window.addEventListener('keydown', (e) => this.onKeyDown(e));
  }

  onKeyDown(e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    switch (e.key) {
      case ' ':
      case 'ArrowRight':
      case 'PageDown':
        e.preventDefault();
        if (state.currentStage === 'opening') {
          this.goTo3DScene();
        } else if (state.currentStage === '3d-bars') {
          this.goToPitch(1);
        } else {
          this.nextSlide();
        }
        break;

      case 'ArrowLeft':
      case 'PageUp':
        e.preventDefault();
        if (state.currentStage === 'slides') {
          this.prevSlide();
        }
        break;

      case 'Escape':
        e.preventDefault();
        const gridModal = document.getElementById('overview-grid-modal');
        if (gridModal && gridModal.classList.contains('open')) {
          this.toggleGridModal(false);
          return;
        }
        if (state.notesVisible) {
          this.toggleNotes(false);
          return;
        }
        this.goTo3DScene();
        break;

      case 'g':
      case 'G':
        e.preventDefault();
        this.toggleGridModal();
        break;

      case 'n':
      case 'N':
        e.preventDefault();
        this.toggleNotes();
        break;

      case 'v':
      case 'V':
        e.preventDefault();
        this.toggleVoice();
        break;

      case 'm':
      case 'M':
        e.preventDefault();
        this.toggleMascot();
        break;

      case 'f':
      case 'F':
        e.preventDefault();
        this.toggleFullscreen();
        break;

      case '1':
      case '2':
      case '3':
      case '4':
      case '5':
      case '6':
      case '7':
      case '8':
      case '9':
        e.preventDefault();
        const slideNum = parseInt(e.key, 10);
        this.goToPitch(slideNum);
        break;
    }
  }

  buildOverviewGrid() {
    const gridEl = document.getElementById('overview-grid-cards');
    if (!gridEl) return;
    gridEl.innerHTML = '';

    const slideMeta = [
      { num: 1, tag: "Title & Team", title: "Cross-Contract Relative Value" },
      { num: 2, tag: "The Problem", title: "Four Contracts, Four Prices" },
      { num: 3, tag: "Step 1", title: "Price Every Contract The Same Way" },
      { num: 4, tag: "Step 2", title: "Watch The Gap Over Three Years" },
      { num: 5, tag: "Step 3", title: "The Z-Score: How Unusual Is Today?" },
      { num: 6, tag: "Step 4", title: "The Cost & Margin Hurdle" },
      { num: 7, tag: "Live Example", title: "The 5 Safeguard Checks" },
      { num: 8, tag: "Step 5", title: "The Walk-Forward Test" },
      { num: 9, tag: "Headline Results", title: "Out-Of-Sample Performance" },
      { num: 10, tag: "Attribution", title: "Results Broken Down By Pair" },
      { num: 11, tag: "Attribution", title: "Where Did The Profit Come From?" },
      { num: 12, tag: "Sensitivity", title: "Execution Slippage Sensitivity" },
      { num: 13, tag: "Market Reality", title: "The 'Normal' Gap Moves Over Time" },
      { num: 14, tag: "Engineering", title: "Architecture & Data Quality" },
      { num: 15, tag: "Commercial Scope", title: "Market Opportunity & Scale" },
      { num: 16, tag: "Summary", title: "Key Takeaways & Future Scope" },
      { num: 17, tag: "Conclusion", title: "Thank You & Live Terminal" }
    ];

    slideMeta.forEach((meta) => {
      const card = document.createElement('div');
      card.className = `grid-slide-card ${meta.num === state.currentSlide ? 'active-slide-card' : ''}`;
      card.dataset.targetSlide = meta.num;
      card.innerHTML = `
        <div class="grid-card-top-row">
          <span class="grid-card-num">Slide ${meta.num}</span>
          <span class="grid-card-tag">${meta.tag}</span>
        </div>
        <div class="grid-card-title">${meta.title}</div>
      `;
      card.addEventListener('click', () => {
        this.goToPitch(meta.num);
        this.toggleGridModal(false);
      });
      gridEl.appendChild(card);
    });
  }

  toggleGridModal(forceState) {
    const modal = document.getElementById('overview-grid-modal');
    if (!modal) return;
    const isOpen = typeof forceState === 'boolean' ? forceState : !modal.classList.contains('open');
    modal.classList.toggle('open', isOpen);

    if (isOpen) {
      this.buildOverviewGrid();
    }
  }

  goTo3DScene() {
    state.currentStage = '3d-bars';
    voiceController.stop();

    if (this.stageOpening) this.stageOpening.classList.add('hidden');
    if (this.stage3dUi) this.stage3dUi.classList.add('active');
    if (this.slidesContainer) this.slidesContainer.classList.remove('active');

    if (main3DWorld) main3DWorld.showStage('3d-bars');
  }

  goToPitch(slideNum) {
    state.currentStage = 'slides';
    if (this.stageOpening) this.stageOpening.classList.add('hidden');
    if (this.stage3dUi) this.stage3dUi.classList.remove('active');
    if (this.slidesContainer) this.slidesContainer.classList.add('active');

    if (main3DWorld) main3DWorld.showStage('slides');
    this.goToSlide(slideNum);
  }

  goToSlide(slideNum) {
    if (slideNum < 1) slideNum = 1;
    if (slideNum > state.totalSlides) slideNum = state.totalSlides;
    state.currentSlide = slideNum;

    // 1. Update Progress Bar & Badge
    const pct = ((slideNum) / state.totalSlides) * 100;
    if (this.progressBar) this.progressBar.style.width = `${pct}%`;
    if (this.slideBadge) this.slideBadge.textContent = `${slideNum} / ${state.totalSlides}`;

    // 2. Hide old slide & show new slide with GSAP staggered entrance
    const allPanels = document.querySelectorAll('.slide-panel');
    allPanels.forEach((panel) => {
      const idx = parseInt(panel.dataset.slide, 10);
      if (idx === slideNum) {
        panel.classList.add('active');
        const animElements = panel.querySelectorAll(
          '.keynote-h1, .keynote-lead, .roster-card, .price-tile, .direction-box, ' +
          '.stat-cell-cinematic, .market-box-cinematic, .check-hero-card, .thank-you-big, ' +
          '.links-row, .crash-columns-card, .chart-card-cinematic, .how-to-read-card, ' +
          '.formula-banner, .walk-forward-timeline, .safeguard-card, .takeaway-item, ' +
          '.roadmap-phase-card, .data-quality-strip'
        );
        gsap.fromTo(animElements, 
          { opacity: 0, y: 20 },
          { opacity: 1, y: 0, stagger: 0.06, duration: 0.55, ease: 'power2.out', clearProps: 'transform' }
        );
      } else {
        panel.classList.remove('active');
      }
    });

    // 3. Animate 3D World visuals for current slide
    if (main3DWorld) {
      main3DWorld.animateSlideVisuals(slideNum);
    }

    // 4. Slide-specific interactive animations
    this.runSlideSpecificAnimations(slideNum);

    // 5. Update Speaker Notes
    this.updateNotes();

    // 6. Speak slide line
    voiceController.speak(spokenLines[slideNum]);

    // 7. Slow-laptop safety: after 2.5 seconds force every animated element on that slide to its final state
    if (this.failsafeTimeout) {
      clearTimeout(this.failsafeTimeout);
      this.failsafeTimeout = null;
    }
    this.failsafeTimeout = setTimeout(() => {
      this.forceSlideFinalState(slideNum);
    }, 2500);
  }

  forceSlideFinalState(slideNum) {
    const panel = document.getElementById(`slide-${slideNum}`);
    if (!panel) return;

    // 1. Force all animated elements on this slide to final opacity 1 and transform none
    const animElements = panel.querySelectorAll(
      '.keynote-h1, .keynote-lead, .roster-card, .price-tile, .direction-box, ' +
      '.stat-cell-cinematic, .market-box-cinematic, .check-hero-card, .thank-you-big, ' +
      '.links-row, .crash-columns-card, .gap-banner-cinematic, .results-table-wrap, ' +
      '.verdict-banner-cinematic, .roadmap-col-cinematic, .flow-step-node, .check-row-cinematic, ' +
      '.chart-card-cinematic, .how-to-read-card, .formula-banner, .walk-forward-timeline, ' +
      '.safeguard-card, .takeaway-item, .roadmap-phase-card, .data-quality-strip'
    );
    animElements.forEach((el) => {
      gsap.killTweensOf(el);
      el.style.opacity = '1';
      el.style.transform = 'none';
    });

    // 2. Reset SVG path animations to fully drawn
    const paths = panel.querySelectorAll('path');
    paths.forEach(p => {
      gsap.killTweensOf(p);
      p.style.strokeDashoffset = '0';
    });

    // 3. Reset SVG bar animations
    const barsW = panel.querySelectorAll('rect[data-target-width]');
    barsW.forEach(b => {
      gsap.killTweensOf(b);
      b.setAttribute('width', b.dataset.targetWidth);
    });
    const barsH = panel.querySelectorAll('rect[data-target-height]');
    barsH.forEach(b => {
      gsap.killTweensOf(b);
      b.setAttribute('y', b.dataset.targetY);
      b.setAttribute('height', b.dataset.targetHeight);
    });

    // 4. Reset dots
    const dots = panel.querySelectorAll('.chart-dot-anim');
    dots.forEach(d => {
      gsap.killTweensOf(d);
      d.style.opacity = '1';
    });

    // 5. Specific slide enforcements
    if (slideNum === 7) {
      for (let i = 1; i <= 5; i++) {
        const row = document.getElementById(`check-row-${i}`);
        if (row) row.classList.add('lit');
      }
    }

    if (slideNum === 9) {
      const counters = panel.querySelectorAll('.counter-stat');
      counters.forEach((el) => {
        gsap.killTweensOf(el);
        // final value straight from the element's data attributes (pitch/data.js fills them from the pipeline's JSON)
        const v = parseFloat(el.dataset.target);
        const dec = parseInt(el.dataset.decimals || '0', 10);
        const body = el.dataset.indian === 'true' ? Math.round(v).toLocaleString('en-IN') : v.toFixed(dec);
        el.textContent = (el.dataset.prefix || '') + body;
      });
    }

    if (slideNum === 11) {
      if (crashColumnsRenderer) {
        crashColumnsRenderer.forceFinal();
      }
    }

    if (slideNum === 14) {
      for (let i = 1; i <= 5; i++) {
        const node = document.getElementById(`arch-node-${i}`);
        if (node) node.classList.remove('active-gold');
      }
    }
  }

  nextSlide() {
    if (state.currentSlide < state.totalSlides) {
      this.goToSlide(state.currentSlide + 1);
    }
  }

  prevSlide() {
    if (state.currentSlide > 1) {
      this.goToSlide(state.currentSlide - 1);
    }
  }

  runSlideSpecificAnimations(slideNum) {
    const panel = document.getElementById(`slide-${slideNum}`);
    if (!panel) return;

    // Slide 3: Normalization bars grow
    if (slideNum === 3) {
      const bars = panel.querySelectorAll('.chart-bar-anim');
      bars.forEach((b, i) => {
        const targetW = parseFloat(b.dataset.targetWidth || b.getAttribute('width'));
        gsap.fromTo(b, { attr: { width: 0 } }, { attr: { width: targetW }, duration: 0.8, delay: i * 0.1, ease: 'power2.out' });
      });
    }

    // Slide 4: 3-Year Gap Line & Dots
    if (slideNum === 4) {
      const line = panel.querySelector('.chart-line-anim');
      if (line) {
        try {
          const len = line.getTotalLength();
          line.style.strokeDasharray = `${len} ${len}`;
          gsap.fromTo(line, { strokeDashoffset: len }, { strokeDashoffset: 0, duration: 1.2, ease: 'power2.out' });
        } catch (e) {}
      }
      const dots = panel.querySelectorAll('.chart-dot-anim');
      gsap.fromTo(dots, { opacity: 0, scale: 0 }, { opacity: 1, scale: 1, duration: 0.45, stagger: 0.02, delay: 0.5, ease: 'back.out(2)' });
    }

    // Slide 5: Bell Curve
    if (slideNum === 5) {
      const curve = panel.querySelector('.chart-curve-anim');
      if (curve) {
        try {
          const len = curve.getTotalLength();
          curve.style.strokeDasharray = `${len} ${len}`;
          gsap.fromTo(curve, { strokeDashoffset: len }, { strokeDashoffset: 0, duration: 1.0, ease: 'power2.out' });
        } catch (e) {}
      }
    }

    // Slide 6: Cost Hurdle Bars
    if (slideNum === 6) {
      const bars = panel.querySelectorAll('.hurdle-bar-anim');
      bars.forEach((b, i) => {
        const targetW = parseFloat(b.dataset.targetWidth || b.getAttribute('width'));
        gsap.fromTo(b, { attr: { width: 0 } }, { attr: { width: targetW }, duration: 0.8, delay: i * 0.08, ease: 'power2.out' });
      });
    }

    // Slide 7: The 5 Checks sequential illumination
    if (slideNum === 7) {
      const checkRows = [
        document.getElementById('check-row-1'),
        document.getElementById('check-row-2'),
        document.getElementById('check-row-3'),
        document.getElementById('check-row-4'),
        document.getElementById('check-row-5'),
      ];
      checkRows.forEach((row, i) => {
        if (!row) return;
        row.classList.remove('lit');
        setTimeout(() => {
          row.classList.add('lit');
        }, (i + 1) * 200);
      });
    }

    // Slide 9: Number counters animation
    if (slideNum === 9) {
      const counters = panel.querySelectorAll('.counter-stat');
      counters.forEach((el) => {
        const target = parseFloat(el.dataset.target);
        const prefix = el.dataset.prefix || '';
        const decimals = parseInt(el.dataset.decimals || '0', 10);
        const isIndian = el.dataset.indian === 'true';

        const obj = { val: 0 };
        gsap.to(obj, {
          val: target,
          duration: 1.4,
          ease: 'power2.out',
          onUpdate: () => {
            let formatted;
            if (isIndian) {
              formatted = prefix + formatIndian(obj.val);
            } else if (decimals > 0) {
              formatted = prefix + obj.val.toFixed(decimals);
            } else {
              formatted = prefix + Math.round(obj.val);
            }
            el.textContent = formatted;
          }
        });
      });
    }

    // Slide 10: Pair breakdown bars
    if (slideNum === 10) {
      const bars = panel.querySelectorAll('.pair-bar-anim');
      bars.forEach((b, i) => {
        const targetW = parseFloat(b.dataset.targetWidth || b.getAttribute('width'));
        gsap.fromTo(b, { attr: { width: 0 } }, { attr: { width: targetW }, duration: 0.8, delay: i * 0.08, ease: 'power2.out' });
      });
    }

    // Slide 11: 3D Crash Columns & Waterfall bars
    if (slideNum === 11) {
      if (crashColumnsRenderer) {
        crashColumnsRenderer.triggerAnimation();
      }
      const bars = panel.querySelectorAll('.waterfall-bar-anim');
      bars.forEach((b, i) => {
        const targetY = parseFloat(b.dataset.targetY);
        const targetH = parseFloat(b.dataset.targetHeight);
        gsap.fromTo(b, 
          { attr: { y: targetY + targetH, height: 0 } }, 
          { attr: { y: targetY, height: targetH }, duration: 0.8, delay: i * 0.1, ease: 'power2.out' }
        );
      });
    }

    // Slide 12: Slippage Sensitivity bars
    if (slideNum === 12) {
      const bars = panel.querySelectorAll('.slip-bar-anim');
      bars.forEach((b, i) => {
        const targetY = parseFloat(b.dataset.targetY);
        const targetH = parseFloat(b.dataset.targetHeight);
        gsap.fromTo(b, 
          { attr: { y: targetY + targetH, height: 0 } }, 
          { attr: { y: targetY, height: targetH }, duration: 0.7, delay: i * 0.06, ease: 'power2.out' }
        );
      });
    }

    // Slide 13: Normal Gap Drift line
    if (slideNum === 13) {
      const line = panel.querySelector('.drift-line-anim');
      if (line) {
        try {
          const len = line.getTotalLength();
          line.style.strokeDasharray = `${len} ${len}`;
          gsap.fromTo(line, { strokeDashoffset: len }, { strokeDashoffset: 0, duration: 1.2, ease: 'power2.out' });
        } catch (e) {}
      }
    }

    // Slide 14: Data Flow Gold Pulse
    if (slideNum === 14) {
      const nodes = [
        document.getElementById('arch-node-1'),
        document.getElementById('arch-node-2'),
        document.getElementById('arch-node-3'),
        document.getElementById('arch-node-4'),
        document.getElementById('arch-node-5')
      ];
      nodes.forEach((node, i) => {
        if (!node) return;
        setTimeout(() => {
          node.classList.add('active-gold');
          setTimeout(() => node.classList.remove('active-gold'), 800);
        }, i * 350);
      });
    }
  }

  updateNotes() {
    if (!this.notesContent) return;
    const note = speakerNotes[state.currentSlide] || "No notes available for this slide.";
    this.notesContent.textContent = note;
  }

  toggleNotes(forceState) {
    state.notesVisible = typeof forceState === 'boolean' ? forceState : !state.notesVisible;
    if (this.notesPanel) {
      this.notesPanel.classList.toggle('visible', state.notesVisible);
    }
    const btn = document.getElementById('btn-toggle-notes');
    if (btn) btn.classList.toggle('active', state.notesVisible);
  }

  toggleVoice() {
    state.voiceEnabled = !state.voiceEnabled;
    const btn = document.getElementById('btn-toggle-voice');
    const icon = document.getElementById('voice-icon');
    if (btn) btn.classList.toggle('active', state.voiceEnabled);
    if (icon) icon.textContent = state.voiceEnabled ? '🔊' : '🔇';

    if (!state.voiceEnabled) {
      voiceController.stop();
    } else {
      const text = state.currentStage === 'slides'
        ? spokenLines[state.currentSlide]
        : spokenLines[state.currentStage === 'opening' ? 'opening' : 'stage2'];
      voiceController.speak(text);
    }
  }

  toggleMascot() {
    state.mascotVisible = !state.mascotVisible;
    if (this.goldieWrap) {
      this.goldieWrap.classList.toggle('hidden', !state.mascotVisible);
    }
    const btn = document.getElementById('btn-toggle-mascot');
    if (btn) btn.classList.toggle('active', state.mascotVisible);
  }

  toggleFullscreen() {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
    } else {
      if (document.exitFullscreen) document.exitFullscreen();
    }
  }
}

// ============================================================
// 2D FALLBACK SYSTEM (IF WEBGL FAILS)
// ============================================================

function checkWebGLSupport() {
  try {
    const canvas = document.createElement('canvas');
    return !!(window.WebGLRenderingContext && (canvas.getContext('webgl') || canvas.getContext('experimental-webgl')));
  } catch (e) {
    return false;
  }
}

function initFallback2D() {
  console.warn("WebGL not available. Initializing high-fidelity 2D fallback.");
  document.body.classList.add('mode-2d');
  const fallbackLayer = document.getElementById('fallback-2d-layer');
  if (fallbackLayer) {
    fallbackLayer.style.display = 'block';
  }
  if (!window.pitchDeck) {
    window.pitchDeck = new PitchDeckManager();
  }
}

// ============================================================
// APP ENTRY POINT
// ============================================================

window.addEventListener('DOMContentLoaded', () => {
  if (!checkWebGLSupport()) {
    initFallback2D();
    return;
  }

  try {
    goldieMascot = new GoldieMascot('goldie-canvas');
    crashColumnsRenderer = new CrashColumnsRenderer('crash-columns-canvas');
    main3DWorld = new Main3DWorld();
    window.pitchDeck = new PitchDeckManager();

    // Initial greeting in Stage 1
    voiceController.speak(spokenLines.opening);
  } catch (err) {
    console.error("Initialization error, falling back to 2D:", err);
    initFallback2D();
  }
});
