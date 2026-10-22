import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { GTAOPass } from "three/examples/jsm/postprocessing/GTAOPass.js";
import { OutputPass } from "three/examples/jsm/postprocessing/OutputPass.js";
import type { Scene } from "../lib/api";
import { addLights, buildScene, sceneBounds } from "../lib/scene3d";
import { translate } from "../i18n";

export type CameraMode = "dollhouse" | "top" | "room";

interface Props {
  scene: Scene;
  mode?: CameraMode;
  roomId?: string | null;
  cameraIndex?: number;
  interactive?: boolean;
  height?: number | string;
  /** Before/after: 0..1 split position; left side shows the raw shell. */
  split?: number | null;
  highlight?: string | null;
  cutaway?: boolean;
  onPick?: (objectId: string | null) => void;
  autoRotate?: boolean;
  background?: string;
  /** "high": PBR textures, environment reflections, soft shadows and ambient occlusion. */
  quality?: "fast" | "high";
  /** Fixed camera elevation for dollhouse views (radians from horizontal). */
  elevation?: number;
  wallHeight?: number;
}

export default function Scene3D({ scene, mode = "dollhouse", roomId, cameraIndex = 0, interactive = true, height = 420, split = null, highlight, cutaway = true, onPick, autoRotate = false, background = "#efe9e1", quality = "fast", elevation, wallHeight }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const splitRef = useRef(split);
  splitRef.current = split;

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: quality === "high" });
    } catch {
      el.innerHTML = `<div class="empty">${translate("common.webgl_unavailable")}</div>`;
      return;
    }
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = quality === "high" ? 0.82 : 1.05;
    el.appendChild(renderer.domElement);

    const b = sceneBounds(scene);
    const hq = quality === "high";
    const wallH = wallHeight ?? (cutaway && mode !== "room" ? 1400 : undefined);
    const pmrem = hq ? new THREE.PMREMGenerator(renderer) : null;
    const envTex = pmrem ? pmrem.fromScene(new RoomEnvironment(), 0.04).texture : null;
    const makeWorld = (raw: boolean) => {
      const s3 = new THREE.Scene();
      s3.background = new THREE.Color(background);
      if (envTex) { s3.environment = envTex; s3.environmentIntensity = raw ? 0.22 : 0.3; }
      addLights(s3, b, hq);
      s3.add(buildScene(scene, { raw, furnished: !raw, wallHeight: wallH ?? (raw ? scene.ceiling_height : undefined), highlight, quality }));
      return s3;
    };
    const after = makeWorld(false);
    const before = split !== null ? makeWorld(true) : null;

    const camera = new THREE.PerspectiveCamera(mode === "room" ? 68 : 38, 1, 0.05, 200);
    const target = new THREE.Vector3(b.cx, 0.6, b.cz);
    if (mode === "top") {
      camera.position.set(b.cx, b.size * 1.6, b.cz + 0.01);
    } else if (mode === "room" && roomId) {
      const cams = scene.cameras.filter((c) => c.room_id === roomId);
      const cam = cams[cameraIndex % Math.max(1, cams.length)];
      if (cam) {
        camera.position.set(cam.position[0] * 0.001, 1.45, cam.position[1] * 0.001);
        target.set(cam.target[0] * 0.001, 1.15, cam.target[1] * 0.001);
      }
    } else if (elevation !== undefined) {
      const dist = b.size * 1.7;
      camera.position.set(b.cx + dist * Math.cos(elevation) * 0.48, dist * Math.sin(elevation), b.cz + dist * Math.cos(elevation) * 0.88);
    } else {
      camera.position.set(b.cx + b.size * 0.55, b.size * 0.95, b.cz + b.size * 1.0);
    }
    camera.lookAt(target);

    let controls: OrbitControls | null = null;
    if (interactive) {
      controls = new OrbitControls(camera, renderer.domElement);
      controls.target.copy(target);
      controls.enableDamping = true;
      controls.maxPolarAngle = Math.PI * 0.49;
      controls.autoRotate = autoRotate;
      controls.autoRotateSpeed = 0.6;
      if (mode === "room") { controls.enableZoom = false; controls.rotateSpeed = -0.35; controls.target.copy(target); }
      controls.update();
    }

    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight;
      renderer.setSize(w, h, false);
      renderer.domElement.style.width = "100%";
      renderer.domElement.style.height = "100%";
      camera.aspect = w / Math.max(1, h);
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);

    const ray = new THREE.Raycaster();
    const onClick = (e: MouseEvent) => {
      if (!onPick) return;
      const r = renderer.domElement.getBoundingClientRect();
      ray.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), camera);
      const hit = ray.intersectObjects(after.children, true).find((h) => {
        let o: THREE.Object3D | null = h.object;
        while (o && !o.userData.objectId) o = o.parent;
        return !!o;
      });
      let o: THREE.Object3D | null = hit?.object ?? null;
      while (o && !o.userData.objectId) o = o.parent;
      onPick(o ? (o.userData.objectId as string) : null);
    };
    renderer.domElement.addEventListener("click", onClick);

    // ambient occlusion + tone mapping pass for the realistic dollhouse
    const makeComposer = (world: THREE.Scene) => {
      const c = new EffectComposer(renderer);
      c.addPass(new RenderPass(world, camera));
      const ao = new GTAOPass(world, camera, el.clientWidth, el.clientHeight);
      ao.updateGtaoMaterial({ radius: 0.35, distanceExponent: 1.5, thickness: 1.2, scale: 1.1 });
      ao.blendIntensity = 0.85;
      c.addPass(ao);
      c.addPass(new OutputPass());
      return c;
    };
    const compAfter = hq ? makeComposer(after) : null;
    const compBefore = hq && before ? makeComposer(before) : null;
    const draw = (world: THREE.Scene, comp: EffectComposer | null) => { if (comp) comp.render(); else renderer.render(world, camera); };
    // render on demand: the scene is static (textures are procedural and synchronous), so frames are drawn only
    // after a camera move, resize or split change — an idle viewer costs no GPU time (laptops, phones)
    let dirty = true;
    let lastSplit = splitRef.current;
    const invalidate = () => { dirty = true; };
    controls?.addEventListener("change", invalidate);
    const sizeComposers = () => { const w = el.clientWidth, h = el.clientHeight; compAfter?.setSize(w, h); compBefore?.setSize(w, h); invalidate(); };
    const ro2 = new ResizeObserver(sizeComposers);
    ro2.observe(el);
    let raf = 0;
    const loop = () => {
      raf = requestAnimationFrame(loop);
      controls?.update();  // damping / auto-rotate emit "change" while the camera moves
      if (splitRef.current !== lastSplit) { lastSplit = splitRef.current; dirty = true; }
      if (!dirty) return;
      dirty = false;
      const w = el.clientWidth, h = el.clientHeight;
      if (before && splitRef.current !== null) {
        const sx = Math.round(w * (splitRef.current ?? 0.5));
        renderer.setScissorTest(true);
        renderer.setScissor(0, 0, sx, h); renderer.setViewport(0, 0, w, h); draw(before, compBefore);
        renderer.setScissorTest(true);
        renderer.setScissor(sx, 0, w - sx, h); renderer.setViewport(0, 0, w, h); draw(after, compAfter);
        renderer.setScissorTest(false);
      } else {
        draw(after, compAfter);
      }
    };
    loop();
    return () => {
      cancelAnimationFrame(raf);
      controls?.removeEventListener("change", invalidate);
      ro.disconnect();
      ro2.disconnect();
      compAfter?.dispose(); compBefore?.dispose(); pmrem?.dispose();
      renderer.domElement.removeEventListener("click", onClick);
      controls?.dispose();
      renderer.dispose();
      el.innerHTML = "";
    };
    // re-create the world when the scene or view changes
  }, [scene, mode, roomId, cameraIndex, interactive, highlight, cutaway, split !== null, autoRotate, background, quality, elevation, wallHeight]);  // eslint-disable-line react-hooks/exhaustive-deps

  return <div ref={host} style={{ width: "100%", height, position: "relative", cursor: onPick ? "pointer" : "grab" }} />;
}
