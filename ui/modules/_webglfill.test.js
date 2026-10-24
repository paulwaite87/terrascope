import { describe, it, expect } from 'vitest';
import { fillMeshVertices } from './_webglfill.js';

// Vertices come back as flat [lon, lat, lon, lat, ...] pairs, three per triangle.
function latitudes(verts) {
    const lats = new Set();
    for (let i = 1; i < verts.length; i += 2) lats.add(verts[i]);
    return [...lats].sort((a, b) => a - b);
}

describe('fillMeshVertices', () => {
    it('reaches both poles, so a polar cap is not left undrawn', () => {
        const lats = latitudes(fillMeshVertices());
        expect(lats[0]).toBeGreaterThan(-90);
        expect(lats[0]).toBeLessThanOrEqual(-89.9);
        expect(lats[lats.length - 1]).toBeGreaterThanOrEqual(89.9);
        expect(lats[lats.length - 1]).toBeLessThan(90);
    });

    it('has no latitude band wider than 2 degrees anywhere, including the polar caps', () => {
        const lats = latitudes(fillMeshVertices());
        for (let i = 1; i < lats.length; i++) {
            expect(lats[i] - lats[i - 1]).toBeLessThanOrEqual(2);
        }
    });

    it('still spans every longitude, with extra world copies either side', () => {
        const verts = fillMeshVertices();
        let min = Infinity, max = -Infinity;
        for (let i = 0; i < verts.length; i += 2) {
            min = Math.min(min, verts[i]);
            max = Math.max(max, verts[i]);
        }
        expect(min).toBe(-180 - 2 * 360);
        expect(max).toBe(180 + 2 * 360);
    });
});
