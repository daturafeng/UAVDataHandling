const elements = {
  reloadImagesBtn: document.getElementById("reloadImagesBtn"),
  imageSelect: document.getElementById("imageSelect"),
  demSelect: document.getElementById("demSelect"),
  loadImageBtn: document.getElementById("loadImageBtn"),
  droneImage: document.getElementById("droneImage"),
  imageStage: document.getElementById("imageStage"),
  overlaySvg: document.getElementById("overlaySvg"),
  statusBar: document.getElementById("statusBar"),
  locateBtn: document.getElementById("locateBtn"),
  toolButtons: Array.from(document.querySelectorAll(".tool-btn")),
  finishShapeBtn: document.getElementById("finishShapeBtn"),
  undoBtn: document.getElementById("undoBtn"),
  clearCurrentBtn: document.getElementById("clearCurrentBtn"),
  clearAllBtn: document.getElementById("clearAllBtn"),
};

const state = {
  viewer: null,
  defaultTdtToken: "",
  defaultDemRoot: "",
  defaultDemPath: "",
  selectedDemPath: "",
  selectedImagePath: "",
  metadata: null,
  images: [],
  dems: [],
  annotations: [],
  solvedAnnotations: [],
  currentTool: "point",
  currentVertices: [],
  overlayBounds: null,
  counters: {
    point: 0,
    polyline: 0,
    polygon: 0,
  },
};

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let errorMessage = `HTTP ${response.status}`;
    try {
      const payload = await response.json();
      if (payload?.error) {
        errorMessage = payload.error;
      }
    } catch (error) {
      console.error(error);
    }
    throw new Error(errorMessage);
  }
  return response.json();
}

function setStatus(message = "", kind = "info") {
  if (!message) {
    elements.statusBar.hidden = true;
    elements.statusBar.textContent = "";
    elements.statusBar.dataset.kind = "";
    return;
  }

  elements.statusBar.hidden = false;
  elements.statusBar.dataset.kind = kind;
  elements.statusBar.textContent = message;
}

function setTool(tool) {
  state.currentTool = tool;
  state.currentVertices = [];
  elements.toolButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.tool === tool);
  });
  renderOverlay();
}

function makeAnnotationLabel(kind) {
  state.counters[kind] += 1;
  const prefix = kind === "point" ? "点" : kind === "polyline" ? "线" : "面";
  return `${prefix}${state.counters[kind]}`;
}

function imagePixelToOverlayPoint(vertex) {
  if (!state.metadata || !state.overlayBounds) {
    return { x: 0, y: 0 };
  }
  const width = state.metadata.intrinsics.image_width_px;
  const height = state.metadata.intrinsics.image_height_px;
  return {
    x: (vertex.u / width) * state.overlayBounds.width,
    y: (vertex.v / height) * state.overlayBounds.height,
  };
}

function syncOverlayBounds() {
  const imageRect = elements.droneImage.getBoundingClientRect();
  const stageRect = elements.imageStage.getBoundingClientRect();
  if (!imageRect.width || !imageRect.height) {
    state.overlayBounds = null;
    return;
  }

  state.overlayBounds = {
    left: imageRect.left - stageRect.left,
    top: imageRect.top - stageRect.top,
    width: imageRect.width,
    height: imageRect.height,
  };

  elements.overlaySvg.style.left = `${state.overlayBounds.left}px`;
  elements.overlaySvg.style.top = `${state.overlayBounds.top}px`;
  elements.overlaySvg.style.width = `${state.overlayBounds.width}px`;
  elements.overlaySvg.style.height = `${state.overlayBounds.height}px`;
  elements.overlaySvg.setAttribute("width", `${state.overlayBounds.width}`);
  elements.overlaySvg.setAttribute("height", `${state.overlayBounds.height}`);
}

function createSvgNode(name, attrs) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  return node;
}

function renderAnnotationSvg(vertices, kind, color, dashed = false) {
  const points = vertices.map(imagePixelToOverlayPoint);
  if (kind === "point") {
    const point = points[0];
    return [
      createSvgNode("circle", {
        cx: `${point.x}`,
        cy: `${point.y}`,
        r: "7",
        fill: color,
        stroke: "#ffffff",
        "stroke-width": "2",
      }),
    ];
  }

  const pointList = points.map((point) => `${point.x},${point.y}`).join(" ");
  const strokeAttrs = {
    fill: kind === "polygon" ? `${color}33` : "none",
    stroke: color,
    "stroke-width": "3",
    "stroke-linejoin": "round",
    "stroke-linecap": "round",
  };
  if (dashed) {
    strokeAttrs["stroke-dasharray"] = "8 8";
  }

  const shape =
    kind === "polygon"
      ? createSvgNode("polygon", { points: pointList, ...strokeAttrs })
      : createSvgNode("polyline", { points: pointList, ...strokeAttrs });

  const markers = points.map((point) =>
    createSvgNode("circle", {
      cx: `${point.x}`,
      cy: `${point.y}`,
      r: "4.5",
      fill: "#ffffff",
      stroke: color,
      "stroke-width": "2",
    }),
  );

  return [shape, ...markers];
}

