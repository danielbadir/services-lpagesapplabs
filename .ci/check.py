#!/usr/bin/env python3
"""
LPagesAppLabs static-site checks.

Every rule here exists because the corresponding defect was actually found in
production on 2026-07-26, not because it appears on a generic checklist. No
dependencies: this site has no build step and the checks should not add one.

Run:  python3 .ci/check.py
Exit: 0 clean, 1 failures.
"""
import io, os, re, sys, glob, datetime

FAIL = []
WARN = []

def fail(rule, path, msg):  FAIL.append((rule, path, msg))
def warn(rule, path, msg):  WARN.append((rule, path, msg))

HTML = sorted(glob.glob("**/*.html", recursive=True))
CSS  = sorted(glob.glob("**/*.css",  recursive=True))
HTML = [p for p in HTML if ".ci/" not in p]
CSS  = [p for p in CSS  if ".ci/" not in p]

def read(p): return io.open(p, encoding="utf-8").read()

# 1 — CSP integrity. style-src/script-src are 'self' with no unsafe-inline, so an
#     inline style silently does nothing and the page renders bare. A 404 page was
#     written with inline styles during the 2026-07-26 sprint and would have shipped
#     unstyled; this check is why that class of mistake cannot ship again.
for p in HTML:
    s = read(p)
    if re.search(r'\sstyle="', s):
        fail("csp-inline-style", p, "inline style attribute — blocked by style-src 'self'")
    if re.search(r'<style[\s>]', s):
        fail("csp-inline-style", p, "<style> block — blocked by style-src 'self'")
    for m in re.finditer(r'<script(?![^>]*\bsrc=)([^>]*)>', s):
        if 'application/ld+json' not in m.group(1):
            fail("csp-inline-script", p, "inline <script> — blocked by script-src 'self'")
    if re.search(r'\son(click|load|error|mouseover|submit)=', s):
        fail("csp-inline-handler", p, "inline event handler — blocked by script-src 'self'")

# 2 — No third-party origins. The platform's claim is zero third-party requests;
#     fonts.bunny.net was the last one and was removed by self-hosting.
ALLOWED_PROSE = ("policies.google.com", "unity.com", "firebase.google.com", "revenuecat.com",
                 "railway.app", "youronlinechoices.com", "aboutads.info", "optout.aboutads.info",
                 "binance.com", "apple.com", "password-hashing.net", "ec.europa.eu",
                 "schema.org", "w3.org", "sitemaps.org", "lpagesapplabs.com")
for p in HTML:
    for m in re.finditer(r'<(?:link|script|img|iframe)[^>]*(?:href|src)="https?://([^/"]+)', read(p)):
        host = m.group(1)
        if not host.endswith("lpagesapplabs.com"):
            fail("third-party-origin", p, "loads a subresource from %s" % host)
for p in CSS:
    for m in re.finditer(r'url\(\s*[\'"]?https?://([^/\'")]+)', read(p)):
        fail("third-party-origin", p, "CSS loads from %s" % m.group(1))

# 3 — Contrast. opacity on already-tuned text is what put the copyright line on
#     every page at 2.69:1. --muted-dim exists so it never needs to happen again.
for p in CSS:
    for m in re.finditer(r'\{([^{}]*)\}', read(p)):
        body = m.group(1)
        if re.search(r'opacity:\s*0\.[1-8]', body) and re.search(r'color:\s*var\(--(muted|emerald|orange|cyan|violet)\)', body):
            fail("contrast-opacity", p, "text dimmed with opacity — use --muted-dim: %s" % body.strip()[:60])
    if re.search(r'outline:\s*(none|0)', read(p)):
        fail("focus-removed", p, "outline:none removes the focus indicator")

# 4 — Focus must be designed, not inherited.
for p in CSS:
    if os.path.basename(p) in ("fonts.css",):  continue
    if ":focus-visible" not in read(p):
        warn("focus-missing", p, "stylesheet defines no :focus-visible")

