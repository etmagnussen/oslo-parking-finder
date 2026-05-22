"""UI helpers — currently a static Leaflet map generator.

The ``build_map`` module reads a normalized CSV and produces a single
self-contained HTML file. Leaflet is loaded from a CDN; everything else
(data, code) is inlined. No server required.
"""
