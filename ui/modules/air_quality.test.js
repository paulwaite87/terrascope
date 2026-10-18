import { describe, it, expect } from 'vitest';
import { keySpecFor } from './air_quality.js';

describe('keySpecFor: dust', () => {
    it('titles the legend "Dust (AOD)" with no unit, since optical depth is dimensionless', () => {
        expect(keySpecFor({ variable: 'dust' }).title).toBe('Dust (AOD)');
    });

    it('runs from the 0.1 default minimum to the fixed 1.5 ceiling in five even ticks', () => {
        const spec = keySpecFor({ variable: 'dust' });

        expect(spec.vmin).toBe(0.1);
        expect(spec.vmax).toBe(1.5);
        expect(spec.ticks).toHaveLength(5);
        [0.1, 0.45, 0.8, 1.15, 1.5].forEach((v, i) => expect(spec.ticks[i]).toBeCloseTo(v, 10));
        expect(spec.tickFormat).toBe('%.2f');
    });

    it('reads its minimum from dust_min, not from the smoke AOD minimum', () => {
        const spec = keySpecFor({ variable: 'dust', dust_min: 0.3, aod_min: 2 });

        expect(spec.vmin).toBe(0.3);
    });

    it('colours the thin end pale sand and the dense end dark brown', () => {
        const { lut } = keySpecFor({ variable: 'dust' });

        expect([...lut.slice(0, 3)]).toEqual([246, 231, 180]);          // #f6e7b4
        expect([...lut.slice(255 * 4, 255 * 4 + 3)]).toEqual([78, 42, 18]); // #4e2a12
    });

    it('does not share a lookup table with the health-index variables', () => {
        expect(keySpecFor({ variable: 'dust' }).lut).not.toBe(keySpecFor({ variable: 'aod' }).lut);
    });
});

describe('keySpecFor: the existing variables are unchanged', () => {
    it('keeps smoke AOD on its 0.5 default minimum and 3 ceiling', () => {
        const spec = keySpecFor({ variable: 'aod' });

        expect(spec.title).toBe('Smoke (AOD)');
        expect(spec.vmin).toBe(0.5);
        expect(spec.vmax).toBe(3);
    });
});