# 5 — Every local reference must resolve. This is the check that would have caught
#     the blog linking to posts/*.html that Cloudflare answered with the index page.
for p in HTML:
    base = os.path.dirname(p) or "."
    for m in re.finditer(r'(?:src|href)="([^"#?][^"]*)"', read(p)):
        u = m.group(1)
        if u.startswith(("http://", "https://", "mailto:", "#", "data:", "//")): continue
        tgt = os.path.join(base, u.lstrip("/")) if u.startswith("/") else os.path.join(base, u)
        if os.path.exists(tgt) or os.path.exists(tgt + ".html"):  continue
        fail("dead-link", p, "-> %s" % u)

# 6 — Orphaned assets. 1.39 MB of unreferenced images were shipping, including two
#     655 KB PNGs used as icons.
refs = " ".join(read(p) for p in HTML + CSS)
for asset in glob.glob("**/*.png", recursive=True) + glob.glob("**/*.svg", recursive=True):
    if os.path.basename(asset) not in refs:
        warn("orphan-asset", asset, "%d bytes, no reference" % os.path.getsize(asset))

# 7 — Legal accuracy. The games privacy policy sat five weeks stale saying analytics
#     would be disclosed "if used" while the app already shipped Firebase.
HEDGES = ["if used", "if ads are implemented", "if analytics", "when they launch",
          "will be disclosed", "no release date yet, but"]
for p in [x for x in HTML if os.path.basename(x) in ("privacy.html", "terms.html")]:
    s = read(p)
    low = s.lower()
    for h in HEDGES:
        if h in low:
            fail("legal-hypothetical", p, 'hypothetical language in a legal page: "%s"' % h)
    m = re.search(r'(?:Effective date|Last updated)[:\s]*([0-9]{4}-[0-9]{2}-[0-9]{2})', s)
    if not m:
        fail("legal-undated", p, "no effective date")
    else:
        age = (datetime.date.today() - datetime.date(*map(int, m.group(1).split("-")))).days
        if age > 365:
            fail("legal-stale", p, "effective date is %d days old" % age)
    if "governed by the laws of" in s and "Romania (EU)" not in s:
        fail("legal-jurisdiction", p, "governing law is not the platform-standard Romania (EU)")

# 8 — Internal tooling must never be publicly servable. This used to be enforced
#     by a _redirects rule that deployed correctly but never actually fired —
#     Cloudflare Pages serves an existing static asset before ever consulting
#     _redirects, so the block was a rule that could never be reached, twice.
#     The real fix is structural: servable content lives under public/, and
#     .ci/ + .github/ live as siblings outside it, so Cloudflare's configured
#     Build output directory (public/) never contains them at all. This check
#     verifies that invariant rather than trusting a routing rule to hold.
if not os.path.isdir("public"):
    fail("tooling-exposed", ".", "no public/ directory — served content is not separated from .ci/.github")
else:
    if os.path.exists(os.path.join("public", ".ci")):
        fail("tooling-exposed", "public/.ci", "internal tooling copied into the served directory")
    if os.path.exists(os.path.join("public", ".github")):
        fail("tooling-exposed", "public/.github", "internal tooling copied into the served directory")

# 9 — Document basics.
for p in HTML:
    s = read(p)
    if 'html lang=' not in s:                        fail("a11y-lang", p, "no lang attribute")
    if s.count("<h1") != 1:                          fail("a11y-h1", p, "expected exactly one h1, found %d" % s.count("<h1"))
    if '<title>' not in s:                           fail("seo-title", p, "no <title>")
    if 'name="description"' not in s and '404' not in p:
        warn("seo-description", p, "no meta description")
    for m in re.finditer(r'<img(?![^>]*\balt=)[^>]*>', s):
        fail("a11y-img-alt", p, "img without alt")

def report(items, label):
    if not items: return
    print("\n%s (%d)" % (label, len(items)))
    for rule, path, msg in items:
        print("  [%s] %s: %s" % (rule, path, msg))

report(WARN, "WARNINGS")
report(FAIL, "FAILURES")
print("\n%d failures, %d warnings" % (len(FAIL), len(WARN)))
sys.exit(1 if FAIL else 0)
