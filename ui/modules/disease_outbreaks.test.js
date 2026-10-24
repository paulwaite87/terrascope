import { describe, expect, test } from 'vitest';
import {
    ATTRIBUTION, COUNTRY_NOTE, formatDate, popupHtml, reportLinkHtml, unplacedLegendHtml,
} from './disease_outbreaks.js';

// Properties as /api/disease_outbreaks/geojson serves them for the recorded MERS report
// (WHO 2026-DON618, 15 Oct 2026), summary shortened.
const SUMMARY = 'On 15 October 2026, WHO was notified of 4 cases of MERS-CoV.\r\n'
    + 'All cases are in Riyadh; 1 died. The risk remains moderate.';
const MERS = {
    don_id: '2026-DON618',
    title: 'Middle East respiratory syndrome coronavirus - Kingdom of Saudi Arabia',
    disease: 'Middle East respiratory syndrome coronavirus',
    country: 'Saudi Arabia',
    countries: ['Saudi Arabia'],
    published: '2026-10-15T09:30:00Z',
    summary: SUMMARY,
    url: 'https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON618',
};

describe('formatDate', () => {
    test('shows the report date as day, month and year in UTC', () => {
        expect(formatDate('2026-10-23T15:48:48Z')).toBe('23 Oct 2026');
        expect(formatDate('2026-01-02T00:00:00Z')).toBe('2 Jan 2026');
    });

    test('an unreadable date shows nothing rather than "Invalid Date"', () => {
        expect(formatDate('latest')).toBe('');
        expect(formatDate(undefined)).toBe('');
    });
});

describe('reportLinkHtml', () => {
    test('links to a WHO page, opened in a new tab without leaking the opener', () => {
        const html = reportLinkHtml(MERS.url);
        expect(html).toContain(`href="${MERS.url}"`);
        expect(html).toContain('target="_blank"');
        expect(html).toContain('rel="noopener noreferrer"');
        expect(html).toContain('Read the full WHO report');
    });

    test('only ever links out to WHO itself: the url comes from an external feed', () => {
        expect(reportLinkHtml('https://evil.example/who.int/')).toBe('');
        expect(reportLinkHtml('javascript:alert(1)')).toBe('');
        expect(reportLinkHtml('http://www.who.int/insecure')).toBe('');
        expect(reportLinkHtml(undefined)).toBe('');
    });
});

describe('popupHtml', () => {
    const html = popupHtml({ properties: MERS });

    test('names the disease and the country, and dates the report', () => {
        expect(html).toContain('Middle East respiratory syndrome coronavirus');
        expect(html).toContain('Saudi Arabia');
        expect(html).toContain('15 Oct 2026');
    });

    test('shows the whole WHO summary with its own paragraph breaks', () => {
        expect(html).toContain(SUMMARY);
        expect(html).toContain('white-space:pre-line');
        expect(html).toContain('overflow-y:auto');   // a long summary scrolls, it does not stretch the popup
    });

    test('links to the full report and credits WHO', () => {
        expect(html).toContain('Read the full WHO report');
        expect(html).toContain(MERS.url);
        expect(html).toContain(ATTRIBUTION);
        expect(ATTRIBUTION).toContain('WHO Disease Outbreak News');
    });

    test('keeps the summary region short enough that the whole popup fits the map popup\'s 320px cap', () => {
        // Title, date, link and the two notes take about 140px; a taller summary region would push
        // the credit below the fold behind a second scrollbar.
        const maxHeight = Number(/max-height:(\d+)px/.exec(html)[1]);
        expect(maxHeight).toBeLessThanOrEqual(170);
        expect(maxHeight).toBeGreaterThanOrEqual(120);
    });

    test('says the marker is at the country, not at the outbreak site', () => {
        expect(html).toContain(COUNTRY_NOTE);
        expect(COUNTRY_NOTE).toMatch(/country/i);
    });

    test('lists the other countries a multi-country report names', () => {
        const ebola = popupHtml({
            properties: { ...MERS, disease: 'Ebola', country: 'Kenya', countries: ['Dem. Rep. Congo', 'Kenya', 'Nigeria'] },
        });
        expect(ebola).toContain('Dem. Rep. Congo, Kenya, Nigeria');
    });

    test('escapes everything that comes from the feed', () => {
        const hostile = popupHtml({
            properties: { ...MERS, disease: '<b>x</b>', summary: '<script>alert(1)</script>', country: '<i>y</i>' },
        });
        expect(hostile).not.toContain('<script>');
        expect(hostile).not.toContain('<b>x</b>');
        expect(hostile).toContain('&lt;script&gt;alert(1)&lt;/script&gt;');
    });
});

describe('unplacedLegendHtml', () => {
    const GLOBAL = {
        don_id: '2026-DON610', title: 'Yellow fever - Global', disease: 'Yellow fever',
        published: '2026-06-24T00:00:00Z', summary: 'Yellow fever remains a global concern.\r\nVaccinate.',
        url: 'https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON610',
    };
    const MULTI = {
        don_id: '2026-DON601', title: 'Hantavirus cluster linked to cruise ship travel, Multi-country',
        disease: 'Hantavirus cluster linked to cruise ship travel',
        published: '2026-05-13T00:00:00Z', summary: 'A cluster across several countries.',
        url: 'https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON601',
    };

    test('is nothing at all when every current report could be placed', () => {
        expect(unplacedLegendHtml([])).toBe('');
        expect(unplacedLegendHtml(undefined)).toBe('');
    });

    test('is a collapsed list headed "Not on the map" with the number of reports', () => {
        const html = unplacedLegendHtml([GLOBAL, MULTI]);
        expect(html).toContain('Not on the map (2)');
        expect(html).toContain('<details');
        expect(html).not.toMatch(/<details[^>]*\sopen/);   // collapsed until opened
    });

    test('lists each report by disease and date, newest first as served', () => {
        const html = unplacedLegendHtml([GLOBAL, MULTI]);
        expect(html).toContain('Yellow fever');
        expect(html).toContain('24 Jun 2026');
        expect(html).toContain('Hantavirus cluster linked to cruise ship travel');
        expect(html.indexOf('Yellow fever')).toBeLessThan(html.indexOf('Hantavirus'));
    });

    test('opening a row shows the same summary, link and credit as a marker\'s popup', () => {
        const html = unplacedLegendHtml([GLOBAL]);
        expect(html).toContain('Yellow fever remains a global concern.\r\nVaccinate.');
        expect(html).toContain(GLOBAL.url);
        expect(html).toContain('Read the full WHO report');
        expect(html).toContain(ATTRIBUTION);
    });

    test('escapes everything that comes from the feed', () => {
        const html = unplacedLegendHtml([{ ...GLOBAL, disease: '<img src=x>', summary: '<script>1</script>' }]);
        expect(html).not.toContain('<img');
        expect(html).not.toContain('<script>');
    });
});
