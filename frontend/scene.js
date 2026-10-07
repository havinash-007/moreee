/* 3D layer: a galaxy of open-source organisations.
   Explore: drag to rotate, hover for details.  Ranked: your top matches fly to the front, click one to choose it.
   Purely decorative + a shortcut: every action also exists as a normal button, and it degrades to nothing without WebGL. */
(function () {
  const COLORS = { web: 0x5aa0ff, 'ai-ml-data': 0xff8a4a, 'cloud-devops': 0x2fd0b0, security: 0xff5a5a, mobile: 0xff9f43, devtools: 0x39d5ff, education: 0x8ce0c0, social: 0xa6e35a, creative: 0xff7a45 };
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const Scene = { available: false, onPick: null };
  window.Scene = Scene;

  let renderer, scene, camera, group, nodes = [], stars, ray, mouse = { x: 0, y: 0 }, ptr = { x: -9, y: -9, down: false, moved: 0 };
  let stage = 'explore', focus = [], selected = null, hovered = null, drag = { vx: 0.0016, vy: 0 }, camTarget = { x: 0, y: 0, z: 20 };
  let tip, labelBox, canvas;
  const TAU = Math.PI * 2;

  function glowTexture() {
    const c = document.createElement('canvas'); c.width = c.height = 128;
    const g = c.getContext('2d'), r = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    r.addColorStop(0, 'rgba(255,255,255,1)'); r.addColorStop(0.25, 'rgba(255,255,255,.35)'); r.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = r; g.fillRect(0, 0, 128, 128);
    return new THREE.CanvasTexture(c);
  }

  Scene.init = function (orgs) {
    if (Scene.available || !window.THREE) return;
    canvas = document.getElementById('bg'); tip = document.getElementById('tip'); labelBox = document.getElementById('labels');
    try { renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true }); } catch (e) { return; }
    Scene.available = true;
    document.documentElement.classList.add('has3d');
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(40, 1, 0.1, 200); camera.position.set(0, 0, 20);
    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const key = new THREE.PointLight(0xffffff, 1.2, 80); key.position.set(6, 8, 12); scene.add(key);

    // starfield
    const N = 900, pos = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) { const r = 40 + Math.random() * 60, a = Math.random() * TAU, b = Math.acos(2 * Math.random() - 1);
      pos[i * 3] = r * Math.sin(b) * Math.cos(a); pos[i * 3 + 1] = r * Math.sin(b) * Math.sin(a); pos[i * 3 + 2] = r * Math.cos(b); }
    const sg = new THREE.BufferGeometry(); sg.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    stars = new THREE.Points(sg, new THREE.PointsMaterial({ color: 0xdbe7ff, size: 0.35, transparent: true, opacity: 0.8, depthWrite: false }));
    scene.add(stars);

    // organisations on a golden-spiral shell
    group = new THREE.Group(); scene.add(group);
    const glow = glowTexture(), n = orgs.length, golden = Math.PI * (3 - Math.sqrt(5));
    orgs.forEach((o, i) => {
      const y = 1 - (i / (n - 1)) * 2, rad = Math.sqrt(1 - y * y), th = i * golden, R = n > 30 ? 7.4 : 6.2;
      const home = new THREE.Vector3(Math.cos(th) * rad * R, y * R * 0.75, Math.sin(th) * rad * R);
      const crowd = Math.max(0.42, Math.sqrt(14 / n)), col = COLORS[o.domains[0]] || 0x7dd3fc, size = (0.38 + o.beginner * 0.07) * crowd;
      const mesh = new THREE.Mesh(new THREE.SphereGeometry(size, n > 30 ? 16 : 32, n > 30 ? 16 : 32),
        new THREE.MeshStandardMaterial({ color: col, emissive: col, emissiveIntensity: 0.55, roughness: 0.35, metalness: 0.1, transparent: true }));
      const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: glow, color: col, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, opacity: 0.55 }));
      halo.scale.setScalar(size * 5); mesh.add(halo);
      mesh.position.copy(home); group.add(mesh);
      const label = document.createElement('div'); label.className = 'lbl'; label.textContent = o.name; labelBox.appendChild(label);
      nodes.push({ org: o, mesh, halo, home, size, base: size, label, color: col, tScale: 1, tOpacity: 1, tPos: home.clone(), phase: Math.random() * TAU });
    });

    // ring that marks the best match
    Scene.ring = new THREE.Mesh(new THREE.TorusGeometry(1, 0.025, 12, 96), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0 }));
    scene.add(Scene.ring);

    ray = new THREE.Raycaster();
    addEventListener('resize', resize); resize();
    addEventListener('pointermove', e => { mouse.x = e.clientX / innerWidth - 0.5; mouse.y = e.clientY / innerHeight - 0.5; const over = e.target === canvas; ptr.x = over ? (e.clientX / innerWidth) * 2 - 1 : -9; ptr.y = over ? -(e.clientY / innerHeight) * 2 + 1 : -9;
      if (ptr.down && stage === 'explore') { const dx = e.movementX || 0, dy = e.movementY || 0; group.rotation.y += dx * 0.006; group.rotation.x = Math.max(-1, Math.min(1, group.rotation.x + dy * 0.004)); drag.vy = dx * 0.0006; ptr.moved += Math.abs(dx) + Math.abs(dy); }
      tip.style.transform = `translate(${e.clientX + 16}px,${e.clientY + 16}px)`; });
    canvas.addEventListener('pointerdown', () => { ptr.down = true; ptr.moved = 0; });
    addEventListener('pointerup', () => {
      if (ptr.down && ptr.moved < 6 && hovered && stage === 'ranked' && focus.includes(hovered.org.name) && Scene.onPick) Scene.onPick(hovered.org.name);
      ptr.down = false; });
    document.body.classList.add('scene-ready');
    requestAnimationFrame(frame);
  };

  // Depth-of-field: blur the 3D layer (and its labels) behind content so text stays readable.
  Scene.setBlur = function (px) {
    if (!Scene.available) return;
    const v = px ? `blur(${px}px) saturate(1.1)` : 'none', sc = px ? 'scale(1.05)' : 'none';
    [canvas, labelBox].forEach((el) => { el.style.transition = 'filter .6s ease, transform .6s ease'; el.style.filter = v; el.style.transform = sc; });
  };

  function resize() { const w = innerWidth, h = innerHeight; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
    camTarget.shift = w < 700 ? 0 : 3.2; }  // push the galaxy right on wide screens so cards stay readable

  Scene.setStage = function (s, opts = {}) {
    if (!Scene.available) return;
    stage = s; focus = opts.focus || focus;
    const byName = n => nodes.find(x => x.org.name === n);
    nodes.forEach(n => { n.tScale = 1; n.tOpacity = 1; n.tPos.copy(n.home); });
    if (s === 'explore') { focus = []; selected = null; camTarget.z = nodes.length > 30 ? 22 : 20; drag.vx = 0.0016; }
    if (s === 'ranked') {
      drag.vx = 0; group.rotation.y = ((group.rotation.y % TAU) + TAU) % TAU; if (group.rotation.y > Math.PI) group.rotation.y -= TAU;
      nodes.forEach(n => { n.tOpacity = 0.18; n.tScale = 0.8; });
      focus.forEach((name, i) => { const n = byName(name); if (!n) return; const score = (opts.scores || {})[name] || 30;
        const wide = innerWidth >= 900;
        const slots = wide ? [[5.8, 4.6, 0], [3.3, 4.9, 0], [8.3, 4.9, 0]] : [[0, 5, 0], [-2.6, 5, 0], [2.6, 5, 0]];
        n.tOpacity = 1; n.tScale = 0.55 + (score / 55) * 0.45; n.tPos.set(...slots[i]); });
      camTarget.z = 17;
    }
    if (s === 'selected' || s === 'working') {
      drag.vx = 0; selected = byName(opts.pick) || null;
      nodes.forEach(n => { n.tOpacity = 0.12; n.tScale = 0.7; });
      if (selected) { selected.tOpacity = 1; selected.tScale = s === 'selected' ? 2.6 : 0.8;
        const ox = innerWidth >= 900 ? 3.4 : 0; selected.tPos.set(s === 'selected' ? ox : (innerWidth >= 900 ? 10.3 : 3.5), s === 'selected' ? 0 : -5.2, s === 'selected' ? 3 : 0); }
      camTarget.z = s === 'selected' ? 15 : 20;
    }
  };

  // Interview feedback: planets that fit the answers glow, the rest dim. Returns how many fit.
  Scene.react = function (pred) {
    if (!Scene.available || stage !== 'explore') return null;
    let c = 0;
    nodes.forEach(n => { const ok = pred(n.org); if (ok) c++; n.tOpacity = ok ? 1 : 0.16; n.tScale = ok ? 1.2 : 0.7; });
    return c;
  };

  function lerp(a, b, t) { return a + (b - a) * (reduce ? 1 : t); }

  function frame(t) {
    requestAnimationFrame(frame);
    const time = t * 0.001;
    if (stage === 'explore') { group.rotation.y += drag.vx + drag.vy; drag.vy *= 0.94; }
    else { group.rotation.x = lerp(group.rotation.x, 0, 0.06); group.rotation.y = lerp(group.rotation.y, 0, 0.06); }
    stars.rotation.y = time * 0.004;

    group.position.x = lerp(group.position.x, stage === 'explore' && innerWidth >= 900 ? (nodes.length > 30 ? 7.8 : 5.4) : 0, 0.05);
    camera.position.x = lerp(camera.position.x, mouse.x * 2.2, 0.05);
    camera.position.y = lerp(camera.position.y, -mouse.y * 1.6, 0.05);
    camera.position.z = lerp(camera.position.z, camTarget.z, 0.05);
    camera.lookAt(0, 0, 0);

    // hover
    ray.setFromCamera({ x: ptr.x, y: ptr.y }, camera);
    const hit = ray.intersectObjects(nodes.map(n => n.mesh), false)[0];
    const h = hit ? nodes.find(n => n.mesh === hit.object) : null;
    if (h !== hovered) { hovered = h; canvas.style.cursor = h && stage !== 'working' ? (stage === 'ranked' && focus.includes(h.org.name) ? 'pointer' : 'grab') : 'default'; showTip(h); }

    nodes.forEach(n => {
      const wob = reduce ? 0 : Math.sin(time * 0.8 + n.phase) * 0.06;
      n.mesh.position.x = lerp(n.mesh.position.x, n.tPos.x, 0.07);
      n.mesh.position.y = lerp(n.mesh.position.y, n.tPos.y + wob, 0.07);
      n.mesh.position.z = lerp(n.mesh.position.z, n.tPos.z, 0.07);
      const s = lerp(n.mesh.scale.x, n.tScale * (n === hovered ? 1.25 : 1), 0.1); n.mesh.scale.setScalar(s);
      n.mesh.material.opacity = lerp(n.mesh.material.opacity, n.tOpacity, 0.08);
      n.halo.material.opacity = n.mesh.material.opacity * (n === hovered ? 0.95 : 0.55);
      n.mesh.material.emissiveIntensity = n === hovered ? 1 : 0.55;
      n.mesh.rotation.y += 0.004;
      // label follows the node
      const p = n.mesh.getWorldPosition(new THREE.Vector3()).project(camera);
      const show = n.mesh.material.opacity > 0.5 || n === hovered;
      const crowded = nodes.length > 30 && stage === 'explore' && n !== hovered;
      n.label.style.opacity = show && p.z < 1 && !crowded ? (stage === 'explore' ? 0.8 : 1) : 0;
      n.label.style.transform = `translate(${(p.x * 0.5 + 0.5) * innerWidth}px,${(-p.y * 0.5 + 0.5) * innerHeight + 14 + n.mesh.scale.x * n.size * 16}px) translateX(-50%)`;
    });

    // marker ring on the best match
    const best = stage === 'ranked' ? nodes.find(n => n.org.name === focus[0]) : null;
    const rm = Scene.ring.material;
    if (best) { Scene.ring.position.copy(best.mesh.position); Scene.ring.scale.setScalar(best.mesh.scale.x * best.size * 1.5);
      Scene.ring.rotation.set(Math.PI / 2.4, time * 0.6, 0); rm.opacity = lerp(rm.opacity, 0.9, 0.08); }
    else rm.opacity = lerp(rm.opacity, 0, 0.15);

    renderer.render(scene, camera);
  }

  function showTip(n) {
    if (!n) { tip.style.opacity = 0; return; }
    const o = n.org, ranked = focus.includes(o.name);
    tip.innerHTML = `<b>${o.name}</b><span>${o.languages.slice(0, 4).join(' · ')}</span><em>${o.domains.join(', ')}</em><small>${o.notes}</small>` +
      (stage === 'ranked' ? (ranked ? '<strong>Click to choose</strong>' : '<strong>Not in your top 3</strong>') : '');
    tip.style.opacity = 1;
  }
})();
