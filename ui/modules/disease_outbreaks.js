// Disease Outbreaks (WHO Disease Outbreak News) -- a Point-feed layer: a marker on each
// country WHO names in a report that is still current (reported within `active_days`, not
// declared over). The popup carries WHO's own whole summary of the report, the date, a link
// to the full report and the credit. A report naming no single country (Global, Multi-country,
// a WHO region) cannot be placed, so it is listed in a collapsed "Not on the map" section of
// the legend instead, with the same text. Everything is read from our own
// /api/disease_outbreaks route -- the browser never calls WHO.
import { liveDataSync } from './_datasync.js';
import { hoverPopup } from './_hoverpopup.js';
import { replaceSlot, removeLegend } from './_legend.js';
import { fetchOrThrow, escapeHtml, buildPopupHtml } from './_feedhelpers.js';

export const ATTRIBUTION = 'Source: WHO Disease Outbreak News';
export const COUNTRY_NOTE = 'Marked at the country, not at the outbreak site.';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const WHO_PREFIX = 'https://www.who.int/';
const ACCENT = '#c0392b';
const LEGEND_SLOT = 'disease-outbreaks-legend-slot';
// The map popup's content is capped at 320px; title, date, link and the two notes take about
// 140px of it, so the summary scrolls inside the rest rather than pushing the credit out of view.
const SUMMARY_MAX_HEIGHT = 170;

export function formatDate(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

// Only ever link out to WHO itself: the url comes from an external feed.
export function reportLinkHtml(url) {
    if (typeof url !== 'string' || !url.startsWith(WHO_PREFIX)) return '';
    return `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Read the full WHO report</a>`;
}

// The blocks shared by a marker's popup and a legend row's detail: the whole summary
// (scrolling, its paragraph breaks kept), the link and the credit.
function reportBlocks(d, { countryNote }) {
    const rows = [];
    const link = reportLinkHtml(d.url);
    if (link) rows.push({ label: 'Report', value: link, raw: true, width: 50 });
    const blocks = [{ type: 'divider' }, { type: 'scrollText', text: d.summary || '', maxHeight: SUMMARY_MAX_HEIGHT }];
    if (rows.length) blocks.push({ type: 'rows', rows });
    if (countryNote) blocks.push({ type: 'notice', text: COUNTRY_NOTE, color: '#888' });
    blocks.push({ type: 'notice', text: ATTRIBUTION, color: '#888' });
    return blocks;
}

export function popupHtml(feature) {
    const d = feature.properties;
    const when = formatDate(d.published);
    const named = Array.isArray(d.countries) && d.countries.length > 1 ? ` · ${d.countries.join(', ')}` : '';
    return buildPopupHtml({
        title: { text: d.disease || 'Disease outbreak', variant: 'alert' },
        subtitle: escapeHtml(`${d.country || ''}${when ? ` · ${when}` : ''}${named}`),
        blocks: reportBlocks(d, { countryNote: true }),
        fontSize: 12,
    });
}

// The legend's collapsed "Not on the map" section: one <details> row per report, newest
// first as served; opening a row shows the same summary, link and credit as a popup.
export function unplacedLegendHtml(unplaced) {
    if (!Array.isArray(unplaced) || unplaced.length === 0) return '';
    const rows = unplaced.map((d) => {
        const when = formatDate(d.published);
        const detail = buildPopupHtml({
            title: { text: d.disease || 'Disease outbreak', variant: 'alert' },
            subtitle: escapeHtml(when),
            blocks: reportBlocks(d, { countryNote: false }),
            fontSize: 11,
        });
        return `<details style="margin-top:2px;"><summary style="cursor:pointer;">` +
            `${escapeHtml(d.disease || 'Disease outbreak')}${when ? ` · ${escapeHtml(when)}` : ''}</summary>` +
            `<div style="background:#fff;border-radius:3px;margin-top:2px;max-width:300px;">${detail}</div></details>`;
    }).join('');
    return `<details><summary style="cursor:pointer;font-weight:600;color:#eee;">` +
        `Not on the map (${unplaced.length})</summary>` +
        `<div style="font-size:10px;color:#ddd;margin-top:2px;">${rows}</div></details>`;
}

// ---- Marker (drawn, not hotlinked) ---------------------------------------------------

const MARKER_PX = 44;
const MARKER_IMAGE = 'disease-outbreak-marker';

// A crimson disc with a white cross, ringed in white so it reads on any basemap.
function drawMarker() {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = MARKER_PX;
    const ctx = canvas.getContext('2d');
    const c = MARKER_PX / 2;
    ctx.beginPath();
    ctx.arc(c, c, c - 3, 0, 2 * Math.PI);
    ctx.fillStyle = ACCENT;
    ctx.fill();
    ctx.lineWidth = 3;
    ctx.strokeStyle = '#ffffff';
    ctx.stroke();
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(c - 3, c - 11, 6, 22);
    ctx.fillRect(c - 11, c - 3, 22, 6);
    return ctx.getImageData(0, 0, MARKER_PX, MARKER_PX);
}

// ---- Layer ------------------------------------------------------------------------

export function loadLayer(map, config) {
    const sourceId = 'disease-outbreaks-source';
    const layerId = 'disease-outbreaks-layer';
    let stopPopup = null;

    const urlFor = (cfg) => `${window.WM_API}/disease_outbreaks/geojson`
        + `?active_days=${cfg.active_days ?? 45}&t=${Date.now()}`;
    const fetchData = (cfg) => fetchOrThrow(urlFor(cfg));

    const showLegend = (data) => {
        const html = unplacedLegendHtml(data.unplaced);
        if (!html) { removeLegend(LEGEND_SLOT); return; }
        replaceSlot(LEGEND_SLOT, (slot) => { slot.innerHTML = html; });
    };

    const mount = async (cfg) => {
        if (!map.hasImage(MARKER_IMAGE)) map.addImage(MARKER_IMAGE, drawMarker(), { pixelRatio: 2 });
        const data = await fetchData(cfg);
        if (map.getSource(sourceId)) return;          // guard against races
        map.addSource(sourceId, { type: 'geojson', data });
        map.addLayer({
            id: layerId, type: 'symbol', source: sourceId,
            layout: {
                'icon-image': MARKER_IMAGE,
                'icon-size': cfg.icon_zoom ?? 1.0,
                'icon-allow-overlap': true, 'icon-ignore-placement': true,
            },
        });
        // Hover popup, which stays open while the cursor travels into it, so the long
        // summary can be scrolled and the WHO link clicked.
        stopPopup = hoverPopup(map, layerId, { html: popupHtml, maxWidth: '380px', closeDelayMs: 350 });
        showLegend(data);
    };

    const refresh = async (cfg) => {
        const data = await fetchData(cfg);
        map.getSource(sourceId)?.setData(data);
        showLegend(data);
    };

    const unmount = () => {
        stopPopup?.();
        if (map.getLayer(layerId)) map.removeLayer(layerId);
        if (map.getSource(sourceId)) map.removeSource(sourceId);
        removeLegend(LEGEND_SLOT);
    };

    return liveDataSync(map, {
        sectionKey: 'disease_outbreaks', initialConfig: config, mount, refresh, unmount, refreshMs: 900000,
    });
}