function renderOverlay() {
  elements.overlaySvg.replaceChildren();
  if (!state.metadata || !state.overlayBounds) {
    return;
  }

  state.annotations.forEach((annotation) => {
    const color =
      annotation.kind === "point"
        ? "#f97316"
        : annotation.kind === "polyline"
          ? "#22c55e"
          : "#38bdf8";
    const nodes = renderAnnotationSvg(annotation.vertices, annotation.kind, color);
    nodes.forEach((node) => elements.overlaySvg.appendChild(node));
  });

  if (state.currentVertices.length) {
    const previewKind = state.currentTool === "point" ? "point" : state.currentTool;
    const nodes = renderAnnotationSvg(state.currentVertices, previewKind, "#f8fafc", true);
    nodes.forEach((node) => elements.overlaySvg.appendChild(node));
  }
}

function flattenPositions(coordinates) {
  return coordinates.flatMap((item) => item);
}

function applyMapResults() {
  if (!state.viewer) {
    return;
  }
  state.viewer.entities.removeAll();

  state.solvedAnnotations.forEach((annotation) => {
    const labelText = annotation.label || annotation.annotation_id;
    if (annotation.geojson.type === "Point") {
      const [lon, lat, alt] = annotation.geojson.coordinates;
      state.viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(lon, lat, alt),
        point: {
          pixelSize: 12,
          color: Cesium.Color.ORANGE,
          outlineColor: Cesium.Color.WHITE,
          outlineWidth: 2,
        },
        label: {
          text: labelText,
          font: "16px Microsoft YaHei",
          fillColor: Cesium.Color.WHITE,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          outlineWidth: 3,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          pixelOffset: new Cesium.Cartesian2(0, -14),
        },
      });
      return;
    }

    if (annotation.geojson.type === "LineString") {
      state.viewer.entities.add({
        polyline: {
          positions: Cesium.Cartesian3.fromDegreesArrayHeights(
            flattenPositions(annotation.geojson.coordinates),
          ),
          width: 4,
          material: Cesium.Color.LIME,
        },
      });
      return;
    }

    if (annotation.geojson.type === "Polygon") {
      state.viewer.entities.add({
        polygon: {
          hierarchy: Cesium.Cartesian3.fromDegreesArrayHeights(
            flattenPositions(annotation.geojson.coordinates[0]),
          ),
          material: Cesium.Color.CYAN.withAlpha(0.25),
          outline: true,
          outlineColor: Cesium.Color.CYAN,
        },
      });
    }
  });
}

function locateSolvedAnnotations() {
  if (!state.viewer || !state.solvedAnnotations.length) {
    return;
  }
  state.viewer.flyTo(state.viewer.entities, {
    duration: 1.2,
    offset: new Cesium.HeadingPitchRange(
      0.0,
      Cesium.Math.toRadians(-90.0),
      120.0,
    ),
  });
}

function describeDemSelection(path) {
  if (!path) {
    return "当前使用平地假设求交。";
  }
  return `当前使用 DEM 地形求交：${formatDemOptionLabel(path)}`;
}

