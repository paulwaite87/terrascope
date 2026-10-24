import { createStaticFillLayer } from './_webglfill.js';
import { replaceSlot, removeLegend } from './_legend.js';
import { opacityUniform } from './_opacity.js';

// NASA SMAP L4 root-zone soil moisture percentile (tasks/soil_moisture.py). The texture
// holds the percentile, 0-100 (0 = driest on record for that place, 100 = wettest), over
// a FIXED domain, so a colour always means the same thing. Cells the product has no value
// for are transparent in the texture itself. The colour ramp lives here, so changing it
// never waits on a server render.
export const ENCODE_DOMAIN = [0, 100];
export const CREDIT = 'NASA SMAP L4';

// Diverging ramp, position 0..1 along the domain: deep red-brown (unusually dry), ochre,
// a pale neutral at the median, sky blue, deep blue (unusually wet).
const STOPS = [
    [0.0,  [122, 46, 14]],
    [0.25, [201, 138, 58]],
    [0.5,  [240, 237, 228]],
    [0.75, [111, 178, 220]],
    [1.0,  [11, 79, 158]],
];

// 256x1 RGBA LUT over the encode domain. Fully opaque throughout: there is no cutoff, every
// valid cell is drawn (opacity is applied separately, per viewer).
export function buildSoilMoistureLUT() {
    const lut = new Uint8Array(256 * 4);
    for (let i = 0; i < 256; i++) {
        const t = i / 255;
        let k = 1;
        while (k < STOPS.length - 1 && t > STOPS[k][0]) k++;
        const [t0, c0] = STOPS[k - 1];
        const [t1, c1] = STOPS[k];
        const f = (t - t0) / (t1 - t0);
        const o = i * 4;
        for (let c = 0; c < 3; c++) lut[o + c] = Math.round(c0[c] + f * (c1[c] - c0[c]));
        lut[o + 3] = 255;
    }
    return lut;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// "2026-10-20T21:00:00Z" -> "20 Oct 2026 21:00 UTC". An unreadable value is shown as-is so
// a stale or odd time is never silently hidden.
export function formatTime(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(String(iso));
    if (!m) return String(iso);
    return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]} ${m[4]}:${m[5]} UTC`;
}

export function legendLines(meta) {
    const time = meta?.soil_moisture?.time;
    return {
        title: 'Soil moisture percentile',
        low: 'Drier',
        high: 'Wetter',
        note: 'than normal for the SMAP record',
        date: time ? `Soil moisture · ${formatTime(time)}` : null,
        credit: CREDIT,
    };
}

// The key bar: the ramp's own stops, fully opaque.
export function legendGradient() {
    const hex = (c) => `#${c.map((v) => v.toString(16).padStart(2, '0')).join('')}`;
    const stops = STOPS.map(([t, c]) => `${hex(c)} ${Math.round(t * 100)}%`);
    return `linear-gradient(to right, ${stops.join(', ')})`;
}

const LEGEND_SLOT = 'soil-moisture-legend-slot';

function metaUrl(cfg) {
    const dir = String(cfg.outfile || 'data/soil_moisture.png').replace(/[^/]*$/, '');
    return `${window.MAP_UI}/${dir}soil_moisture_meta.json?t=${Date.now()}`;
}

async function addLegend(cfg) {
    if (opacityUniform(cfg, 0.7) <= 0) { removeLegend(LEGEND_SLOT); return; }
    const meta = await fetch(metaUrl(cfg)).then((r) => (r.ok ? r.json() : {})).catch(() => ({}));
    const lines = legendLines(meta);
    replaceSlot(LEGEND_SLOT, (slot) => {
        const line = (text, css) => {
            const el = document.createElement('div');
            el.textContent = text;
            el.style.cssText = css;
            slot.appendChild(el);
        };
        line(lines.title, 'font-size:11px;font-weight:600;color:#eee;margin-bottom:3px;');
        const bar = document.createElement('div');
        bar.style.cssText = `width:160px;height:10px;border-radius:2px;border:1px solid #555;background:${legendGradient()};`;
        slot.appendChild(bar);
        const scale = document.createElement('div');
        scale.style.cssText = 'display:flex;justify-content:space-between;width:160px;font-size:9px;color:#ddd;';
        for (const t of [lines.low, lines.high]) {
            const s = document.createElement('span');
            s.textContent = t;
            scale.appendChild(s);
        }
        slot.appendChild(scale);
        line(lines.note, 'font-size:9px;color:#aaa;');
        if (lines.date) line(lines.date, 'font-size:9px;color:#aaa;margin-top:3px;');
        line(lines.credit, 'font-size:9px;color:#aaa;');
    });
}

export function loadLayer(map, config) {
    const lut = buildSoilMoistureLUT();

    return createStaticFillLayer(map, {
        sectionKey: 'soil_moisture',
        initialConfig: config,
        dataUrl: (cfg) => `${window.MAP_UI}/${cfg.outfile}`,
        physicalDomain: () => ENCODE_DOMAIN,
        fragmentBody: `
            uniform float u_alpha;
            vec4 shade(float value, vec2 uv) {
                float t = clamp((value - u_vmin) / u_span, 0.0, 1.0);
                vec4 c = texture(u_cmap, vec2(t, 0.5));
                return vec4(c.rgb, c.a * u_alpha);
            }`,
        customUniforms: (cfg) => ({ u_alpha: opacityUniform(cfg, 0.7) }),
        colormap: () => lut,
        refreshMs: 3600000,                // a new granule every few hours at most
        onMount: (cfg) => addLegend(cfg),
        onRefresh: (cfg) => addLegend(cfg),
        onUnmount: () => removeLegend(LEGEND_SLOT),
    });
}
