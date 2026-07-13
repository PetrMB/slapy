/* ============ Odhad hloubky pod lodí ============
   Čte hloubkovou mřížku data/depth.png (generuje CI bake, 1 px ≈ 30 m,
   hodnota pixelu = metry). ORIENTAČNÍ MODELOVÝ ODHAD — nenahrazuje měření. */
const Depth = (() => {
  let grid = null;    // {data: Uint8ClampedArray (jen R kanál po krocích 4), w, h, bbox}
  let loading = null;

  function load() {
    if (grid || typeof DEPTH_GRID === "undefined" || !DEPTH_GRID) return loading || Promise.resolve();
    if (loading) return loading;
    loading = new Promise(resolve => {
      const img = new Image();
      img.onload = () => {
        const c = document.createElement("canvas");
        c.width = img.width; c.height = img.height;
        const ctx = c.getContext("2d", { willReadFrequently: true });
        ctx.drawImage(img, 0, 0);
        grid = {
          data: ctx.getImageData(0, 0, img.width, img.height).data,
          w: img.width, h: img.height,
          bbox: DEPTH_GRID.bbox,
        };
        resolve();
      };
      img.onerror = () => resolve();
      img.src = DEPTH_GRID.url;
    });
    return loading;
  }

  /* odhad hloubky [m] na souřadnici, null = mimo vodu / bez dat */
  function at(lat, lon) {
    if (!grid) { load(); return null; }
    const [lon0, lat0, lon1, lat1] = grid.bbox;
    if (lon < lon0 || lon > lon1 || lat < lat0 || lat > lat1) return null;
    // mřížka je ve Web Mercatoru — převod přes latitudu
    const mercY = l => Math.log(Math.tan(Math.PI / 4 + (l * Math.PI / 180) / 2));
    const x = Math.round((lon - lon0) / (lon1 - lon0) * (grid.w - 1));
    const y = Math.round((mercY(lat1) - mercY(lat)) / (mercY(lat1) - mercY(lat0)) * (grid.h - 1));
    if (x < 0 || y < 0 || x >= grid.w || y >= grid.h) return null;
    const d = grid.data[(y * grid.w + x) * 4];
    return d > 0 ? d : null;
  }

  return {
    at,
    load,
    available: () => typeof DEPTH_GRID !== "undefined" && !!DEPTH_GRID,
  };
})();
