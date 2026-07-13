/* ============ Říční kilometráž: projekce polohy na osu Vltavy ============
   Podporuje dvě osy: RIVER_AXIS (nádrž Slapy, km 91,61–134,73, js/data/river.js)
   a DOWNSTREAM_AXIS (hráz Slapy → Mělník, km 91,61–0, js/data/downstream.js).
   Každá osa má kalibraci [{i: index bodu, km: říční km}] dle oficiální
   kilometráže Vltavy. Km rozsahy os se nepřekrývají. */
const RiverKM = (() => {
  let axes = null; // [{pts, cal, cum, kmMin, kmMax}]

  function buildAxis(pts, cal) {
    const cum = [0];
    for (let i = 1; i < pts.length; i++) {
      cum[i] = cum[i - 1] + GPS.haversine(pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1]);
    }
    const kms = cal.map(c => c.km);
    return { pts, cal, cum, kmMin: Math.min(...kms), kmMax: Math.max(...kms) };
  }

  function build() {
    axes = [buildAxis(RIVER_AXIS, RIVER_KM_CAL)];
    if (typeof DOWNSTREAM_AXIS !== "undefined") {
      axes.push(buildAxis(DOWNSTREAM_AXIS, DOWNSTREAM_KM_CAL));
    }
  }
  function ensure() { if (!axes) build(); }

  /* interpolace km <-> vzdálenost podél osy */
  function distToKm(ax, d) {
    const cal = ax.cal;
    let j = 1;
    while (j < cal.length - 1 && d > ax.cum[cal[j].i]) j++;
    const a = cal[j - 1], b = cal[j];
    const da = ax.cum[a.i], db = ax.cum[b.i];
    if (db === da) return a.km;
    return a.km + (b.km - a.km) * (d - da) / (db - da);
  }
  function kmToDist(ax, km) {
    const cal = ax.cal;
    const asc = cal[cal.length - 1].km > cal[0].km;
    let j = 1;
    while (j < cal.length - 1 && (asc ? km > cal[j].km : km < cal[j].km)) j++;
    const a = cal[j - 1], b = cal[j];
    if (b.km === a.km) return ax.cum[a.i];
    return ax.cum[a.i] + (ax.cum[b.i] - ax.cum[a.i]) * (km - a.km) / (b.km - a.km);
  }
  function pointAtDist(ax, d) {
    const cum = ax.cum, pts = ax.pts;
    let i = 1;
    while (i < cum.length - 1 && cum[i] < d) i++;
    const t = (d - cum[i - 1]) / (cum[i] - cum[i - 1] || 1);
    const [alat, alon] = pts[i - 1];
    const [blat, blon] = pts[i];
    return [alat + (blat - alat) * t, alon + (blon - alon) * t];
  }

  function projectAxis(ax, lat, lon) {
    let best = { dist: Infinity, along: 0 };
    const pts = ax.pts;
    for (let i = 1; i < pts.length; i++) {
      const [alat, alon] = pts[i - 1];
      const [blat, blon] = pts[i];
      const kx = Math.cos(alat * Math.PI / 180) * 111320;
      const ky = 110574;
      const bx = (blon - alon) * kx, by = (blat - alat) * ky;
      const px = (lon - alon) * kx, py = (lat - alat) * ky;
      const len2 = bx * bx + by * by;
      let t = len2 ? (px * bx + py * by) / len2 : 0;
      t = Math.max(0, Math.min(1, t));
      const dx = px - t * bx, dy = py - t * by;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < best.dist) {
        best = { dist, along: ax.cum[i - 1] + t * (ax.cum[i] - ax.cum[i - 1]) };
      }
    }
    return best;
  }

  /* nejbližší bod na kterékoli ose: {km, offAxis} */
  function project(lat, lon) {
    ensure();
    let out = null;
    for (const ax of axes) {
      const b = projectAxis(ax, lat, lon);
      if (!out || b.dist < out.offAxis) out = { km: distToKm(ax, b.along), offAxis: b.dist };
    }
    return out;
  }

  function axisForKm(km) {
    ensure();
    return axes.find(a => km >= a.kmMin - 0.01 && km <= a.kmMax + 0.01) || axes[0];
  }

  /* souřadnice bodu na ose pro daný říční km */
  function kmToPoint(km) {
    const ax = axisForKm(km);
    return pointAtDist(ax, kmToDist(ax, km));
  }

  /* lomená čára podél osy mezi dvěma km (pro úseky ponorů) */
  function slice(km1, km2) {
    const ax = axisForKm((km1 + km2) / 2);
    let d1 = kmToDist(ax, km1), d2 = kmToDist(ax, km2);
    if (d1 > d2) [d1, d2] = [d2, d1];
    const out = [pointAtDist(ax, d1)];
    for (let i = 0; i < ax.pts.length; i++) {
      if (ax.cum[i] > d1 && ax.cum[i] < d2) out.push(ax.pts[i]);
    }
    out.push(pointAtDist(ax, d2));
    return out;
  }

  /* rozsahy km všech os (pro km značky na mapě) */
  function ranges() {
    ensure();
    return axes.map(a => ({ min: a.kmMin, max: a.kmMax }));
  }

  return { project, kmToPoint, slice, ranges };
})();