async function solveAndRenderAnnotations() {
  if (!state.selectedImagePath || !state.annotations.length) {
    state.solvedAnnotations = [];
    applyMapResults();
    return;
  }

  const payload = {
    image_path: state.selectedImagePath,
    annotations: state.annotations.map((item) => ({
      annotation_id: item.annotation_id,
      kind: item.kind,
      label: item.label,
      vertices: item.vertices,
    })),
    overrides: {},
    terrain_options: state.selectedDemPath
      ? {
          dem_path: state.selectedDemPath,
        }
      : {},
  };
  const result = await fetchJson("/api/solve-annotations", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  state.solvedAnnotations = result.annotations;
  if (result.terrain_options?.dem_path) {
    setStatus(describeDemSelection(result.terrain_options.dem_path), "success");
  } else {
    setStatus("当前使用平地假设求交。", "info");
  }
  applyMapResults();
}

function getClickedPixel(event) {
  if (!state.metadata || !state.overlayBounds) {
    return null;
  }
  const rect = elements.overlaySvg.getBoundingClientRect();
  if (!rect.width || !rect.height) {
    return null;
  }
  return {
    u: ((event.clientX - rect.left) / rect.width) * state.metadata.intrinsics.image_width_px,
    v: ((event.clientY - rect.top) / rect.height) * state.metadata.intrinsics.image_height_px,
  };
}

async function loadImageMetadata(imagePath) {
  const metadata = await fetchJson(`/api/metadata?image_path=${encodeURIComponent(imagePath)}`);
  state.selectedImagePath = imagePath;
  state.metadata = metadata;
  state.annotations = [];
  state.solvedAnnotations = [];
  state.currentVertices = [];

  elements.droneImage.src = metadata.image_url;
  elements.droneImage.style.display = "block";
  applyMapResults();
  setStatus(describeDemSelection(state.selectedDemPath), state.selectedDemPath ? "success" : "info");
}

async function reloadImages() {
  const result = await fetchJson("/api/images");
  state.images = result.images;
  elements.imageSelect.replaceChildren();

  if (!state.images.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "未找到图片";
    elements.imageSelect.appendChild(option);
    return;
  }

  state.images.forEach((imagePath) => {
    const option = document.createElement("option");
    option.value = imagePath;
    option.textContent = imagePath.split("\\").slice(-1)[0];
    elements.imageSelect.appendChild(option);
  });
}

function formatDemOptionLabel(demPath) {
  const parts = demPath.split("\\");
  const district = parts.at(-2) || "未知区域";
  const filename = parts.at(-1) || demPath;
  return `${district} / ${filename}`;
}

function renderDemOptions() {
  elements.demSelect.replaceChildren();

  const noneOption = document.createElement("option");
  noneOption.value = "";
  noneOption.textContent = "不使用 DEM（平地假设）";
  elements.demSelect.appendChild(noneOption);

  state.dems.forEach((demPath) => {
    const option = document.createElement("option");
    option.value = demPath;
    option.textContent = formatDemOptionLabel(demPath);
    elements.demSelect.appendChild(option);
  });

  if (state.selectedDemPath && state.dems.includes(state.selectedDemPath)) {
    elements.demSelect.value = state.selectedDemPath;
  } else if (state.defaultDemPath && state.dems.includes(state.defaultDemPath)) {
    state.selectedDemPath = state.defaultDemPath;
    elements.demSelect.value = state.defaultDemPath;
  } else {
    state.selectedDemPath = "";
    elements.demSelect.value = "";
  }
}

async function reloadDems() {
  const query = state.defaultDemRoot
    ? `?root=${encodeURIComponent(state.defaultDemRoot)}`
    : "";
  const result = await fetchJson(`/api/dems${query}`);
  state.dems = result.dems;
  renderDemOptions();
}

function buildTdtProvider(token) {
  return new Cesium.UrlTemplateImageryProvider({
    url: `https://t{s}.tianditu.gov.cn/DataServer?T=img_w&x={x}&y={y}&l={z}&tk=${token}`,
    subdomains: ["0", "1", "2", "3", "4", "5", "6", "7"],
    tilingScheme: new Cesium.WebMercatorTilingScheme(),
    maximumLevel: 18,
  });
}

function buildFallbackImageryProvider() {
  return new Cesium.UrlTemplateImageryProvider({
    url: "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    maximumLevel: 18,
  });
}

function applyImageryProviders() {
  const imageryLayers = state.viewer.imageryLayers;
  imageryLayers.removeAll();

  try {
    if (state.defaultTdtToken) {
      imageryLayers.addImageryProvider(buildTdtProvider(state.defaultTdtToken));
      return;
    }
  } catch (error) {
    console.error(error);
  }

  imageryLayers.addImageryProvider(buildFallbackImageryProvider());
}

function initViewer() {
  state.viewer = new Cesium.Viewer("cesiumContainer", {
    baseLayer: false,
    animation: false,
    baseLayerPicker: false,
    fullscreenButton: false,
    geocoder: false,
    homeButton: false,
    infoBox: false,
    navigationHelpButton: false,
    sceneModePicker: false,
    selectionIndicator: false,
    timeline: false,
  });
  state.viewer.scene.globe.showGroundAtmosphere = false;
  state.viewer.scene.skyAtmosphere.show = false;
  state.viewer.scene.fog.enabled = false;
  applyImageryProviders();
  state.viewer.camera.setView({
    destination: Cesium.Cartesian3.fromDegrees(106.55, 29.59, 18000),
    orientation: {
      heading: 0.0,
      pitch: Cesium.Math.toRadians(-90.0),
      roll: 0.0,
    },
  });
}

async function finishCurrentShape() {
  if (!state.currentVertices.length) {
    return;
  }
  if (state.currentTool === "polyline" && state.currentVertices.length < 2) {
    return;
  }
  if (state.currentTool === "polygon" && state.currentVertices.length < 3) {
    return;
  }

  state.annotations.push({
    annotation_id: crypto.randomUUID(),
    label: makeAnnotationLabel(state.currentTool),
    kind: state.currentTool,
    vertices: [...state.currentVertices],
  });
  state.currentVertices = [];
  renderOverlay();
  await solveAndRenderAnnotations();
}

function bindEvents() {
  elements.toolButtons.forEach((button) => {
    button.addEventListener("click", () => setTool(button.dataset.tool));
  });

  elements.reloadImagesBtn.addEventListener("click", async () => {
    try {
      await Promise.all([reloadImages(), reloadDems()]);
      setStatus(describeDemSelection(state.selectedDemPath), state.selectedDemPath ? "success" : "info");
    } catch (error) {
      console.error(error);
      setStatus(error.message, "error");
    }
  });

  elements.demSelect.addEventListener("change", async () => {
    state.selectedDemPath = elements.demSelect.value || "";
    const kind = state.selectedDemPath ? "success" : "info";
    setStatus(describeDemSelection(state.selectedDemPath), kind);
    if (state.annotations.length) {
      try {
        await solveAndRenderAnnotations();
      } catch (error) {
        console.error(error);
        setStatus(error.message, "error");
      }
    }
  });

  elements.loadImageBtn.addEventListener("click", async () => {
    const imagePath = elements.imageSelect.value;
    if (!imagePath) {
      return;
    }
    try {
      await loadImageMetadata(imagePath);
    } catch (error) {
      console.error(error);
      setStatus(error.message, "error");
    }
  });

  elements.locateBtn.addEventListener("click", () => {
    locateSolvedAnnotations();
  });

  elements.finishShapeBtn.addEventListener("click", async () => {
    try {
      await finishCurrentShape();
    } catch (error) {
      console.error(error);
      setStatus(error.message, "error");
    }
  });

  elements.undoBtn.addEventListener("click", async () => {
    if (state.currentVertices.length) {
      state.currentVertices.pop();
      renderOverlay();
      return;
    }
    state.annotations.pop();
    try {
      await solveAndRenderAnnotations();
      renderOverlay();
    } catch (error) {
      console.error(error);
      setStatus(error.message, "error");
    }
  });

  elements.clearCurrentBtn.addEventListener("click", () => {
    state.currentVertices = [];
    renderOverlay();
  });

  elements.clearAllBtn.addEventListener("click", () => {
    state.currentVertices = [];
    state.annotations = [];
    state.solvedAnnotations = [];
    renderOverlay();
    applyMapResults();
    setStatus(describeDemSelection(state.selectedDemPath), state.selectedDemPath ? "success" : "info");
  });

  elements.overlaySvg.addEventListener("click", async (event) => {
    const pixel = getClickedPixel(event);
    if (!pixel) {
      return;
    }

    if (state.currentTool === "point") {
      state.annotations.push({
        annotation_id: crypto.randomUUID(),
        label: makeAnnotationLabel("point"),
        kind: "point",
        vertices: [pixel],
      });
      renderOverlay();
      try {
        await solveAndRenderAnnotations();
      } catch (error) {
        console.error(error);
        setStatus(error.message, "error");
      }
      return;
    }

    state.currentVertices.push(pixel);
    renderOverlay();
  });

  elements.overlaySvg.addEventListener("dblclick", async (event) => {
    event.preventDefault();
    if (state.currentTool === "polyline" || state.currentTool === "polygon") {
      try {
        await finishCurrentShape();
      } catch (error) {
        console.error(error);
        setStatus(error.message, "error");
      }
    }
  });

  elements.droneImage.addEventListener("load", () => {
    syncOverlayBounds();
    renderOverlay();
  });

  window.addEventListener("resize", () => {
    syncOverlayBounds();
    renderOverlay();
  });
}

async function bootstrap() {
  initViewer();
  bindEvents();
  setTool("point");

  const config = await fetchJson("/api/config");
  state.defaultTdtToken = config.default_tdt_token || "";
  state.defaultDemRoot = config.default_dem_root || "";
  state.defaultDemPath = config.default_dem_path || "";
  state.selectedDemPath = state.defaultDemPath || "";
  applyImageryProviders();
  await Promise.all([reloadImages(), reloadDems()]);
  setStatus(describeDemSelection(state.selectedDemPath), state.selectedDemPath ? "success" : "info");
}

bootstrap().catch((error) => {
  console.error(error);
  setStatus(error.message, "error");
});
