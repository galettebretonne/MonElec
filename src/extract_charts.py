"""Extract graph configurations from the D2L website."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

auth_file = Path("data/auth_state.json")

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(viewport={"width": 1280, "height": 2000})

    with open(auth_file) as f:
        state = json.load(f)
    context.add_cookies(state.get("cookies", []))

    page = context.new_page()
    page.goto("https://d2l.sicame.io/Details/22002000211", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(5000)

    # Get page HTML structure around the graph
    graph_section = page.evaluate("""() => {
        const el = document.querySelector('h5');
        if (!el) return null;
        let parent = el.parentElement;
        let html = parent ? parent.innerHTML.substring(0, 5000) : el.outerHTML;
        return html;
    }""")
    print("=== Graph section HTML (first 3000 chars) ===")
    print(graph_section[:3000] if graph_section else "Not found")

    # Find the chart canvas and its parent
    chart_container = page.evaluate("""() => {
        const canvas = document.querySelector('canvas');
        if (!canvas) return { found: false };
        const parent = canvas.parentElement;
        const grandparent = parent ? parent.parentElement : null;
        return {
            found: true,
            canvas: {
                id: canvas.id,
                width: canvas.width,
                height: canvas.height,
                classes: canvas.className
            },
            parent: {
                tag: parent ? parent.tagName : null,
                id: parent ? parent.id : null,
                classes: parent ? parent.className : null
            },
            grandparent: {
                tag: grandparent ? grandparent.tagName : null,
                id: grandparent ? grandparent.id : null,
                classes: grandparent ? grandparent.className : null
            }
        };
    }""")
    print("\n=== Chart container ===")
    print(json.dumps(chart_container, indent=2))

    # Check if it's a custom SVG chart
    svg_charts = page.evaluate("""() => {
        const svgs = document.querySelectorAll('svg');
        return Array.from(svgs).map(s => ({
            id: s.id,
            width: s.getAttribute('width'),
            height: s.getAttribute('height'),
            viewBox: s.getAttribute('viewBox'),
            children: s.children.length,
            classes: s.className
        }));
    }""")
    print(f"\n=== SVG charts: {len(svg_charts)} ===")
    for s in svg_charts:
        print(f"  #{s['id']} {s['width']}x{s['height']} viewBox={s['viewBox']} children={s['children']}")

    # Check Google Charts or other libs
    libs = page.evaluate("""() => {
        const libs = {};
        if (typeof google !== 'undefined' && google.charts) libs['google-charts'] = true;
        if (typeof Highcharts !== 'undefined') libs['highcharts'] = true;
        if (typeof Chart !== 'undefined') libs['chart.js'] = true;
        if (typeof d3 !== 'undefined') libs['d3'] = true;
        if (typeof Plotly !== 'undefined') libs['plotly'] = true;
        if (typeof FusionCharts !== 'undefined') libs['fusioncharts'] = true;
        libs['canvas'] = document.querySelectorAll('canvas').length;
        libs['svg'] = document.querySelectorAll('svg').length;
        return libs;
    }""")
    print(f"\n=== Chart libraries detected: ===")
    print(json.dumps(libs, indent=2))

    # Get the full page HTML below header
    body_html = page.evaluate("""() => {
        return document.body.innerHTML;
    }""")
    print("\n=== Full body HTML (10000 chars around graph) ===")
    # Find the graph area
    import re
    idx = body_html.find('Consommation')
    if idx >= 0:
        start = max(0, idx - 500)
        end = min(len(body_html), idx + 5000)
        print(body_html[start:end])

    # Get SVG content
    svg_content = page.evaluate("""() => {
        const svg = document.querySelector('svg');
        if (!svg) return 'no svg';
        return svg.outerHTML;
    }""")
    print("\n=== SVG chart (first 5000 chars) ===")
    print(svg_content[:5000])

    # Switch to "Jour" view and capture
    print("\n\n=== Switching to 'Jour' view ===")
    page.evaluate("""() => {
        const items = document.querySelectorAll('.dropdown-item');
        for (const item of items) {
            if (item.textContent.trim() === 'Jour') {
                item.click();
                break;
            }
        }
    }""")
    page.wait_for_timeout(3000)
    svg_jour = page.evaluate("""() => {
        const svg = document.querySelector('svg');
        return svg ? svg.outerHTML : 'no svg';
    }""")
    print("Jour SVG (first 3000):", svg_jour[:3000])

    # Switch to "Mois" view
    print("\n=== Switching to 'Mois' view ===")
    page.evaluate("""() => {
        const items = document.querySelectorAll('.dropdown-item');
        for (const item of items) {
            if (item.textContent.trim() === 'Mois') {
                item.click();
                break;
            }
        }
    }""")
    page.wait_for_timeout(3000)
    svg_mois = page.evaluate("""() => {
        const svg = document.querySelector('svg');
        return svg ? svg.outerHTML : 'no svg';
    }""")
    print("Mois SVG (first 3000):", svg_mois[:3000])

    # Switch to "Année" view
    print("\n=== Switching to 'Année' view ===")
    page.evaluate("""() => {
        const items = document.querySelectorAll('.dropdown-item');
        for (const item of items) {
            if (item.textContent.trim() === 'Année') {
                item.click();
                break;
            }
        }
    }""")
    page.wait_for_timeout(3000)
    svg_annee = page.evaluate("""() => {
        const svg = document.querySelector('svg');
        return svg ? svg.outerHTML : 'no svg';
    }""")
    print("Année SVG (first 3000):", svg_annee[:3000])

    # Try clicking the dropdown to see Jour/Mois/Année views
    # First find the current view
    current_view = page.evaluate("""() => {
        const items = document.querySelectorAll('.dropdown-item');
        const active = document.querySelector('.dropdown-item.active, .dropdown-item:focus, .dropdown-item[aria-current]');
        return {
            count: items.length,
            items: Array.from(items).map(i => ({
                text: i.textContent.trim(),
                active: i.classList.contains('active')
            }))
        };
    }""")
    print("\n=== Dropdown state ===")
    print(json.dumps(current_view, indent=2))

    browser.close()
