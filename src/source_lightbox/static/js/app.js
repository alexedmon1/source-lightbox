/* source-lightbox SPA — vanilla JS, fully offline (no fetch needed) */
(function () {
  "use strict";

  const M = window.MANIFEST;
  const PAGE_SIZE = 50;

  /* ── Acronym map for display formatting ── */
  const ACRONYMS = {
    "psd": "PSD", "pac": "PAC", "mvpa": "MVPA", "roi": "ROI", "vertex": "Vertex", "lmm": "LMM",
    "itc": "ITC", "ersp": "ERSP", "stp": "STP", "svm": "SVM", "nbs": "NBS",
    "assr": "ASSR", "qc": "QC", "eeg": "EEG", "ica": "ICA", "falff": "fALFF",
    "fdr": "FDR", "aic": "AIC", "bic": "BIC", "se": "SE", "df": "df",
    // Connectivity / coupling / directed metrics and method acronyms — keep the
    // canonical mixed case (wPLI, dwPLI, dPLI) consistent everywhere they render.
    "aec": "AEC", "pli": "PLI", "wpli": "wPLI", "dwpli": "dwPLI", "dpli": "dPLI",
    "aac": "AAC", "ppc": "PPC", "dtf": "DTF", "te": "TE", "cfc": "CFC",
    "fcd": "FCD", "auc": "AUC", "tfce": "TFCE", "fooof": "FOOOF", "mi": "MI",
  };

  /* ── Group label map for readable contrast display ── */
  const GROUP_LABELS = {
    "vehicle": "Vehicle",
    "6mgkg": "AUT00201 (6 mg/kg)",
    "30mgkg": "AUT00206 (30 mg/kg)",
  };

  /* ── State ── */
  let currentSource = null;
  let lightbox = null;

  /* ── Init ── */
  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("gallery-title").textContent = M.title || "Gallery";
    document.title = M.title || "Source Analysis Gallery";
    buildSidebar();
    initThemeToggle();
    initSearch();
    initKeyboard();
    window.addEventListener("hashchange", route);
    route();
  });

  /* ── Router ── */
  function route() {
    var hash = location.hash.slice(1) || "/overview";
    var parts = hash.split("/").filter(Boolean);
    highlightNav(hash);

    if (parts[0] === "overview" || parts.length === 0) {
      renderOverview();
    } else if (parts[0] === "search") {
      renderSearch(decodeURIComponent(parts.slice(1).join("/")));
    } else if (parts[0] === "localization") {
      if (parts[1] === "qc") renderQC(parts[2]);
      else if (parts[1] === "subjects") renderSubjects(parts[2]);
      else renderLocalizationHome();
    } else if (parts[0] === "domain") {
      // #/domain/<source>/<paradigm>/<domain>
      renderDomain(decodeURIComponent(parts[1] || ""),
        decodeURIComponent(parts[2] || ""), decodeURIComponent(parts[3] || ""));
    } else if (parts[0] === "analytics") {
      // #/analytics/<source>/<paradigm>/<analysis>  (single-analysis deep link)
      var src = decodeURIComponent(parts[1] || "");
      if (parts.length >= 4) {
        renderAnalysis(parts[2], parts[3], src);
      } else if (parts.length === 3) {
        renderStudyDesign(parts[2], src);
      } else {
        renderSourceHome(src);
      }
    } else {
      renderOverview();
    }
  }

  /* Sources that actually carry analytics data. Localization pipelines
     (paths.localizations, e.g. ROI/Shell) are a separate namespace from the
     analytics source(s) (paths.results) and have zero figures/tables here, so
     they're excluded — derived from the data, no hardcoded source names. */
  function analyticsSources() {
    return M.sources.filter(function (src) {
      for (var para of Object.keys(M.paradigms)) {
        var analyses = M.paradigms[para];
        for (var aname of Object.keys(analyses)) {
          var ad = analyses[aname];
          if ((ad.figures[src] && ad.figures[src].length) ||
              (ad.tables[src] && ad.tables[src].length)) {
            return true;
          }
        }
      }
      return false;
    });
  }

  /* Analytics breadcrumb — include the source only when more than one exists,
     so a single results source (e.g. "results_treatment") isn't redundant noise. */
  function analyticsCrumbs(src, tail) {
    var base = analyticsSources().length > 1 ? ["Analytics", src] : ["Analytics"];
    return base.concat(tail || []);
  }

  /* ── Domain grouping ──────────────────────────────────────────────────────
     Each analysis carries meta.domain (where it is listed) and meta.supplements
     (the primary it runs *after*, consuming its output). The gallery shows one
     page per (paradigm × domain); a secondary nests right after its primary as a
     sub-tab. Domain order is fixed; unknown domains fall to the end. */
  var DOMAIN_ORDER = ["Spectral", "Connectivity", "Cross-frequency", "Sensor-level", "Source vs Sensor", "Evoked", "Other"];
  // "Sensor-level" is a distinct acquisition level (scalp electrodes, not source-
  // localized ROI/vertex data), so in the nav it is promoted out of its paradigm's
  // domain list into its own study-design heading rather than listed under ROI/vertex.
  var SENSOR_DOMAIN = "Sensor-level";
  // "Source vs Sensor" holds the source-vs-sensor comparison layers (PSD,
  // Connectivity); it renders as a sub-group at the end of the Sensor-level section.
  var COMPARISON_DOMAIN = "Source vs Sensor";

  function analysisHasData(ad, src) {
    return (ad.figures[src] && ad.figures[src].length > 0) ||
           (ad.tables[src] && ad.tables[src].length > 0) || !!ad.summary;
  }
  function analysisDomain(ad) {
    return (ad && ad.meta && ad.meta.domain) || "Other";
  }

  // Ordered domain names with ≥1 analysis that has data for src, within paradigm.
  function domainsForParadigm(paradigm, src) {
    var analyses = M.paradigms[paradigm] || {};
    var present = {};
    for (var a of Object.keys(analyses)) {
      if (analysisHasData(analyses[a], src)) present[analysisDomain(analyses[a])] = true;
    }
    return DOMAIN_ORDER.filter(function (d) { return present[d]; })
      .concat(Object.keys(present).filter(function (d) { return DOMAIN_ORDER.indexOf(d) < 0; }));
  }

  // Analyses in a (paradigm, domain) that have data for src — primaries first,
  // each secondary placed immediately after the primary it supplements.
  // Canonical intra-domain analysis order: PSD (the standard analysis) leads,
  // then the other primary measures. Names are matched by keyword; unknown
  // analyses keep their existing (manifest) order after the ranked ones.
  var ANALYSIS_ORDER = ["psd", "cluster", "aperiodic", "specparam", "spatial",
                        "connectivity", "cross_freq", "directed", "graph", "nbs",
                        "comparison", "mvpa", "evoked"];
  function analysisRank(name) {
    var n = String(name).toLowerCase();
    for (var i = 0; i < ANALYSIS_ORDER.length; i++) {
      if (n.indexOf(ANALYSIS_ORDER[i]) >= 0) return i;
    }
    return ANALYSIS_ORDER.length;
  }

  function domainAnalyses(paradigm, domain, src) {
    var analyses = M.paradigms[paradigm] || {};
    var names = Object.keys(analyses).filter(function (a) {
      return analysisHasData(analyses[a], src) && analysisDomain(analyses[a]) === domain;
    });
    var suppOf = function (a) { return analyses[a].meta && analyses[a].meta.supplements; };
    var prim = names.filter(function (a) { return !suppOf(a); })
      .sort(function (a, b) { return analysisRank(a) - analysisRank(b); });
    var supp = names.filter(function (a) { return suppOf(a); });
    var out = [];
    prim.forEach(function (p) {
      out.push({ name: p, supp: false });
      supp.filter(function (s) { return suppOf(s) === p; })
        .forEach(function (s) { out.push({ name: s, supp: true }); });
    });
    // Orphan secondaries (primary missing / no data) go last.
    supp.filter(function (s) { return prim.indexOf(suppOf(s)) < 0; })
      .forEach(function (s) { out.push({ name: s, supp: true }); });
    return out;
  }

  function domainRoute(src, paradigm, domain) {
    return "/domain/" + encodeURIComponent(src) + "/" + encodeURIComponent(paradigm) +
      "/" + encodeURIComponent(domain);
  }

  /* ── Paradigm display metadata (optional, from M.paradigm_meta) ──
     Lets a study nest its paradigms under a shared group header and relabel them
     (e.g. resting/vertex → group "Resting" with "ROI-based"/"Vertex-based"). When
     a paradigm has no entry, the nav stays flat and labels fall back to formatName. */
  function paradigmMeta(p) { return (M.paradigm_meta && M.paradigm_meta[p]) || null; }
  function paradigmGroup(p) { var m = paradigmMeta(p); return (m && m.group) || null; }
  function paradigmLabel(p) { var m = paradigmMeta(p); return (m && m.label) || formatName(p); }

  // Display name for an analysis (module meta.display_name overrides the
  // formatted module name), e.g. electrode_comparison → "PSD".
  function analysisLabel(paradigm, name) {
    var a = M.paradigms[paradigm] && M.paradigms[paradigm][name];
    return (a && a.meta && a.meta.display_name) || formatName(name);
  }

  // The study-design label for an analysis header/breadcrumb. Sensor-level and
  // Source-vs-Sensor analyses aren't ROI/vertex source-space, so they read their
  // own design label, not the paradigm label ("ROI-based") they sit in.
  function designLabel(paradigm, analysisName) {
    var ad = M.paradigms[paradigm] && M.paradigms[paradigm][analysisName];
    var d = ad && analysisDomain(ad);
    if (d === COMPARISON_DOMAIN) return COMPARISON_DOMAIN;
    if (d === SENSOR_DOMAIN) return SENSOR_DOMAIN;
    return paradigmLabel(paradigm);
  }

  /* ── Sidebar ── */
  function buildSidebar() {
    var nav = document.getElementById("sidebar-nav");
    var html = "";

    // Overview
    html += '<a class="nav-item" href="#/overview" data-route="/overview">Overview</a>';

    // Localization — section title (matching Analytics), nested per source
    var locSources = Object.keys(M.localization);
    if (locSources.length > 0) {
      html += '<div class="nav-divider"></div>';
      html += '<div class="nav-section-title">Localization</div>';
      for (var source of locSources) {
        if (locSources.length > 1) {
          html += '<div class="nav-paradigm">' + escapeHtml(source) + '</div>';
        }
        html += navItem("/localization/subjects/" + source, "Subjects");
        html += navItem("/localization/qc/" + source, "QC");
      }
    }

    // Analytics — grouped by source, then study design (paradigm), then analysis.
    // Only sources with analytics data appear (localization-only sources skip).
    var aSources = analyticsSources();
    if (aSources.length > 0) {
      html += '<div class="nav-divider"></div>';
      html += '<div class="nav-section-title">Analytics</div>';

      for (var si = 0; si < aSources.length; si++) {
        var src = aSources[si];
        // Only show source header when there's more than one analytics source
        if (aSources.length > 1) {
          html += '<div class="nav-paradigm">' + escapeHtml(src) + '</div>';
        }
        // Group paradigms that have data for this source. A paradigm may declare
        // a display group (M.paradigm_meta) so siblings nest under one header
        // (e.g. "Resting" › "ROI-based"/"Vertex-based"); otherwise the nav is flat.
        var lastGroup = null;
        // Sensor-level sections are deferred to the END of their group so they sit
        // after the source-localized study designs (ROI → Vertex → Sensor-level).
        // A group's sensor analyses from EVERY paradigm are merged under ONE
        // Sensor-level heading (so scalp + source-vs-sensor comparisons sit together).
        var pendingSensor = "";      // Sensor-level nav items (no heading)
        var pendingComparison = "";  // Source-vs-Sensor items (own sub-heading)
        function flushSensor() {
          if (pendingSensor || pendingComparison) {
            html += '<div class="nav-study-design">' + escapeHtml(SENSOR_DOMAIN) + '</div>' + pendingSensor;
            if (pendingComparison) {
              html += '<div class="nav-subgroup">' + escapeHtml(COMPARISON_DOMAIN) + '</div>' +
                '<div class="nav-subgroup-items">' + pendingComparison + '</div>';
            }
            pendingSensor = ""; pendingComparison = "";
          }
        }
        for (var paradigm of Object.keys(M.paradigms)) {
          var analyses = M.paradigms[paradigm];
          var hasData = false;
          for (var aname of Object.keys(analyses)) {
            var adata = analyses[aname];
            if ((adata.figures[src] && adata.figures[src].length > 0) ||
                (adata.tables[src] && adata.tables[src].length > 0)) {
              hasData = true;
              break;
            }
          }
          if (!hasData) continue;

          var grp = paradigmGroup(paradigm);
          if (grp !== lastGroup) {
            flushSensor();  // close out the previous group's sensor section first
            if (grp) html += '<div class="nav-paradigm-group">' + escapeHtml(grp) + '</div>';
          }
          lastGroup = grp;  // null for ungrouped → next grouped paradigm re-emits

          html += '<div class="nav-study-design">' + paradigmLabel(paradigm) + '</div>';
          // Group analyses by domain (one nav item per domain → domain page).
          // Sensor-level is promoted to its own study-design heading (deferred to the
          // group end), so it is not listed as a domain under this paradigm's label.
          var analyticBase = "/analytics/" + encodeURIComponent(src) + "/" + encodeURIComponent(paradigm) + "/";
          var pdomains = domainsForParadigm(paradigm, src);
          pdomains.forEach(function (domain) {
            if (domain === SENSOR_DOMAIN || domain === COMPARISON_DOMAIN) return;
            html += navItem(domainRoute(src, paradigm, domain), domain);
          });
          // Sensor-level + Source-vs-Sensor analyses are deferred and merged across
          // paradigms; the headings are emitted by flushSensor at the group's end.
          if (pdomains.indexOf(SENSOR_DOMAIN) >= 0) {
            domainAnalyses(paradigm, SENSOR_DOMAIN, src).forEach(function (o) {
              pendingSensor += navItem(analyticBase + encodeURIComponent(o.name), analysisLabel(paradigm, o.name));
            });
          }
          if (pdomains.indexOf(COMPARISON_DOMAIN) >= 0) {
            domainAnalyses(paradigm, COMPARISON_DOMAIN, src).forEach(function (o) {
              pendingComparison += navItem(analyticBase + encodeURIComponent(o.name), analysisLabel(paradigm, o.name));
            });
          }
        }
        flushSensor();  // emit the final group's sensor section
      }
    }

    nav.innerHTML = html;
  }

  function navItem(route, label) {
    return '<a class="nav-item" href="#' + route + '" data-route="' + route + '">' + label + '</a>';
  }

  function highlightNav(hash) {
    document.querySelectorAll(".nav-item").forEach(function (el) {
      el.classList.toggle("active", el.getAttribute("data-route") === hash.replace("#", ""));
    });
  }

  /* ── Overview ── */
  function renderOverview() {
    setBreadcrumb(["Overview"]);
    clearSourceSelector();
    var s = M.stats;
    var html = '<h2 class="section-header">Overview</h2>';
    html += '<div class="overview-grid">';
    html += statCard(s.total_figures, "Figures");
    html += statCard(s.total_tables, "Tables");
    html += statCard(s.total_summaries, "Summaries");
    html += statCard(s.paradigm_count, "Study Designs");
    var aSources = analyticsSources();
    html += statCard(aSources.length, aSources.length === 1 ? "Source" : "Sources");
    html += "</div>";

    // List by source → paradigm → analysis (only analytics sources)
    for (var si = 0; si < aSources.length; si++) {
      var src = aSources[si];
      var srcEnc = encodeURIComponent(src);
      if (aSources.length > 1) {
        html += '<h2 class="section-header">' + escapeHtml(src) + '</h2>';
      }
      for (var paradigm of Object.keys(M.paradigms)) {
        var domains = domainsForParadigm(paradigm, src);
        if (domains.length === 0) continue;
        html += '<h3 style="margin:12px 0 6px">' + paradigmLabel(paradigm) + '</h3>';
        html += "<ul>" + domainListItems(paradigm, domains, src) + "</ul>";
      }
    }

    setContent(html);
  }

  // <li> rows for each domain in a paradigm (link → domain page, with counts).
  function domainListItems(paradigm, domains, src) {
    var rows = "";
    domains.forEach(function (domain) {
      var das = domainAnalyses(paradigm, domain, src);
      var nf = 0, nt = 0;
      das.forEach(function (o) {
        var ad = M.paradigms[paradigm][o.name];
        nf += (ad.figures[src] || []).length;
        nt += (ad.tables[src] || []).length;
      });
      rows += '<li><a href="#' + domainRoute(src, paradigm, domain) + '">' + escapeHtml(domain) +
        '</a> — ' + das.length + ' analys' + (das.length === 1 ? "is" : "es") +
        ', ' + nf + ' figures, ' + nt + ' tables</li>';
    });
    return rows;
  }

  function statCard(value, label) {
    return '<div class="stat-card"><div class="stat-value">' + value + '</div><div class="stat-label">' + label + '</div></div>';
  }

  /* ── Source Home (list paradigms for a source) ── */
  function renderSourceHome(src) {
    setBreadcrumb(analyticsCrumbs(src));
    clearSourceSelector();
    var srcEnc = encodeURIComponent(src);
    var html = '<h2 class="section-header">' + escapeHtml(src) + '</h2>';

    for (var paradigm of Object.keys(M.paradigms)) {
      var domains = domainsForParadigm(paradigm, src);
      if (domains.length === 0) continue;
      html += '<h3 style="margin:12px 0 6px">' + paradigmLabel(paradigm) + '</h3>';
      html += "<ul>" + domainListItems(paradigm, domains, src) + "</ul>";
    }
    setContent(html);
  }

  /* ── Study Design page (list analyses for a paradigm+source) ── */
  function renderStudyDesign(paradigm, src) {
    var analyses = M.paradigms[paradigm];
    if (!analyses) {
      setContent('<div class="empty-state"><p>Study design not found</p></div>');
      return;
    }
    setBreadcrumb(analyticsCrumbs(src, [paradigmLabel(paradigm)]));
    clearSourceSelector();

    var domains = domainsForParadigm(paradigm, src);
    var html = '<h2 class="section-header">' + paradigmLabel(paradigm) + '</h2>';
    html += "<ul>" + domainListItems(paradigm, domains, src) + "</ul>";
    setContent(html);
  }

  /* ── Analysis Page ── */
  function renderAnalysis(paradigm, analysis, src) {
    var data = (M.paradigms[paradigm] || {})[analysis];
    if (!data) {
      setContent('<div class="empty-state"><p>Analysis not found</p></div>');
      return;
    }

    setBreadcrumb(analyticsCrumbs(src, [designLabel(paradigm, analysis), analysisLabel(paradigm, analysis)]));

    // Source selector (if multiple sources have this analysis)
    var sources = M.sources.filter(function (s) {
      return (data.figures[s] && data.figures[s].length > 0) ||
             (data.tables[s] && data.tables[s].length > 0);
    });

    if (sources.length > 1) {
      renderSourceSelector(sources, src, function (newSrc) {
        location.hash = "#/analytics/" + encodeURIComponent(newSrc) + "/" + paradigm + "/" + analysis;
      });
    } else {
      clearSourceSelector();
    }

    renderAnalysisContent(paradigm, analysis, data, src, sources);
  }

  function renderAnalysisContent(paradigm, analysis, data, source, allSources) {
    var inner = buildAnalysisInner(paradigm, analysis, data, source, allSources, "a");
    var html = '<h2 class="section-header">' + designLabel(paradigm, analysis) + ' — ' + analysisLabel(paradigm, analysis) + '</h2>' + inner.html;
    setContent(html);
    initLightbox();
    bindTableToggles(inner.tables);
    bindTabs();
    bindMetricTabs();
    bindFigureGroups();
  }

  // Build the Summary/Figures/Tables tab UI for ONE analysis and return
  // {html, tables} — no <h2>, no setContent/bind — so it can be dropped into a
  // standalone analysis page OR a domain-page sub-panel (pill). `idPrefix` keeps
  // table element ids unique when several analyses share one page.
  function buildAnalysisInner(paradigm, analysis, data, source, allSources, idPrefix) {
    idPrefix = idPrefix || "a";
    var sourcesWithFigs = allSources.filter(function (s) { return data.figures[s] && data.figures[s].length > 0; });
    var figs = (data.figures[source] || []);
    var figCount = figs.length;
    var figPanel = "";
    if (sourcesWithFigs.length > 1 && source === "__compare__") {
      figPanel = renderComparisonGrid(data, sourcesWithFigs);
      figCount = sourcesWithFigs.reduce(function (n, s) { return n + data.figures[s].length; }, 0);
    } else if (figs.length > 0) {
      // Circos sets get a metric-tab / band-row layout of small click-to-enlarge
      // plots; larger sets are split into collapsible groups by an adaptive axis;
      // small sets get full-width titled rows.
      if (figs[0].filename.indexOf("circos__") === 0) {
        figPanel = renderCircosFigures(figs);
      } else {
        // Connectivity-matrix modules: metric (AEC, …) first, then figure type.
        var nested = figs.length > 8 ? chooseNestedConnectivityGrouping(figs, _contrastVocab()) : null;
        if (nested) {
          figPanel = renderNestedMetricFigures(nested);
        } else {
          var groups = figs.length > 8 ? chooseFigureGrouping(figs, _contrastVocab()) : null;
          figPanel = groups ? renderGroupedFigures(groups) : renderFigureRows(figs);
        }
      }
    }

    var tableSource = data.tables[source] ? source : Object.keys(data.tables)[0];
    var tables = data.tables[tableSource] || [];
    var tablePanel = "";
    if (tables.length > 0) {
      tablePanel = '<div class="tables-section">';
      for (var ti = 0; ti < tables.length; ti++) {
        var tbl = tables[ti];
        var id = idPrefix + "-tbl-" + ti + "-" + tbl.filename.replace(/[^a-z0-9]/gi, "_");
        var displayName = formatTableFilename(tbl.filename);
        tablePanel += '<button class="table-toggle" data-table-idx="' + ti + '" data-table-id="' + id + '">';
        tablePanel += '<span class="arrow">&#9654;</span> ' + displayName;
        tablePanel += "</button>";
        tablePanel += '<div id="' + id + '" class="table-container" style="display:none"></div>';
      }
      tablePanel += "</div>";
    }

    // Concise 'significant results by contrast' digest (generated from tables).
    var summaryPanel = data.summary ? '<div class="summary-content">' + data.summary + '</div>' : "";

    // "About this analysis" — what the test is, what it looks at, how to read it
    // (from the analysis metadata; generic to the analysis type).
    var aboutPanel = (data.meta && data.meta.about)
      ? '<div class="analysis-about"><span class="about-label">About this analysis</span> '
        + escapeHtml(data.meta.about) + '</div>' : "";

    // Natural reading order for viewers: summary, then figures, then tables.
    var tabs = [];
    if (summaryPanel) tabs.push({ id: "summary", label: "Summary", count: null, html: summaryPanel });
    if (figPanel) tabs.push({ id: "figures", label: "Figures", count: figCount, html: figPanel });
    if (tablePanel) tabs.push({ id: "tables", label: "Tables", count: tables.length, html: tablePanel });

    // Connectivity-family analyses get a collapsible metric-definitions glossary.
    var glossaryPanel = isConnectivityFamily(analysis) ? renderMetricGlossary() : "";

    var html = aboutPanel + glossaryPanel;
    if (tabs.length === 0) {
      html += '<div class="empty-state"><p>No figures, tables, or summary for this analysis.</p></div>';
    } else {
      html += '<div class="tab-bar" role="tablist">';
      tabs.forEach(function (t, i) {
        var badge = t.count != null ? ' <span class="tab-count">' + t.count + "</span>" : "";
        html += '<button class="tab-btn' + (i === 0 ? " active" : "") + '" data-tab="' + t.id + '" role="tab">' +
          t.label + badge + "</button>";
      });
      html += "</div>";
      tabs.forEach(function (t, i) {
        html += '<div class="tab-panel' + (i === 0 ? " active" : "") + '" data-panel="' + t.id + '">' + t.html + "</div>";
      });
    }
    return { html: html, tables: tables };
  }

  /* ── Domain Page (one page per paradigm × domain; secondaries nested) ──
     A domain with a single analysis renders that analysis directly; with several
     it exposes a pill bar (one pill per analysis, secondaries flagged), and each
     pill's Summary/Figures/Tables content is filled in lazily on first view. */
  function renderDomain(src, paradigm, domain) {
    var ordered = domainAnalyses(paradigm, domain, src);
    if (!ordered.length) {
      setContent('<div class="empty-state"><p>Nothing in this domain.</p></div>');
      return;
    }
    // Sensor-level is its own study design (scalp, not ROI/vertex), so it isn't
    // sub-labelled "ROI-based"; show its group (e.g. "Resting") instead.
    var isSensor = (domain === SENSOR_DOMAIN);
    var domainSub = isSensor ? (paradigmGroup(paradigm) || "") : paradigmLabel(paradigm);
    setBreadcrumb(analyticsCrumbs(src, isSensor ? [domain] : [paradigmLabel(paradigm), domain]));
    clearSourceSelector();

    var html = '<h2 class="section-header">' + escapeHtml(domain) +
      (domainSub ? ' <span class="domain-sub">' + escapeHtml(domainSub) + '</span>' : "") + '</h2>';
    if (ordered.length > 1) {
      html += '<div class="pill-bar" role="tablist">';
      ordered.forEach(function (o, i) {
        var supTip = o.supp ? ' title="Runs after ' +
          escapeHtml(M.paradigms[paradigm][o.name].meta.supplements) + '"' : "";
        var supTag = o.supp ? ' <span class="pill-supp">supplemental</span>' : "";
        html += '<button class="pill' + (i === 0 ? " active" : "") + '" data-pill="' + i + '"' +
          supTip + '>' + analysisLabel(paradigm, o.name) + supTag + "</button>";
      });
      html += "</div>";
    }
    ordered.forEach(function (o, i) {
      html += '<div class="pill-panel' + (i === 0 ? " active" : "") + '" data-pillpanel="' + i + '"></div>';
    });
    setContent(html);

    var rendered = {};
    function fill(i) {
      if (rendered[i]) return;
      rendered[i] = true;
      var o = ordered[i];
      var data = M.paradigms[paradigm][o.name];
      var allSources = M.sources.filter(function (s) {
        return (data.figures[s] && data.figures[s].length > 0) ||
               (data.tables[s] && data.tables[s].length > 0);
      });
      var asrc = analysisHasData(data, src) ? src : (allSources[0] || src);
      var cont = document.querySelector('[data-pillpanel="' + i + '"]');
      var inner = buildAnalysisInner(paradigm, o.name, data, asrc, allSources, "p" + i);
      var desc = (data.meta && data.meta.description)
        ? ' <span class="analysis-desc">' + escapeHtml(data.meta.description) + '</span>' : "";
      cont.innerHTML = (ordered.length > 1
        ? '<h3 class="analysis-sub-header">' + analysisLabel(paradigm, o.name) + desc + '</h3>' : "") + inner.html;
      initLightbox();
      bindTableToggles(inner.tables, cont);
      bindTabs(cont);
      bindMetricTabs(cont);
      bindFigureGroups(cont);
    }
    fill(0);

    document.querySelectorAll(".pill").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var i = parseInt(btn.getAttribute("data-pill"), 10);
        document.querySelectorAll(".pill").forEach(function (b) { b.classList.toggle("active", b === btn); });
        document.querySelectorAll(".pill-panel").forEach(function (p) {
          p.classList.toggle("active", p.getAttribute("data-pillpanel") === String(i));
        });
        fill(i);
      });
    });
  }

  function bindTabs(root) {
    root = root || document;
    var btns = root.querySelectorAll(".tab-btn");
    btns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-tab");
        root.querySelectorAll(".tab-btn").forEach(function (b) {
          b.classList.toggle("active", b === btn);
        });
        root.querySelectorAll(".tab-panel").forEach(function (p) {
          p.classList.toggle("active", p.getAttribute("data-panel") === id);
        });
      });
    });
  }

  /* ── Localization Pages ── */
  /* Treatment-group helpers (shared by the localization pages) */
  var TX_GROUP_ORDER = ["WT_VEH", "KO_VEH", "KO_HD_ICV", "KO_HD_IV", "KO_LD_IV_ICV"];
  var TX_GROUP_LABELS = {
    "WT_VEH": "WT Vehicle", "KO_VEH": "KO Vehicle",
    "KO_HD_ICV": "KO HD-ICV", "KO_HD_IV": "KO HD-IV", "KO_LD_IV_ICV": "KO LD-IV+ICV",
  };
  function formatGroup(g) {
    if (!g) return "Unknown";
    return TX_GROUP_LABELS[g] || g.replace(/_/g, " ");
  }
  function groupSubjects(loc) {
    var meta = loc.subject_meta || {};
    var buckets = {};
    for (var key of Object.keys(loc.subjects || {})) {
      var g = (meta[key] && meta[key].group) || "Unknown";
      (buckets[g] = buckets[g] || []).push(key);
    }
    var order = TX_GROUP_ORDER.filter(function (g) { return buckets[g]; })
      .concat(Object.keys(buckets).filter(function (g) { return TX_GROUP_ORDER.indexOf(g) < 0; }));
    return order.map(function (g) { return { group: g, subjects: buckets[g].sort() }; });
  }
  function subjectIsOutlier(loc, key) {
    var m = loc.subject_meta && loc.subject_meta[key];
    return m && m.outliers && m.outliers.length ? m.outliers : null;
  }

  function renderLocalizationHome() {
    setBreadcrumb(["Localization"]);
    clearSourceSelector();
    var html = '<h2 class="section-header">Localization</h2>';
    html += '<p class="page-lead">Source-reconstruction pipelines and per-subject QC.</p>';
    html += '<div class="loc-cards">';
    for (var source of Object.keys(M.localization)) {
      var loc = M.localization[source];
      var nSub = Object.keys(loc.subjects || {}).length;
      var nOut = loc.n_outliers || 0;
      var enc = encodeURIComponent(source);
      html += '<div class="loc-card">';
      html += '<h3>' + escapeHtml(source) + '</h3>';
      html += '<div class="loc-stats"><span>' + nSub + ' subjects</span>';
      html += '<span class="' + (nOut ? "loc-flag" : "") + '">' + nOut + ' outlier' + (nOut === 1 ? "" : "s") + '</span></div>';
      html += '<div class="loc-groups">';
      for (var gb of groupSubjects(loc)) {
        html += '<span class="loc-group-chip">' + escapeHtml(formatGroup(gb.group)) + ' <b>' + gb.subjects.length + '</b></span>';
      }
      html += '</div><div class="loc-links">';
      html += '<a class="btn-link" href="#/localization/subjects/' + enc + '">Browse subjects</a>';
      html += '<a class="btn-link" href="#/localization/qc/' + enc + '">QC dashboard</a>';
      html += '</div></div>';
    }
    html += '</div>';
    setContent(html);
  }

  function renderQC(sourceEnc) {
    var source = decodeURIComponent(sourceEnc || "");
    var loc = M.localization[source];
    if (!loc) { setContent('<div class="empty-state">Source not found</div>'); return; }

    setBreadcrumb(["Localization", source, "QC"]);
    clearSourceSelector();

    var nSub = Object.keys(loc.subjects || {}).length;
    var nOut = loc.n_outliers || 0;
    var html = '<h2 class="section-header">QC — ' + escapeHtml(source) + '</h2>';
    html += '<p class="qc-lead">' + nSub + ' subjects &middot; <span class="' + (nOut ? "loc-flag" : "") + '">' +
      nOut + ' flagged as outlier' + (nOut === 1 ? "" : "s") + '</span> (z &gt; 2 on key metrics).</p>';

    var figsPanel = (loc.qc_figures && loc.qc_figures.length) ? renderFigureRows(loc.qc_figures) : "";
    var metricsPanel = (loc.qc_metrics && loc.qc_metrics.length) ? renderQCMetricsTable(loc.qc_metrics, loc.subject_meta) : "";
    var reportPanel = loc.qc_report ? '<iframe class="qc-iframe" src="' + loc.qc_report + '"></iframe>' : "";

    var tabs = [];
    if (figsPanel) tabs.push({ id: "figures", label: "Figures", html: figsPanel });
    if (metricsPanel) tabs.push({ id: "metrics", label: "Metrics", html: metricsPanel });
    if (reportPanel) tabs.push({ id: "report", label: "Report", html: reportPanel });

    if (tabs.length === 0) {
      html += '<div class="empty-state"><p>No QC data for this source.</p></div>';
    } else {
      html += '<div class="tab-bar" role="tablist">';
      tabs.forEach(function (t, i) {
        html += '<button class="tab-btn' + (i === 0 ? " active" : "") + '" data-tab="' + t.id + '">' + t.label + '</button>';
      });
      html += '</div>';
      tabs.forEach(function (t, i) {
        html += '<div class="tab-panel' + (i === 0 ? " active" : "") + '" data-panel="' + t.id + '">' + t.html + '</div>';
      });
    }

    setContent(html);
    initLightbox();
    initTableSort();
    bindTabs();
  }

  function renderQCMetricsTable(metrics, subjectMeta) {
    if (!metrics || metrics.length === 0) return "";
    subjectMeta = subjectMeta || {};
    var outlierIds = {};
    for (var k of Object.keys(subjectMeta)) {
      if (subjectMeta[k].outliers && subjectMeta[k].outliers.length) {
        outlierIds[k.replace(/^sub-/, "")] = subjectMeta[k].outliers;
      }
    }
    var headers = Object.keys(metrics[0]);
    var html = '<div class="table-container"><table><thead><tr>';
    for (var h of headers) {
      html += '<th>' + escapeHtml(h) + '<span class="sort-indicator"></span></th>';
    }
    html += "</tr></thead><tbody>";
    for (var row of metrics) {
      var flagged = outlierIds[String(row.subject_id)];
      html += "<tr" + (flagged ? ' class="qc-outlier-row" title="Outlier: ' + escapeHtml(flagged.join(", ")) + '"' : "") + ">";
      for (var h of headers) {
        html += '<td>' + escapeHtml(row[h] || "") + '</td>';
      }
      html += "</tr>";
    }
    html += "</tbody></table></div>";
    return html;
  }

  function renderSubjects(sourceEnc) {
    var source = decodeURIComponent(sourceEnc || "");
    var loc = M.localization[source];
    if (!loc) { setContent('<div class="empty-state">Source not found</div>'); return; }

    setBreadcrumb(["Localization", source, "Subjects"]);
    clearSourceSelector();

    var subjectKeys = Object.keys(loc.subjects || {});
    if (subjectKeys.length === 0) {
      setContent('<div class="empty-state"><p>No subject figures found</p></div>');
      return;
    }

    var html = '<h2 class="section-header">Subjects — ' + escapeHtml(source) + '</h2>';
    html += '<div class="subject-browser"><div class="subject-list">';
    for (var gb of groupSubjects(loc)) {
      html += '<div class="subject-group"><div class="subject-group-label">' +
        escapeHtml(formatGroup(gb.group)) + ' <span class="cnt">' + gb.subjects.length + '</span></div>';
      html += '<div class="subject-chips">';
      for (var key of gb.subjects) {
        var sid = key.replace(/^sub-/, "");
        var out = subjectIsOutlier(loc, key);
        html += '<button class="subject-chip' + (out ? " is-outlier" : "") + '" data-sub="' + key + '"' +
          (out ? ' title="Outlier: ' + escapeHtml(out.join(", ")) + '"' : "") + '>' +
          escapeHtml(sid) + (out ? ' <span class="warn">&#9888;</span>' : "") + '</button>';
      }
      html += '</div></div>';
    }
    html += '</div><div class="subject-detail"><div id="subject-meta"></div><div id="subject-figures"></div></div></div>';

    setContent(html);

    var chips = document.querySelectorAll(".subject-chip");
    chips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        chips.forEach(function (c) { c.classList.toggle("active", c === chip); });
        showSubject(loc, chip.getAttribute("data-sub"));
      });
    });
    if (chips.length) {
      chips[0].classList.add("active");
      showSubject(loc, chips[0].getAttribute("data-sub"));
    }
  }

  function showSubject(loc, key) {
    var meta = (loc.subject_meta && loc.subject_meta[key]) || { group: null, outliers: [] };
    var sid = key.replace(/^sub-/, "");
    var bits = '<span class="sm-id">' + escapeHtml(sid) + '</span>';
    if (meta.group) bits += '<span class="sm-group">' + escapeHtml(formatGroup(meta.group)) + '</span>';
    if (meta.outliers && meta.outliers.length) {
      bits += '<span class="sm-out">&#9888; outlier: ' + escapeHtml(meta.outliers.join(", ")) + '</span>';
    }
    document.getElementById("subject-meta").innerHTML = '<div class="subject-meta-bar">' + bits + '</div>';
    document.getElementById("subject-figures").innerHTML = renderFigureRows(loc.subjects[key] || []);
    initLightbox();
  }

  /* ── Search ── */
  function initSearch() {
    var input = document.getElementById("search-input");
    var debounce = null;
    input.addEventListener("input", function () {
      clearTimeout(debounce);
      debounce = setTimeout(function () {
        var q = input.value.trim();
        if (q.length >= 2) {
          location.hash = "#/search/" + encodeURIComponent(q);
        } else if (q.length === 0) {
          location.hash = "#/overview";
        }
      }, 300);
    });
  }

  function renderSearch(query) {
    setBreadcrumb(["Search", query]);
    clearSourceSelector();
    var q = query.toLowerCase();
    var results = [];

    for (var paradigm of Object.keys(M.paradigms)) {
      var analyses = M.paradigms[paradigm];
      for (var analysis of Object.keys(analyses)) {
        var data = analyses[analysis];
        for (var source of Object.keys(data.figures)) {
          var figs = data.figures[source];
          for (var fig of figs) {
            if (fig.filename.toLowerCase().includes(q) ||
                paradigm.toLowerCase().includes(q) ||
                analysis.toLowerCase().includes(q) ||
                formatName(analysis).toLowerCase().includes(q)) {
              results.push({ type: "figure", paradigm: paradigm, analysis: analysis, source: source, item: fig });
            }
          }
        }
      }
    }

    var html = '<h2 class="section-header">Search: "' + escapeHtml(query) + '"</h2>';
    html += '<p class="search-results-header">' + results.length + ' result(s)</p>';

    if (results.length > 0) {
      var figItems = results.filter(function (r) { return r.type === "figure"; }).map(function (r) { return r.item; });
      html += renderFigureGrid(figItems, PAGE_SIZE);
    }

    setContent(html);
    initLightbox();
  }

  /* ── Figure Grid ── */
  function renderFigureGrid(figs, limit) {
    if (!figs || figs.length === 0) {
      return '<div class="empty-state"><p>No figures</p></div>';
    }
    var show = Math.min(figs.length, limit);
    var html = '<div class="figure-grid">';
    for (var i = 0; i < show; i++) {
      var fig = figs[i];
      html += '<a href="' + fig.path + '" class="glightbox figure-card" data-gallery="gallery">';
      html += '<img src="' + fig.thumb + '" alt="' + escapeHtml(fig.filename) + '" loading="lazy">';
      html += '<div class="caption">' + escapeHtml(fig.filename) + '</div>';
      html += "</a>";
    }
    html += "</div>";

    if (figs.length > limit) {
      html += '<button class="show-more-btn" onclick="window._showMore(this)" data-figs=\'' +
        JSON.stringify(figs.slice(limit)).replace(/'/g, "&#39;") +
        "'>Show " + (figs.length - limit) + " more</button>";
    }
    return html;
  }

  // The facet that distinguishes one figure in a module from the next — band
  // (Delta…), aperiodic measure (exponent/offset), or power type. Surfaced up
  // front so a reader can tell figures apart at a glance instead of hunting the
  // end of the title. Bands come from BAND_ORDER (defined below; available at
  // call time).
  function _figureFacet(name) {
    var measures = ["Exponent", "Offset", "Relative", "Absolute"];
    var facets = BAND_ORDER.concat(measures);  // bands first — prefer the band
    for (var i = 0; i < facets.length; i++) {
      var re = new RegExp("(^|\\s)" + facets[i].replace(/ /g, "\\s") + "(\\s|$)", "i");
      if (re.test(name)) return { facet: facets[i], re: re };
    }
    return null;
  }

  function formatFigureTitle(filename) {
    var name = (filename || "").replace(/\.(png|jpe?g|svg|pdf)$/i, "");
    name = name.replace(/^\d+[_-]/, "");   // strip a leading "01_"
    name = name.replace(/__+/g, " — ");    // double underscore = section separator
    name = name.replace(/_/g, " ").trim(); // single underscore = space (hyphens kept)
    // Title-case word initials, fixing known acronyms (ROI, PSD, MVPA, NBS, …).
    name = name.replace(/\S+/g, function (w) {
      var key = w.toLowerCase();
      if (ACRONYMS[key]) return ACRONYMS[key];
      return w.charAt(0).toUpperCase() + w.slice(1);
    });
    name = name.replace(/\bZscore\b/i, "Z-Score");
    // Lead with the distinguishing facet (band / aperiodic measure) when present,
    // dropping the redundant "Effect Size" prefix every analysis figure carries.
    var hit = _figureFacet(name);
    if (hit) {
      var rest = name.replace(hit.re, " ").replace(/\s+/g, " ")
        .replace(/^Effect Size\s*/i, "").trim();
      return rest ? hit.facet + " — " + rest : hit.facet;
    }
    return name;
  }

  // One figure per full-width row with a title — for reading diagnostics inline
  // (vs the thumbnail grid). Full image shown; click opens the lightbox to zoom.
  /* ── Adaptive figure grouping ─────────────────────────────────────────────
     A module can emit 200+ figures; a flat wall is unreadable. We group them by
     the single axis that best organizes THAT module, chosen adaptively from the
     filenames so it works for any study without hardcoding:
       kind (figure-type prefix) → contrast → connectivity/coupling metric → band.
     Rendered as collapsible sections so the page opens as a handful of headers. */
  var GROUP_VOCAB = {
    // longest-first within each list so "imag_coherence" beats "coherence",
    // "high_gamma" beats "gamma", "partial_correlation" beats "partial_corr".
    conn_metric: ["imag_coherence", "partial_correlation", "partial_corr",
                  "coherence", "dwpli", "wpli", "dpli", "pli", "aec"],
    coupling_metric: ["pac", "aac", "ppc"],
    // both "_" and " " gamma variants — filenames built from display band names
    // ("High Gamma") use spaces, source-space maps ("high_gamma") use underscores.
    band: ["low_gamma", "high_gamma", "low gamma", "high gamma", "peak_alpha",
           "spectral_slope", "delta", "theta", "alpha", "beta", "gamma", "epsilon"],
    power: ["absolute", "relative"],
    flow: ["inflow", "outflow", "netflow"],
    measure: ["summary", "exponent", "offset"],
    group_name: ["ko_ld_iv_icv", "ko_hd_icv", "ko_hd_iv", "ko_veh", "wt_veh"],
  };
  function _escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
  function _contrastVocab() {
    // Longest-first so "hd_icv_rescue" is matched before any shorter substring.
    return Object.keys((M && M.contrast_labels) || {})
      .map(function (k) { return k.toLowerCase(); })
      .sort(function (a, b) { return b.length - a.length; });
  }
  // Position of `value` in `base` only when it sits on token boundaries
  // (start/end or _ - space), so "pli" doesn't match inside "dwpli". -1 if absent.
  function _tokenHit(base, value) {
    var i = base.indexOf(value);
    while (i !== -1) {
      var b = i === 0 ? "" : base.charAt(i - 1);
      var aPos = i + value.length;
      var a = aPos >= base.length ? "" : base.charAt(aPos);
      var okB = b === "" || b === "_" || b === "-" || b === " ";
      var okA = a === "" || a === "_" || a === "-" || a === " ";
      if (okB && okA) return i;
      i = base.indexOf(value, i + 1);
    }
    return -1;
  }
  function _axisValue(base, values) {           // first (longest) value that hits
    for (var i = 0; i < values.length; i++) {
      if (_tokenHit(base, values[i]) !== -1) return values[i];
    }
    return null;
  }
  function _figBase(fig) {
    return (fig.filename || "").replace(/\.(png|jpe?g|svg|pdf)$/i, "").toLowerCase();
  }
  // Figure "kind" = the descriptive words left after removing every variable
  // token (contrast / band / metric / power / flow / group / measure), wherever
  // they sit. "fcd" from "fcd_alpha_aec"; "peak_presence" from "alpha_peak_presence";
  // "region_significance_heatmap" from "region_significance_heatmap_disease_effect_relative".
  var _kindVocabCache = null, _kindVocabKey = null;
  function _kindVocab(contrasts) {
    var key = contrasts.join("|");
    if (_kindVocabKey === key) return _kindVocabCache;
    var all = contrasts
      .concat(GROUP_VOCAB.conn_metric, GROUP_VOCAB.coupling_metric, GROUP_VOCAB.band,
              GROUP_VOCAB.power, GROUP_VOCAB.flow, GROUP_VOCAB.measure, GROUP_VOCAB.group_name);
    // Longest-first so "imag_coherence" is removed before "coherence" can strand "imag".
    all = all.filter(function (v, i) { return all.indexOf(v) === i; })
             .sort(function (a, b) { return b.length - a.length; })
             .map(function (v) { return new RegExp("(^|[_\\-\\s])" + _escapeRe(v) + "(?=$|[_\\-\\s])", "g"); });
    _kindVocabKey = key; _kindVocabCache = all;
    return all;
  }
  function _figKind(base, contrasts) {
    var s = base;
    _kindVocab(contrasts).forEach(function (re) { s = s.replace(re, "$1"); });
    s = s.replace(/[_\-\s]+/g, "_").replace(/^_|_$/g, "");
    return s || base;
  }
  function _kindLabel(kind) { return formatName(kind.replace(/_+/g, " ").trim()); }
  function _bandOrderKey(base) {
    for (var i = 0; i < BAND_ORDER.length; i++) {
      if (_tokenHit(base, BAND_ORDER[i].toLowerCase().replace(/ /g, "_")) !== -1) return i;
    }
    return 99;
  }
  // Choose the best grouping axis for this figure set; return ordered groups or
  // null (→ render flat). Axes are tried in priority order and the first that
  // partitions the set usefully wins.
  function chooseFigureGrouping(figs, contrasts) {
    var N = figs.length;
    function build(valueOf) {
      var map = {}, order = [];
      figs.forEach(function (f) {
        var v = valueOf(_figBase(f)) || "__other__";
        if (!map[v]) { map[v] = []; order.push(v); }
        map[v].push(f);
      });
      return { map: map, order: order };
    }
    // kind: qualifies when it yields 2–15 balanced groups (no group > 70%).
    var k = build(function (base) { return _figKind(base, contrasts); });
    if (k.order.length >= 2 && k.order.length <= 15) {
      var maxShare = Math.max.apply(null, k.order.map(function (v) { return k.map[v].length; })) / N;
      if (maxShare <= 0.70) {
        return k.order.map(function (v) { return { key: v, label: _kindLabel(v), figs: k.map[v] }; });
      }
    }
    // contrast / metric / band: qualify at ≥2 values covering ≥60% of figures.
    var axes = [
      { valueOf: function (b) { return _axisValue(b, contrasts); },
        label: function (v) { return (M.contrast_labels && M.contrast_labels[v]) || formatName(v); } },
      { valueOf: function (b) { return _axisValue(b, GROUP_VOCAB.conn_metric); }, label: metricLabel },
      { valueOf: function (b) { return _axisValue(b, GROUP_VOCAB.coupling_metric); }, label: metricLabel },
      { valueOf: function (b) { return _axisValue(b, GROUP_VOCAB.band); }, label: formatName },
    ];
    for (var ai = 0; ai < axes.length; ai++) {
      var g = build(axes[ai].valueOf);
      var matched = N - (g.map.__other__ ? g.map.__other__.length : 0);
      var distinct = g.order.filter(function (v) { return v !== "__other__"; }).length;
      if (distinct >= 2 && matched >= 0.6 * N) {
        var lab = axes[ai].label;
        var groups = g.order.filter(function (v) { return v !== "__other__"; })
          .map(function (v) { return { key: v, label: lab(v), figs: g.map[v] }; });
        if (g.map.__other__) groups.push({ key: "__other__", label: "Other", figs: g.map.__other__ });
        return groups;
      }
    }
    return null;
  }
  function renderGroupedFigures(groups) {
    var html = '<div class="figure-groups">';
    html += '<div class="fig-group-controls">' +
      '<button type="button" class="fig-toggle-all" data-open="1">Expand all</button>' +
      '<button type="button" class="fig-toggle-all" data-open="0">Collapse all</button></div>';
    groups.forEach(function (g, i) {
      var open = i === 0 ? " open" : "";
      var sorted = g.figs.slice().sort(function (a, b) {
        var ba = _figBase(a), bb = _figBase(b);
        return (_bandOrderKey(ba) - _bandOrderKey(bb)) || ba.localeCompare(bb);
      });
      html += '<details class="fig-group"' + open + '>';
      html += '<summary class="fig-group-summary">' + escapeHtml(g.label) +
        ' <span class="fig-group-count">' + g.figs.length + '</span></summary>';
      html += renderFigureRows(sorted);
      html += '</details>';
    });
    html += "</div>";
    return html;
  }
  // Connectivity-matrix modules (e.g. roi_connectivity): organize figures by
  // metric (AEC, Coherence, …) FIRST, then by figure type (Circos / Heatmap /
  // Matrix), then band. Returns [{metric,label,kinds:[{kind,label,figs}]}] or
  // null when the set isn't metric×figure-type shaped.
  function chooseNestedConnectivityGrouping(figs, contrasts) {
    function metricOf(b) { return _axisValue(b, GROUP_VOCAB.conn_metric); }
    var nMetric = figs.filter(function (f) { return metricOf(_figBase(f)); }).length;
    if (nMetric < 0.5 * figs.length) return null;      // not a metric-keyed set
    var byMetric = {}, morder = [], kinds = {};
    figs.forEach(function (f) {
      var base = _figBase(f);
      var m = metricOf(base) || "__other__";
      var kind = _figKind(base, contrasts) || "figures";
      kinds[kind] = true;
      if (!byMetric[m]) { byMetric[m] = {}; morder.push(m); }
      (byMetric[m][kind] = byMetric[m][kind] || []).push(f);
    });
    var distinctMetrics = morder.filter(function (m) { return m !== "__other__"; }).length;
    if (distinctMetrics < 2 || Object.keys(kinds).length < 2) return null;
    morder.sort(function (a, b) {
      if (a === "__other__") return 1;
      if (b === "__other__") return -1;
      var ia = METRIC_ORDER.indexOf(a), ib = METRIC_ORDER.indexOf(b);
      if (ia === -1) ia = 99;
      if (ib === -1) ib = 99;
      return ia - ib || a.localeCompare(b);
    });
    function bandSort(a, b) {
      var ba = _figBase(a), bb = _figBase(b);
      return (_bandOrderKey(ba) - _bandOrderKey(bb)) || ba.localeCompare(bb);
    }
    return morder.map(function (m) {
      var kmap = byMetric[m];
      return {
        metric: m,
        label: m === "__other__" ? "Other" : metricLabel(m),
        kinds: Object.keys(kmap).sort().map(function (k) {
          return { kind: k, label: _kindLabel(k), figs: kmap[k].slice().sort(bandSort) };
        }),
      };
    });
  }
  function renderNestedMetricFigures(nested) {
    var html = '<div class="figure-groups">';
    html += '<div class="fig-group-controls">' +
      '<button type="button" class="fig-toggle-all" data-open="1">Expand all</button>' +
      '<button type="button" class="fig-toggle-all" data-open="0">Collapse all</button></div>';
    nested.forEach(function (mg, i) {
      var open = i === 0 ? " open" : "";
      var count = mg.kinds.reduce(function (n, k) { return n + k.figs.length; }, 0);
      html += '<details class="fig-group"' + open + '>';
      html += '<summary class="fig-group-summary">' + escapeHtml(mg.label) +
        ' <span class="fig-group-count">' + count + '</span></summary>';
      mg.kinds.forEach(function (k) {
        html += '<div class="fig-subgroup-title">' + escapeHtml(k.label) +
          ' <span class="fig-group-count">' + k.figs.length + '</span></div>';
        html += renderFigureRows(k.figs);
      });
      html += '</details>';
    });
    html += "</div>";
    return html;
  }
  function bindFigureGroups(root) {
    (root || document).querySelectorAll(".fig-toggle-all").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var open = btn.getAttribute("data-open") === "1";
        var scope = btn.closest(".figure-groups") || document;
        scope.querySelectorAll("details.fig-group").forEach(function (d) { d.open = open; });
      });
    });
  }

  function renderFigureRows(figs) {
    if (!figs || figs.length === 0) {
      return '<div class="empty-state"><p>No figures</p></div>';
    }
    var html = '<div class="figure-rows">';
    for (var fig of figs) {
      html += '<figure class="figure-row">';
      html += '<figcaption>' + escapeHtml(formatFigureTitle(fig.filename)) + '</figcaption>';
      html += '<a href="' + fig.path + '" class="glightbox" data-gallery="gallery">';
      html += '<img src="' + fig.path + '" alt="' + escapeHtml(fig.filename) + '" loading="lazy">';
      html += '</a></figure>';
    }
    html += "</div>";
    return html;
  }

  /* ── Circos figures: metric tabs → band rows → small click-to-enlarge plots ── */
  var BAND_ORDER = ["Delta", "Theta", "Alpha", "Beta", "Low Gamma", "High Gamma", "Epsilon"];
  var METRIC_ORDER = ["imag_coherence", "dwpli", "pli", "aec", "coherence"];
  var METRIC_LABELS = {
    imag_coherence: "Imag. coherence", coherence: "Coherence",
    dwpli: "dwPLI", wpli: "wPLI", pli: "PLI", dpli: "dPLI", aec: "AEC",
    partial_corr: "Partial corr.", partial_correlation: "Partial corr.",
    pac: "PAC", aac: "AAC", ppc: "PPC",
  };
  var CONTRAST_UPPER = { hd: "HD", icv: "ICV", iv: "IV", ld: "LD", wt: "WT", veh: "Veh" };

  function metricLabel(m) { return METRIC_LABELS[m] || formatName(m); }

  /* ── Connectivity metric glossary ─────────────────────────────────────────
     Definitions of the same-frequency functional-connectivity metrics, shown on
     connectivity-family analysis pages. Sourced from CONNECTIVITY_METHODS.md
     (source-analytics) — each carries its primary reference. */
  var METRIC_DEFS = [
    { key: "coherence", name: "Coherence (magnitude-squared)",
      def: "Squared cross-spectrum normalized by both auto-spectra, |S<sub>xy</sub>|² / (S<sub>xx</sub>·S<sub>yy</sub>); range 0–1. Total linear coupling at a frequency — but maximally sensitive to zero-lag volume conduction.",
      cite: "Carter 1987; classical" },
    { key: "imag_coherence", name: "Imaginary coherence",
      def: "Imaginary part of coherency, ℑ(S<sub>ij</sub>) / √(S<sub>ii</sub>·S<sub>jj</sub>). Volume-conduction coupling is purely real, so a non-zero imaginary part reflects genuine time-lagged interaction.",
      cite: "Nolte et al. 2004" },
    { key: "pli", name: "Phase Lag Index (PLI)",
      def: "Consistency of the sign of the phase difference, |⟨sign(ℑ)⟩|; range 0–1. Ignores zero-lag (volume-conduction) coupling by construction.",
      cite: "Stam et al. 2007" },
    { key: "wpli", name: "Weighted PLI (wPLI)",
      def: "PLI weighted by the magnitude of the imaginary cross-spectrum, |E{ℑ}| / E{|ℑ|}. Less sensitive to noise and to small perturbations near zero phase lag.",
      cite: "Vinck et al. 2011, Eq. 8" },
    { key: "dwpli", name: "Debiased weighted PLI² (dwPLI)",
      def: "wPLI² with the sample-size bias removed (self-term diagonal excluded). May take small negative values where true connectivity is ~0 — expected, not an error.",
      cite: "Vinck et al. 2011, Eqs. 31–32" },
    { key: "dpli", name: "Directed PLI (dPLI)",
      def: "Directional PLI: mean Heaviside of the phase difference; range 0–1. dPLI > 0.5 ⇒ region i phase-leads j; dPLI<sub>ij</sub>+dPLI<sub>ji</sub>=1.",
      cite: "Stam & van Straaten 2012" },
    { key: "aec", name: "Orthogonalized amplitude-envelope correlation (AEC)",
      def: "Pearson correlation of band-power envelopes after pairwise orthogonalization removes the zero-lag shared signal (both directions averaged). Captures amplitude co-modulation of genuinely distinct sources.",
      cite: "Hipp et al. 2012" },
    { key: "partial_corr", name: "Partial correlation",
      def: "Correlation between two regions with all others regressed out, from the (shrinkage-regularized) inverse covariance: −p<sub>ij</sub> / √(p<sub>ii</sub>·p<sub>jj</sub>). Separates direct from indirect connections.",
      cite: "Marrelec et al. 2006" },
  ];
  // Analyses that use these same-frequency FC metrics (→ show the glossary).
  function isConnectivityFamily(analysis) {
    return /(_connectivity|_nbs|_graph|fcd_comparison)$/.test(analysis || "");
  }
  function renderMetricGlossary() {
    var html = '<details class="metric-glossary">';
    html += '<summary class="metric-glossary-summary">Connectivity metric definitions</summary>';
    html += '<dl class="metric-glossary-list">';
    METRIC_DEFS.forEach(function (m) {
      html += '<dt>' + escapeHtml(m.name) + '</dt>';
      html += '<dd>' + m.def +
        ' <span class="metric-cite">' + escapeHtml(m.cite) + '</span></dd>';
    });
    html += '</dl></details>';
    return html;
  }

  function circosContrastLabel(name) {
    return name.split("_").map(function (t) {
      var l = t.toLowerCase();
      if (CONTRAST_UPPER[l]) return CONTRAST_UPPER[l];
      if (l === "vs") return "vs";
      return t.charAt(0).toUpperCase() + t.slice(1);
    }).join(" ");
  }

  function parseCircos(filename) {
    var base = (filename || "").replace(/\.png$/i, "");
    if (base.indexOf("circos__") !== 0) return null;
    var parts = base.slice("circos__".length).split("__");
    if (parts.length < 3) return null;
    return { metric: parts[0], band: parts[1], contrast: parts.slice(2).join("__") };
  }

  function orderBands(bands) {
    return bands.slice().sort(function (a, b) {
      var ia = BAND_ORDER.indexOf(formatName(a)); if (ia < 0) ia = 99;
      var ib = BAND_ORDER.indexOf(formatName(b)); if (ib < 0) ib = 99;
      return ia - ib || a.localeCompare(b);
    });
  }

  function renderCircosFigures(figs) {
    var byMetric = {};
    figs.forEach(function (f) {
      var p = parseCircos(f.filename);
      if (!p) return;
      byMetric[p.metric] = byMetric[p.metric] || {};
      (byMetric[p.metric][p.band] = byMetric[p.metric][p.band] || []).push({ fig: f, contrast: p.contrast });
    });
    var metrics = Object.keys(byMetric);
    if (!metrics.length) return renderFigureRows(figs);
    metrics.sort(function (a, b) {
      var ia = METRIC_ORDER.indexOf(a); if (ia < 0) ia = 99;
      var ib = METRIC_ORDER.indexOf(b); if (ib < 0) ib = 99;
      return ia - ib || a.localeCompare(b);
    });

    var html = '<div class="metric-tabs" role="tablist">';
    metrics.forEach(function (m, i) {
      html += '<button class="metric-tab' + (i === 0 ? " active" : "") + '" data-mtab="' +
        escapeHtml(m) + '">' + escapeHtml(metricLabel(m)) + "</button>";
    });
    html += "</div>";

    metrics.forEach(function (m, i) {
      html += '<div class="metric-panel' + (i === 0 ? " active" : "") + '" data-mpanel="' + escapeHtml(m) + '">';
      orderBands(Object.keys(byMetric[m])).forEach(function (band) {
        html += '<div class="band-block"><h4 class="band-title">' + escapeHtml(formatName(band)) + "</h4>";
        html += '<div class="band-figs">';
        byMetric[m][band].forEach(function (it) {
          html += '<figure class="circos-thumb">' +
            '<a class="glightbox" href="' + it.fig.path + '" data-gallery="gallery">' +
            '<img src="' + it.fig.thumb + '" loading="lazy" alt="' + escapeHtml(it.fig.filename) + '"></a>' +
            '<figcaption>' + escapeHtml(circosContrastLabel(it.contrast)) + "</figcaption></figure>";
        });
        html += "</div></div>";
      });
      html += "</div>";
    });
    return html;
  }

  function bindMetricTabs(root) {
    (root || document).querySelectorAll(".metric-tabs").forEach(function (bar) {
      var container = bar.parentNode;
      bar.querySelectorAll(".metric-tab").forEach(function (btn) {
        btn.addEventListener("click", function () {
          var id = btn.getAttribute("data-mtab");
          bar.querySelectorAll(".metric-tab").forEach(function (b) { b.classList.toggle("active", b === btn); });
          container.querySelectorAll(".metric-panel").forEach(function (p) {
            p.classList.toggle("active", p.getAttribute("data-mpanel") === id);
          });
        });
      });
    });
  }

  window._showMore = function (btn) {
    try {
      var extra = JSON.parse(btn.getAttribute("data-figs"));
      var grid = btn.previousElementSibling;
      for (var fig of extra) {
        var a = document.createElement("a");
        a.href = fig.path;
        a.className = "glightbox figure-card";
        a.setAttribute("data-gallery", "gallery");
        a.innerHTML = '<img src="' + fig.thumb + '" alt="' + escapeHtml(fig.filename) +
          '" loading="lazy"><div class="caption">' + escapeHtml(fig.filename) + '</div>';
        grid.appendChild(a);
      }
      btn.remove();
      initLightbox();
    } catch (e) {
      console.error("Show more error:", e);
    }
  };

  /* ── Comparison Grid ── */
  function renderComparisonGrid(data, sources) {
    var html = '<div class="comparison-grid">';
    for (var source of sources) {
      html += '<div class="comparison-column"><h3>' + escapeHtml(source) + '</h3>';
      html += renderFigureGrid(data.figures[source] || [], PAGE_SIZE);
      html += "</div>";
    }
    html += "</div>";
    return html;
  }

  /* ── Source Selector ── */
  function renderSourceSelector(sources, current, onChange) {
    var el = document.getElementById("source-selector");
    var html = "<label>Source: <select id='source-select'>";
    for (var s of sources) {
      var sel = s === current ? " selected" : "";
      html += '<option value="' + escapeHtml(s) + '"' + sel + '>' + escapeHtml(s) + '</option>';
    }
    if (sources.length > 1) {
      html += '<option value="__compare__">Compare All</option>';
    }
    html += "</select></label>";
    el.innerHTML = html;

    document.getElementById("source-select").addEventListener("change", function (e) {
      onChange(e.target.value);
    });
  }

  function clearSourceSelector() {
    document.getElementById("source-selector").innerHTML = "";
  }

  /* ── Tables (inline from manifest — no fetch needed) ── */
  function bindTableToggles(tables, root) {
    (root || document).querySelectorAll(".table-toggle").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.getAttribute("data-table-id");
        var idx = parseInt(btn.getAttribute("data-table-idx"), 10);
        var container = document.getElementById(id);

        if (container.style.display === "none") {
          container.style.display = "block";
          btn.classList.add("expanded");
          if (!container.innerHTML.trim()) {
            renderInlineTable(tables[idx], container);
          }
        } else {
          container.style.display = "none";
          btn.classList.remove("expanded");
        }
      });
    });
  }

  function renderInlineTable(tbl, container) {
    if (!tbl || !tbl.headers || tbl.headers.length === 0) {
      container.innerHTML = "<p style='padding:10px'>Empty table</p>";
      return;
    }

    var headers = tbl.headers;
    var rows = tbl.rows;

    // Determine which columns to hide (diagnostic/model-fit columns)
    var hideCols = computeHiddenColumns(headers);

    // Find grouping columns (pass rows so we only group columns that actually have repeated values)
    var groupCols = findGroupingColumns(headers, rows);
    var visibleCount = hideCols.filter(function (h) { return !h; }).length;

    // Sort rows by grouping columns for clean visual grouping
    if (groupCols.length > 0) {
      rows = rows.slice().sort(function (a, b) {
        for (var gc of groupCols) {
          var va = (a[gc.idx] || "").toString().toLowerCase().replace(/^"|"$/g, "");
          var vb = (b[gc.idx] || "").toString().toLowerCase().replace(/^"|"$/g, "");
          if (va < vb) return -1;
          if (va > vb) return 1;
        }
        return 0;
      });
    }

    // Build table header — hide grouped columns since they appear as sub-headers
    var groupColIndices = groupCols.map(function (gc) { return gc.idx; });
    var html = "<table><thead><tr>";
    for (var ci = 0; ci < headers.length; ci++) {
      if (hideCols[ci] || groupColIndices.indexOf(ci) >= 0) continue;
      html += '<th>' + escapeHtml(formatColumnHeader(headers[ci])) + '<span class="sort-indicator"></span></th>';
    }
    html += "</tr></thead><tbody>";

    var sigIdx = headers.findIndex(function (h) {
      return h.toLowerCase() === "significant";
    });

    // Count visible, non-grouped columns for colspan
    var dataColCount = 0;
    for (var ci = 0; ci < headers.length; ci++) {
      if (!hideCols[ci] && groupColIndices.indexOf(ci) < 0) dataColCount++;
    }

    // Track current group values for sub-header insertion
    var currentGroups = groupCols.map(function () { return null; });

    for (var ri = 0; ri < rows.length; ri++) {
      var row = rows[ri];

      // Insert group sub-headers when values change
      for (var gi = 0; gi < groupCols.length; gi++) {
        var gc = groupCols[gi];
        var val = (row[gc.idx] || "").toString().replace(/^"|"$/g, "");
        if (val !== currentGroups[gi]) {
          currentGroups[gi] = val;
          // Reset child group values when parent changes
          for (var gi2 = gi + 1; gi2 < groupCols.length; gi2++) {
            currentGroups[gi2] = null;
          }
          var formattedVal = gc.formatter(val);
          var level = gi === 0 ? "group-header-primary" : gi === 1 ? "group-header-secondary" : "group-header-tertiary";
          html += '<tr class="' + level + '"><td colspan="' + dataColCount + '">' +
            escapeHtml(gc.label + ": " + formattedVal) + '</td></tr>';
        }
      }

      var isSig = sigIdx >= 0 && row[sigIdx] && row[sigIdx].toUpperCase() === "TRUE";
      html += '<tr' + (isSig ? ' class="significant"' : '') + '>';
      for (var ci = 0; ci < row.length; ci++) {
        if (hideCols[ci] || groupColIndices.indexOf(ci) >= 0) continue;
        html += '<td>' + formatCellValue(row[ci], headers[ci]) + '</td>';
      }
      html += "</tr>";
    }
    html += "</tbody></table>";
    if (tbl.truncated) {
      html += '<p style="padding:8px 10px;font-size:12px;color:var(--text-muted)">Showing ' +
        rows.length + ' of ' + tbl.total_rows + ' rows</p>';
    }
    container.innerHTML = html;
  }

  /**
   * Find columns to use for grouping, in priority order.
   * Returns array of {idx, label, formatter} objects.
   * Supports up to 3 levels: contrast → measure/band → metric.
   * Only includes a column if it actually creates multi-row groups
   * within the context of already-chosen parent grouping columns.
   */
  function findGroupingColumns(headers, rows) {
    var lowerHeaders = headers.map(function (h) { return h.toLowerCase().replace(/^"|"$/g, ""); });
    var groups = [];
    var usedIndices = [];
    var totalRows = rows ? rows.length : 0;

    // Helper: check if adding column at idx creates any leaf group with >1 row,
    // given the already-chosen parent grouping columns.
    function columnAddsGrouping(idx) {
      if (!rows || totalRows <= 1) return false;

      // Build composite keys from parent groups + this candidate
      var allIndices = usedIndices.concat([idx]);
      var keyCounts = {};
      for (var r = 0; r < rows.length; r++) {
        var key = allIndices.map(function (i) {
          return (rows[r][i] || "").toString().replace(/^"|"$/g, "");
        }).join("||");
        keyCounts[key] = (keyCounts[key] || 0) + 1;
      }

      // Check if at least some leaf groups have >1 row
      // (i.e., this column doesn't make every group a singleton)
      var multiRowGroups = 0;
      var totalGroups = 0;
      for (var k in keyCounts) {
        totalGroups++;
        if (keyCounts[k] > 1) multiRowGroups++;
      }

      // Also check that this column has fewer unique values than rows
      // within the parent context (it actually groups something)
      var uniqueVals = {};
      for (var r = 0; r < rows.length; r++) {
        var v = (rows[r][idx] || "").toString().replace(/^"|"$/g, "");
        uniqueVals[v] = true;
      }
      var uniqueCount = Object.keys(uniqueVals).length;
      if (uniqueCount >= totalRows) return false;

      // If adding this column makes ALL groups singletons, it's not useful as a grouping column.
      // Keep the column as a regular data column instead.
      return totalGroups < totalRows;
    }

    // Primary: contrast (or "key" for NBS tables)
    var contrastIdx = lowerHeaders.indexOf("contrast");
    if (contrastIdx < 0) contrastIdx = lowerHeaders.indexOf("key");
    if (contrastIdx >= 0 && columnAddsGrouping(contrastIdx)) {
      groups.push({
        idx: contrastIdx,
        label: contrastIdx === lowerHeaders.indexOf("key") ? "Key" : "Contrast",
        formatter: contrastIdx === lowerHeaders.indexOf("key") ? function (v) { return formatName(v); } : formatContrast,
      });
      usedIndices.push(contrastIdx);
    }

    // Ordered list of all possible secondary/tertiary groupings
    var candidates = [
      { names: ["measure_type", "type", "power_type"], label: "Measure Type", formatter: formatMeasureName },
      { names: ["dv", "measure"], label: "Measure", formatter: formatMeasureName },
      { names: ["freq_pair"], label: "Frequency Pair", formatter: function (v) { return formatName(v); } },
      { names: ["parameter"], label: "Parameter", formatter: function (v) { return formatName(v); } },
      { names: ["band"], label: "Band", formatter: function (v) { return formatName(v); } },
      { names: ["conn_metric"], label: "Connectivity", formatter: function (v) { return formatName(v); } },
      { names: ["metric"], label: "Metric", formatter: function (v) { return formatName(v); } },
      { names: ["graph_metric"], label: "Graph Metric", formatter: function (v) { return formatName(v); } },
    ];

    // Add up to 2 more grouping levels from candidates
    for (var cand of candidates) {
      if (groups.length >= 3) break;
      for (var name of cand.names) {
        var idx = lowerHeaders.indexOf(name);
        if (idx >= 0 && usedIndices.indexOf(idx) < 0 && columnAddsGrouping(idx)) {
          groups.push({ idx: idx, label: cand.label, formatter: cand.formatter });
          usedIndices.push(idx);
          break;
        }
      }
    }

    return groups;
  }

  /**
   * Determine which columns to hide for cleaner presentation.
   * Returns an array of booleans (true = hidden).
   */
  function computeHiddenColumns(headers) {
    var lowerHeaders = headers.map(function (h) { return h.toLowerCase().replace(/"/g, ""); });
    var hide = new Array(headers.length).fill(false);

    // Always hide these diagnostic/redundant columns
    var alwaysHide = [
      "converged", "singular", "convergence",
      "aic_spatial", "bic_spatial", "aic_nonspatial", "bic_nonspatial", "aic_improvement",
      "sig_label",
    ];

    for (var i = 0; i < lowerHeaders.length; i++) {
      if (alwaysHide.indexOf(lowerHeaders[i]) >= 0) {
        hide[i] = true;
      }
    }

    return hide;
  }

  /**
   * Format a column header for display.
   */
  function formatColumnHeader(header) {
    // Strip surrounding quotes
    var h = header.replace(/^"|"$/g, "");

    // Special header renames
    var renames = {
      "group_f": "Group F",
      "group_p": "Group p",
      "roi_f": "ROI F",
      "roi_p": "ROI p",
      "interaction_f": "Interaction F",
      "interaction_p": "Interaction p",
      "group_q": "Group q (FDR)",
      "group_significant": "Group Sig.",
      "interaction_q": "Interaction q (FDR)",
      "interaction_significant": "Interact. Sig.",
      "n_a": "N (A)",
      "n_b": "N (B)",
      "n_rois": "N ROIs",
      "n_regions": "N Regions",
      "group_a": "Group A",
      "group_b": "Group B",
      "measure_type": "Type",
      "dv": "Measure",
      "t_ratio": "t",
      "t_value": "t",
      "p_value": "p",
      "q_value": "q (FDR)",
      "hedges_g": "Hedges' g",
      "std_error": "SE",
      "estimated_range_mm": "Range (mm)",
      "mean_t": "Mean |t|",
      "max_abs_t": "Max |t|",
      "mean_hedges_g": "Mean |g|",
      "max_abs_hedges_g": "Max |g|",
      "n_nominal_sig": "N sig. (uncorr.)",
      "n_vertices": "N Vertices",
      "cluster_stat": "Cluster Stat",
      "peak_t": "Peak t",
      "p_corrected": "p (corrected)",
      "cluster_id": "Cluster",
      "vertex_idx": "Vertex",
      "conn_metric": "Connectivity",
      "graph_metric": "Graph Metric",
      "p_fdr": "p (FDR)",
      "emmean_a": "EMM (A)",
      "emmean_b": "EMM (B)",
      "mean_a": "Mean (A)",
      "mean_b": "Mean (B)",
      "sd_a": "SD (A)",
      "sd_b": "SD (B)",
      "t_stat": "t",
      "observed_diff": "Diff",
    };

    var lower = h.toLowerCase();
    if (renames[lower]) return renames[lower];

    // Default: apply formatName
    return formatName(h);
  }

  /**
   * Format a cell value for display.
   */
  function formatCellValue(value, header) {
    if (value === null || value === undefined || value === "") {
      return '<span style="color:var(--text-muted)">—</span>';
    }

    var str = String(value).replace(/^"|"$/g, ""); // strip quotes
    var headerLower = header.toLowerCase().replace(/^"|"$/g, "");

    // Format contrast names: "30mgkg_vs_Vehicle" → "AUT00206 (30 mg/kg) vs Vehicle"
    if (headerLower === "contrast") {
      return escapeHtml(formatContrast(str));
    }

    // Format group names
    if (headerLower === "group_a" || headerLower === "group_b" || headerLower === "group") {
      return escapeHtml(formatGroupName(str));
    }

    // Format measure names (e.g. "itc_40hz" → "ITC 40 Hz")
    if (headerLower === "measure" || headerLower === "dv" || headerLower === "measure_type") {
      return escapeHtml(formatMeasureName(str));
    }

    // Format band names
    if (headerLower === "band") {
      return escapeHtml(formatName(str));
    }

    // Format metric names
    if (headerLower === "metric" || headerLower === "graph_metric" || headerLower === "conn_metric") {
      return escapeHtml(formatName(str));
    }

    // Boolean display
    if (headerLower === "significant" || headerLower === "group_significant" || headerLower === "interaction_significant") {
      var upper = str.toUpperCase();
      if (upper === "TRUE") return '<strong style="color:#4CAF50">Yes</strong>';
      if (upper === "FALSE") return '<span style="color:var(--text-muted)">No</span>';
    }

    // Numeric formatting
    var num = parseFloat(str);
    if (!isNaN(num) && isFinite(num) && str.match(/^-?\d*\.?\d+(?:e[+-]?\d+)?$/i)) {
      return escapeHtml(formatNumber(num, headerLower));
    }

    return escapeHtml(str);
  }

  /**
   * Format a contrast string for display.
   * "30mgkg_vs_Vehicle" → "AUT00206 (30 mg/kg) vs Vehicle"
   */
  function formatContrast(str) {
    var parts = str.split("_vs_");
    if (parts.length === 2) {
      return formatGroupName(parts[0]) + " vs " + formatGroupName(parts[1]);
    }
    return formatName(str);
  }

  /**
   * Format a group name for display.
   */
  function formatGroupName(name) {
    var lower = name.toLowerCase();
    if (GROUP_LABELS[lower]) return GROUP_LABELS[lower];
    return name;
  }

  /**
   * Format measure names like "itc_40hz" → "ITC 40 Hz", "stp_onset" → "STP Onset"
   */
  function formatMeasureName(str) {
    // Split on underscores and format each part
    return str.split("_").map(function (part) {
      var lower = part.toLowerCase();
      if (ACRONYMS[lower]) return ACRONYMS[lower];
      var hzMatch = lower.match(/^(\d+)(hz)$/);
      if (hzMatch) return hzMatch[1] + " Hz";
      return part.charAt(0).toUpperCase() + part.slice(1);
    }).join(" ");
  }

  /**
   * Format a number based on context (header name).
   */
  function formatNumber(num, headerLower) {
    // p-values: show 3-4 significant digits, scientific notation for very small
    if (headerLower.match(/^p$|^p_|_p$|p_value|p_corrected|q_value|group_q|interaction_q|p_fdr/)) {
      if (num < 0.001) return num.toExponential(2);
      return num.toFixed(4);
    }

    // F-statistics, t-statistics
    if (headerLower.match(/^f$|_f$|group_f|roi_f|interaction_f|^t$|t_ratio|t_value|t_stat|peak_t|mean_t|max_abs_t|cluster_stat/)) {
      return num.toFixed(3);
    }

    // Effect sizes (hedges_g, etc.)
    if (headerLower.match(/hedges_g|mean_hedges_g|max_abs_hedges_g|cohen/)) {
      return num.toFixed(3);
    }

    // Estimates, means, SEs, coefficients
    if (headerLower.match(/estimate|coefficient|std_error|^se$|emmean|^mean|^sd/)) {
      return num.toFixed(4);
    }

    // Degrees of freedom
    if (headerLower.match(/^df$/)) {
      return Math.abs(num - Math.round(num)) < 0.01 ? num.toFixed(0) : num.toFixed(1);
    }

    // AIC/BIC
    if (headerLower.match(/^aic|^bic/)) {
      return num.toFixed(1);
    }

    // Integers (counts)
    if (headerLower.match(/^n$|^n_|n_edges|n_vertices|n_rois|n_regions|n_nominal|n_sig|cluster_id|vertex_idx|n_permutations/)) {
      return Math.abs(num - Math.round(num)) < 0.01 ? num.toFixed(0) : num.toFixed(2);
    }

    // Default: 4 significant figures
    if (Math.abs(num) >= 100) return num.toFixed(1);
    if (Math.abs(num) >= 1) return num.toFixed(3);
    if (Math.abs(num) >= 0.001) return num.toFixed(4);
    return num.toExponential(2);
  }

  /**
   * Format table filename for display.
   * "evoked_omnibus.csv" → "Evoked Omnibus"
   */
  function formatTableFilename(filename) {
    var name = filename.replace(/\.csv$/i, "");
    return formatName(name);
  }

  function initTableSort() {
    if (!window.Tablesort) return;
    document.querySelectorAll(".table-container table").forEach(function (table) {
      new Tablesort(table);
    });
  }

  /* ── Lightbox ── */
  function initLightbox() {
    if (lightbox) { lightbox.destroy(); }
    if (window.GLightbox) {
      lightbox = GLightbox({
        selector: ".glightbox",
        touchNavigation: true,
        loop: true,
        zoomable: true,
        draggable: true,
      });
    }
  }

  /* ── Theme ── */
  function initThemeToggle() {
    var saved = localStorage.getItem("theme");
    if (saved) {
      document.documentElement.setAttribute("data-theme", saved);
    } else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) {
      document.documentElement.setAttribute("data-theme", "light");
    }

    document.getElementById("theme-toggle").addEventListener("click", function () {
      var current = document.documentElement.getAttribute("data-theme");
      var next = current === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("theme", next);
    });
  }

  /* ── Keyboard ── */
  function initKeyboard() {
    document.addEventListener("keydown", function (e) {
      if (e.key === "/" && document.activeElement.tagName !== "INPUT") {
        e.preventDefault();
        document.getElementById("search-input").focus();
      }
      if (e.key === "Escape") {
        document.getElementById("search-input").blur();
      }
    });
  }

  /* ── Helpers ── */
  function setBreadcrumb(parts) {
    var el = document.getElementById("breadcrumb");
    el.innerHTML = parts.map(function (p, i) {
      return (i > 0 ? "<span>&rsaquo;</span>" : "") + escapeHtml(p);
    }).join("");
  }

  function setContent(html) {
    document.getElementById("figures-section").innerHTML = html;
    document.getElementById("tables-section").innerHTML = "";
    document.getElementById("summary-section").innerHTML = "";
  }

  function formatName(slug) {
    return slug
      .replace(/_/g, " ")
      .split(" ")
      .map(function (word) {
        var lower = word.toLowerCase();
        if (ACRONYMS[lower]) return ACRONYMS[lower];
        // Handle "40hz" → "40 Hz", "80hz" → "80 Hz"
        var hzMatch = lower.match(/^(\d+)(hz)$/);
        if (hzMatch) return hzMatch[1] + " Hz";
        return word.charAt(0).toUpperCase() + word.slice(1);
      })
      .join(" ");
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
})();
