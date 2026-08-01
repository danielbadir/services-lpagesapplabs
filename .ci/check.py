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
    # The original guard was `"governed by the laws of" in s`, which never matched
    # root terms.html ("governed by AND CONSTRUED IN ACCORDANCE WITH the laws of ...") —
    # so the one file whose wording actually diverged was the one file the check could
    # not see. Match on "laws of" alone and read the jurisdiction that follows.
    for m in re.finditer(r"laws of\s+([^,<.]+)", s):
        named = m.group(1).strip()
        if not named.startswith("Romania (EU)"):
            fail("legal-jurisdiction", p,
                 'governing law reads "%s", not the platform-standard "Romania (EU)"' % named)

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

# 9 — Render-contract check. Today's outage: main.js was moved into <head>
#     without defer so its .js flag would land before first paint, but the rest
#     of the file still called document.querySelectorAll('.reveal') at parse
#     time — when the body does not exist yet. It matched zero elements, nothing
#     was ever observed, .visible was never added, and every .reveal element
#     stayed at opacity:0 on all nine production sites. Nothing was malformed;
#     every static check passed while the pages were visibly blank.
#     The invariant: a head script without defer/async must not touch the DOM
#     at parse time, and any stylesheet that hides .reveal behind .js must have
#     a script that both sets the flag and reveals on DOM-ready.
for p in HTML:
    s = read(p)
    head = s.split("</head>")[0] if "</head>" in s else s
    for m in re.finditer(r'<script[^>]*\bsrc="([^"]+)"[^>]*>', head):
        tag, src = m.group(0), m.group(1)
        if "defer" in tag or "async" in tag:
            continue
        js_path = os.path.join(os.path.dirname(p) or ".", src)
        if not os.path.exists(js_path):
            continue
        js = read(js_path)
        # strip function bodies is overkill; the reliable signal is whether any
        # DOM query sits outside a boot/DOMContentLoaded guard
        touches_dom = re.search(r'document\.(querySelectorAll|querySelector|getElementById)', js)
        guarded = ("DOMContentLoaded" in js) or ("readyState" in js)
        if touches_dom and not guarded:
            fail("render-contract", js_path,
                 "loaded in <head> without defer but queries the DOM at parse time — "
                 "the body is not parsed yet, so this silently matches nothing")

for c in CSS:
    s = read(c)
    if re.search(r'\.js\s+\.reveal\s*\{[^}]*opacity:\s*0', s):
        site_js = os.path.join(os.path.dirname(c) or ".", "main.js")
        if not os.path.exists(site_js):
            fail("render-contract", c, ".js .reveal is hidden but no main.js exists to reveal it")
        else:
            js = read(site_js)
            if "className" not in js and "classList" not in js:
                fail("render-contract", site_js, "never sets the .js flag that the CSS depends on")
            if "visible" not in js:
                fail("render-contract", site_js, "never adds .visible — hidden content can never appear")

# 10 — Document basics.
for p in HTML:
    s = read(p)
    if 'html lang=' not in s:                        fail("a11y-lang", p, "no lang attribute")
    if s.count("<h1") != 1:                          fail("a11y-h1", p, "expected exactly one h1, found %d" % s.count("<h1"))
    if '<title>' not in s:                           fail("seo-title", p, "no <title>")
    if 'name="description"' not in s and '404' not in p:
        warn("seo-description", p, "no meta description")
    for m in re.finditer(r'<img(?![^>]*\balt=)[^>]*>', s):
        fail("a11y-img-alt", p, "img without alt")

# 11 — HTML structural validity (A3). Nothing on this platform validated HTML at all:
#      the workflow claimed A2/A3 compliance in a comment while running no validator.
#      A full W3C conformance checker needs Java and a network fetch, which would add the
#      first dependency this site has ever had and could fail closed. This is the
#      dependency-free subset that catches structural defects a browser silently absorbs —
#      an unclosed <div> shifts an entire layout with no error anywhere.
#
#      Deliberately NOT checked: a bare "&" followed by whitespace. That is valid HTML5,
#      and the first draft of this rule flagged 45 of them across the platform. Only an
#      *ambiguous* ampersand (&name; that is not a real entity) is a parse error.
from html.parser import HTMLParser
from html.entities import html5 as HTML5_ENTITIES

VOID_ELEMENTS = {"area","base","br","col","embed","hr","img","input","link","meta",
                 "param","source","track","wbr"}
