import { describe, expect, test } from 'vitest';
import {
    CREDIT, ENCODE_DOMAIN, buildSoilMoistureLUT, formatTime, legendGradient, legendLines,
} from './soil_moisture.js';

// RGBA of the LUT texel the shader samples for a percentile.
const lut = buildSoilMoistureLUT();
const texel = (pct) => {
    const i = Math.round(((pct - ENCODE_DOMAIN[0]) / (ENCODE_DOMAIN[1] - ENCODE_DOMAIN[0])) * 255);
    return Array.from(lut.slice(i * 4, i * 4 + 4));
};

describe('the encode domain', () => {
    test('is the fixed 0-100 percentile scale the backend texture is written in', () => {
        expect(ENCODE_DOMAIN).toEqual([0, 100]);
    });
});

describe('buildSoilMoistureLUT', () => {
    test('is a 256-entry RGBA table', () => {
        expect(lut).toBeInstanceOf(Uint8Array);
        expect(lut.length).toBe(256 * 4);
    });

    test('is a deep red-brown at the driest end', () => {
        const [r, g, b, a] = texel(0);
        expect(a).toBe(255);
        expect(r).toBeGreaterThan(g);   // red-brown: red leads...
        expect(g).toBeGreaterThan(b);   // ...then green, blue least
        expect(r).toBeLessThan(160);    // and deep, not bright
    });

    test('is a deep blue at the wettest end', () => {
        const [r, g, b, a] = texel(100);
        expect(a).toBe(255);
        expect(b).toBeGreaterThan(g);
        expect(g).toBeGreaterThan(r);
        expect(b).toBeGreaterThan(120);
    });

    test('is a pale near-neutral at the median', () => {
        const [r, g, b] = texel(50);
        for (const c of [r, g, b]) expect(c).toBeGreaterThan(215);
        expect(Math.max(r, g, b) - Math.min(r, g, b)).toBeLessThan(30);
    });

    test('is fully opaque everywhere: no cutoff, every valid cell is drawn', () => {
        for (let pct = 0; pct <= 100; pct += 5) expect(texel(pct)[3]).toBe(255);
    });

    test('moves from warm to cool steadily: red falls and blue rises across the scale', () => {
        const levels = [0, 25, 50, 75, 100].map(texel);
        // red never rises after the median and blue never falls after the driest end
        const red = levels.map((t) => t[0]);
        const blue = levels.map((t) => t[2]);
        expect(red[0]).toBeGreaterThan(red[4]);
        expect(blue[4]).toBeGreaterThan(blue[0]);
        expect(blue[2]).toBeGreaterThan(blue[0]);   // the neutral is lighter than the dry end
    });
});

describe('formatTime', () => {
    test('shows the granule time as day, month, year and UTC hour', () => {
        expect(formatTime('2026-10-20T21:00:00Z')).toBe('20 Oct 2026 21:00 UTC');
        expect(formatTime('2026-01-02T03:00:00Z')).toBe('2 Jan 2026 03:00 UTC');
    });

    test('passes through a time it cannot read rather than hiding it', () => {
        expect(formatTime('latest')).toBe('latest');
    });
});

describe('legendLines', () => {
    test('names the layer, the scale ends, the granule time and the credit', () => {
        expect(legendLines({ soil_moisture: { time: '2026-10-20T21:00:00Z' } })).toEqual({
            title: 'Soil moisture percentile',
            low: 'Drier',
            high: 'Wetter',
            note: 'than normal for the SMAP record',
            date: 'Soil moisture · 20 Oct 2026 21:00 UTC',
            credit: 'NASA SMAP L4',
        });
        expect(CREDIT).toBe('NASA SMAP L4');
    });

    test('still shows the layer and credit when the time is not available', () => {
        const lines = legendLines({});
        expect(lines.title).toBe('Soil moisture percentile');
        expect(lines.date).toBeNull();
        expect(lines.credit).toBe('NASA SMAP L4');
    });
});

describe('legendGradient', () => {
    test('is a left-to-right CSS gradient from the dry colour through the neutral to the wet colour', () => {
        const css = legendGradient();
        expect(css.startsWith('linear-gradient(to right,')).toBe(true);
        const colours = css.match(/#[0-9a-f]{6}/gi);
        expect(colours.length).toBeGreaterThanOrEqual(3);
        const [first, last] = [colours[0], colours[colours.length - 1]].map((c) => c.toLowerCase());
        const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
        expect(rgb(first)[0]).toBeGreaterThan(rgb(first)[2]);   // dry end: red over blue
        expect(rgb(last)[2]).toBeGreaterThan(rgb(last)[0]);     // wet end: blue over red
    });
});