# Elements whose end tag is optional in HTML5. Enforcing balance on these produces
# false positives on valid markup, so they are excluded from the stack.
OPTIONAL_END = {"p","li","dt","dd","option","thead","tbody","tfoot","tr","td","th",
                "rt","rp","optgroup","colgroup","html","head","body"}

class StructureCheck(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=False)
        self.stack, self.ids, self.idrefs, self.errors = [], {}, [], []

    def _err(self, msg): self.errors.append(msg)

    def handle_starttag(self, tag, attrs):
        names = [a[0] for a in attrs]
        for n in set(names):
            if names.count(n) > 1:
                self._err("duplicate attribute '%s' on <%s> (line %d)" % (n, tag, self.getpos()[0]))
        d = dict(attrs)
        if d.get("id"):
            if d["id"] in self.ids:
                self._err("duplicate id '%s' (lines %d and %d)" % (d["id"], self.ids[d["id"]], self.getpos()[0]))
            else:
                self.ids[d["id"]] = self.getpos()[0]
        for a in ("aria-controls", "aria-labelledby", "aria-describedby"):
            if d.get(a):
                for ref in d[a].split():
                    self.idrefs.append((self.getpos()[0], a, ref))
        if tag not in VOID_ELEMENTS and tag not in OPTIONAL_END:
            self.stack.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack and self.stack[-1][0] == tag: self.stack.pop()

    def handle_endtag(self, tag):
        if tag in VOID_ELEMENTS:
            self._err("end tag </%s> for void element (line %d)" % (tag, self.getpos()[0])); return
        if tag in OPTIONAL_END: return
        if not self.stack:
            self._err("stray </%s> (line %d)" % (tag, self.getpos()[0])); return
        if self.stack[-1][0] == tag:
            self.stack.pop(); return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                unclosed = ", ".join("<%s> from line %d" % (t, l) for t, l in self.stack[i+1:])
                self._err("</%s> at line %d closes across unclosed %s" % (tag, self.getpos()[0], unclosed))
                del self.stack[i:]
                return
        self._err("stray </%s> (line %d)" % (tag, self.getpos()[0]))

for p in HTML:
    s = read(p)
    parser = StructureCheck()
    try:
        parser.feed(s); parser.close()
    except Exception as e:
        parser._err("parse error: %s" % e)
    for tag, line in parser.stack:
        parser._err("unclosed <%s> opened at line %d" % (tag, line))
    for line, attr, ref in parser.idrefs:
        if ref not in parser.ids:
            parser._err("%s='%s' at line %d references an id that does not exist" % (attr, ref, line))
    for m in re.finditer(r"&([a-zA-Z][a-zA-Z0-9]*;)", s):
        if m.group(1) not in HTML5_ENTITIES:
            parser._err("ambiguous ampersand '&%s' at line %d" % (m.group(1), s[:m.start()].count("\n") + 1))
    for msg in parser.errors:
        fail("html-structure", p, msg)

# 12 — Class/stylesheet drift. company.html was written with .footer-logo/.footer-logo-img
#      copied from index.html; legal.css defines neither, so the footer would have shipped
#      as an unstyled image. Every other check in this file passed on it.
#
#      WARN, not FAIL, and deliberately so: a class can legitimately carry no rules of its
#      own. The blog TOC marks links .h2/.h3 where only a.h3 needs indenting, so .h2 is
#      correct markup with no styling. Failing on that would make CI permanently red for
#      valid code, which teaches people to ignore CI (see the removed live-header job).
for p in HTML:
    s = read(p)
    sheets = re.findall(r'<link[^>]*rel="stylesheet"[^>]*href="([^"]+)"', s)
    css_text = ""
    for sheet in sheets:
        f = os.path.join(os.path.dirname(p), sheet)
        if os.path.exists(f):
            css_text += read(f)
    if not css_text:
        continue
    defined = set(re.findall(r'\.([A-Za-z][A-Za-z0-9_-]*)', css_text))
    used = set()
    for m in re.finditer(r'class="([^"]+)"', s):
        used.update(m.group(1).split())
    # Applied at runtime by main.js rather than authored in the markup.
    for c in sorted(used - defined - {"visible", "js", "active", "open", "reveal"}):
        warn("css-class-drift", p, ".%s is used but no stylesheet this page loads defines it" % c)

def report(items, label):
    if not items: return
    print("\n%s (%d)" % (label, len(items)))
    for rule, path, msg in items:
        print("  [%s] %s: %s" % (rule, path, msg))

report(WARN, "WARNINGS")
report(FAIL, "FAILURES")
print("\n%d failures, %d warnings" % (len(FAIL), len(WARN)))
sys.exit(1 if FAIL else 0)
